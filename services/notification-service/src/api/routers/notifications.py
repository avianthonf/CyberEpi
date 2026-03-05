"""Notification-service API – push notifications, SSE stream, Kafka consumer."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from src.auth import get_current_user
from src.db.models import PushToken
from src.db.session import get_db

logger = structlog.get_logger()
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────
class SendNotificationRequest(BaseModel):
    patient_id: uuid.UUID
    title: str
    body: str
    data: dict[str, Any] | None = None


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
    except Exception as e:
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
    except Exception as e:
        logger.warning("APNs send failed", error=str(e))
        return False


# ─── Endpoints ────────────────────────────────────────────────────
@router.post("/api/v1/notifications/send", response_model=SendNotificationResponse)
async def send_notification(
    body: SendNotificationRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> SendNotificationResponse:
    """Send push notification to a patient's registered devices."""
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

    return SendNotificationResponse(
        patient_id=body.patient_id,
        platforms_sent=platforms_sent,
    )


@router.get("/api/v1/physicians/{physician_id}/alerts/stream")
async def physician_alert_stream(
    physician_id: uuid.UUID,
    request: Request,
    _user: dict[str, Any] = Depends(get_current_user),
) -> EventSourceResponse:
    """SSE stream of patient alerts for a physician.

    Uses Redis pub/sub channel alerts:{physician_id}.
    """
    redis_client: aioredis.Redis = request.app.state.redis

    async def event_generator():
        pubsub = redis_client.pubsub()
        channel = f"alerts:{physician_id}"
        await pubsub.subscribe(channel)

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
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return EventSourceResponse(event_generator())
