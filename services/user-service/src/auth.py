"""JWT authentication — shared via libs/shared."""

from __future__ import annotations

from shared.auth import build_auth_dependency

from src.config import settings

get_current_user, require_role = build_auth_dependency(settings)
