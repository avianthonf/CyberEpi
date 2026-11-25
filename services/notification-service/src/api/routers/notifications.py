"""Notification-service API - push notifications, SSE stream, Kafka consumer."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from src.auth import get_current_user
from src.db.models import Notification, PushToken
from src.db.session import get_db

logger = structlog.get_logger()
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────
class SendNotificationRequest(BaseModel):
    patient_id: uuid.UUID
    title: str
    body: str
    data: dict[str, Any] | None = None


class CreateNotificationRequest(BaseModel):
    patient_id: uuid.UUID
    title: str
    body: str
    type: str  # risk_alert, reminder, general
    priority: str  # low, medium, high


class UpdateNotificationRequest(BaseModel):
    read: bool


class NotificationResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    title: str
    body: str
    type: str
    priority: str
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SendNotificationResponse(BaseModel):
    message: str = "Notification sent"
    patient_id: uuid.UUID
    platforms_sent: list[str]


# ─── Push notification helpers ────────────────────────────────────
async def _send_fcm(token: str, title: str, body: str, data: dict[str, Any] | None) -> bool:
    """Send push notification via Firebase Cloud Messaging."""
    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )
        messaging.send(message)
        return True
    except Exception as e:  # noqa: BLE001 — Firebase SDK raises many non-public exception types; delivery failure means "not delivered"
        logger.warning("FCM send failed", error=str(e))
        return False


async def _send_apns(token: str, title: str, body: str, data: dict[str, Any] | None) -> bool:
    """Send push notification via Apple Push Notification Service."""
    try:
        from aioapns import APNs, NotificationRequest

        from src.config import settings

        apns = APNs(
            key=settings.apns_key_path,
            key_id=settings.apns_key_id,
            team_id=settings.apns_team_id,
            topic=settings.apns_bundle_id,
        )
        notification = NotificationRequest(
            device_token=token,
            message={
                "aps": {"alert": {"title": title, "body": body}, "sound": "default"},
                **(data or {}),
            },
        )
        response = await apns.send_notification(notification)
        return response.is_successful
    except Exception as e:  # noqa: BLE001 — aioapns raises connection/TLS-level exceptions of varying types
        logger.warning("APNs send failed", error=str(e))
        return False


# ─── Endpoints ────────────────────────────────────────────────────
@router.post("/api/v1/notifications/send", response_model=SendNotificationResponse)
async def send_notification(
    body: SendNotificationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> SendNotificationResponse:
    """Send push notification to a patient's registered devices."""
    # Authorization: Only Physician or Admin can send notifications.
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Access denied: Only physicians or admins can send notifications.")
    result = await db.execute(select(PushToken).where(PushToken.patient_id == body.patient_id))
    tokens = result.scalars().all()
    if not tokens:
        raise HTTPException(status_code=404, detail="No push tokens registered for patient")

    platforms_sent: list[str] = []
    for pt in tokens:
        success = False
        if pt.platform == "android" or pt.platform == "web":
            success = await _send_fcm(pt.token, body.title, body.body, body.data)
        elif pt.platform == "ios":
            success = await _send_apns(pt.token, body.title, body.body, body.data)
        if success:
            platforms_sent.append(pt.platform)

    if not platforms_sent:
        # Every delivery attempt failed (e.g. FCM/APNs not configured).
        # Returning 200 with an empty list made callers believe the message
        # was delivered.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to deliver notification to any registered device",
        )

    return SendNotificationResponse(
        patient_id=body.patient_id,
        platforms_sent=platforms_sent,
    )


@router.get("/api/v1/physicians/{physician_id}/alerts/stream")
async def physician_alert_stream(
    physician_id: uuid.UUID,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> EventSourceResponse:
    """SSE stream of patient alerts for a physician.

    Subscribes to two Redis pub/sub channels:
    - alerts:{physician_id}: Personal alerts published directly to this physician
    - alerts:broadcast: System-wide high-risk alerts (urgent/consult tier) for all staff

    Authorization: Physician can only access their own stream; admin can access any.
    """
    # Authorization: Physician can only listen to their own stream. Admin can listen to any.
    user_id = user.get("sub")

    async def event_generator():
        pubsub = redis_client.pubsub()
        # Subscribe to both personal physician channel and global broadcast
        personal_channel = f"alerts:{physician_id}"
        await pubsub.subscribe(personal_channel, "alerts:broadcast")

        try:
            while True:
                if await request.is_disconnected():
                    break

                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield {
                        "event": "alert",
                        "data": data,
                    }
                else:
                    # Send heartbeat every second to keep connection alive
                    yield {"event": "heartbeat", "data": ""}
                    await asyncio.sleep(1)
        finally:
            await pubsub.unsubscribe(personal_channel, "alerts:broadcast")
            await pubsub.aclose()

    return EventSourceResponse(event_generator())


@router.post("/api/v1/notifications", response_model=NotificationResponse)
async def create_notification(
    body: CreateNotificationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> NotificationResponse:
    """Create a notification record.

    Stores the notification in the database but does NOT send push notifications.
    Use POST /api/v1/notifications/send for immediate push delivery.
    """
    # Authorization check...
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Access denied")

    notification = Notification(
        patient_id=body.patient_id,
        title=body.title,
        body=body.body,
        type=body.type,
        priority=body.priority,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return NotificationResponse.model_validate(notification)


@router.get("/api/v1/notifications", response_model=list[NotificationResponse])
async def get_notifications(
    patient_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[NotificationResponse]:
    """Get notifications, optionally filtered by patient_id."""
    roles = user.get("realm_access", {}).get("roles", [])
    is_staff = "physician" in roles or "admin" in roles
    if not is_staff:
        from src.auth import patient_id_from_jwt

        own_patient_id = await patient_id_from_jwt(db, user)
        if own_patient_id is None:
            raise HTTPException(status_code=403, detail="Access denied")
        if patient_id is not None and patient_id != own_patient_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Patients can only view their own notifications.",
            )
        patient_id = own_patient_id

    query = select(Notification)
    if patient_id:
        query = query.where(Notification.patient_id == patient_id)

    result = await db.execute(query)
    notifications = result.scalars().all()
    return [NotificationResponse.model_validate(n) for n in notifications]


@router.patch("/api/v1/notifications/{notification_id}", response_model=NotificationResponse)
async def update_notification(
    notification_id: uuid.UUID,
    body: UpdateNotificationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> NotificationResponse:
    """Mark notification as read or unread."""
    result = await db.execute(select(Notification).where(Notification.id == notification_id))
    notification = result.scalars().first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    roles = user.get("realm_access", {}).get("roles", [])
    is_staff = "physician" in roles or "admin" in roles
    if not is_staff:
        from src.auth import patient_id_from_jwt

        own_patient_id = await patient_id_from_jwt(db, user)
        if own_patient_id is None or notification.patient_id != own_patient_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Patients can only update their own notifications.",
            )

    notification.read = body.read
    await db.commit()
    await db.refresh(notification)
    return NotificationResponse.model_validate(notification)
