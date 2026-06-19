from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from app.config import Settings


CustomerActionType = Literal["proof", "assets"]
CustomerActionStatus = Literal["pending", "approved", "changes_requested", "submitted", "expired", "canceled"]
CustomerActionEventType = Literal[
    "created",
    "sent",
    "approved",
    "changes_requested",
    "assets_submitted",
    "canceled",
    "expired",
]


@dataclass(frozen=True)
class CustomerActionFileInput:
    role: str
    bucket: str | None = None
    object_path: str | None = None
    public_url: str | None = None
    external_url: str | None = None
    original_filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None


def generate_public_token() -> str:
    return secrets.token_urlsafe(32)


def customer_action_token_secret(settings: Settings) -> str:
    secret = settings.customer_action_token_secret.strip()
    if secret:
        return secret
    if settings.app_env.lower() == "production":
        raise RuntimeError("CUSTOMER_ACTION_TOKEN_SECRET is required in production.")
    return f"development:{settings.admin_password or settings.app_base_url or 'maya-relay'}"


def hash_public_token(token: str, secret: str) -> str:
    if not token.strip():
        raise ValueError("Customer action token is required.")
    if not secret.strip():
        raise ValueError("Customer action token secret is required.")
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def build_public_action_url(base_url: str, *, action_type: CustomerActionType, token: str) -> str:
    root = base_url.strip().rstrip("/") or "http://localhost:8000"
    return f"{root}/{action_type}/{quote(token, safe='')}"
