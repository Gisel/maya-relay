import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request

from app.config import Settings


SESSION_COOKIE = "maya_admin"
SESSION_VERSION = 1
SESSION_TTL = timedelta(hours=12)


@dataclass(frozen=True)
class OperatorProfile:
    id: str
    email: str
    display_name: str
    role: str
    routing_line: str
    click_to_call_phone: str
    active: bool = True
    supabase_user_id: str | None = None


def admin_enabled(settings: Settings) -> None:
    if not settings.admin_password and not settings.operator_auth_configured:
        raise HTTPException(status_code=404)


def session_value(settings: Settings) -> str:
    return hmac.new(
        settings.admin_password.encode("utf-8"),
        b"maya-admin-session",
        "sha256",
    ).hexdigest()


def operator_session_value(settings: Settings, operator: OperatorProfile) -> str:
    secret = settings.auth_cookie_secret
    if not secret:
        raise HTTPException(status_code=503, detail="AUTH_SESSION_SECRET is required for operator sessions.")
    expires_at = datetime.now(UTC) + SESSION_TTL
    payload = {
        "version": SESSION_VERSION,
        "operatorId": operator.id,
        "email": operator.email,
        "displayName": operator.display_name,
        "role": operator.role,
        "routingLine": operator.routing_line,
        "clickToCallPhone": operator.click_to_call_phone,
        "supabaseUserId": operator.supabase_user_id,
        "expiresAt": expires_at.isoformat(),
    }
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _sign(encoded_payload, secret)
    return f"operator.{encoded_payload}.{signature}"


def current_operator(request: Request, settings: Settings) -> OperatorProfile | None:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if not cookie.startswith("operator."):
        return None
    payload = _verified_operator_payload(cookie, settings)
    if payload is None:
        return None
    return OperatorProfile(
        id=str(payload.get("operatorId") or ""),
        email=str(payload.get("email") or ""),
        display_name=str(payload.get("displayName") or ""),
        role=str(payload.get("role") or "operator"),
        routing_line=str(payload.get("routingLine") or ""),
        click_to_call_phone=str(payload.get("clickToCallPhone") or ""),
        active=True,
        supabase_user_id=str(payload["supabaseUserId"]) if payload.get("supabaseUserId") else None,
    )


def is_authenticated(request: Request, settings: Settings) -> bool:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if current_operator(request, settings) is not None:
        return True
    if settings.enable_admin_password_fallback and settings.admin_password:
        return hmac.compare_digest(cookie, session_value(settings))
    return False


def require_admin(request: Request, settings: Settings) -> None:
    admin_enabled(settings)
    if not is_authenticated(request, settings):
        raise HTTPException(status_code=401)


def _verified_operator_payload(cookie: str, settings: Settings) -> dict[str, Any] | None:
    secret = settings.auth_cookie_secret
    if not secret:
        return None
    parts = cookie.split(".")
    if len(parts) != 3 or parts[0] != "operator":
        return None
    encoded_payload = parts[1]
    expected_signature = _sign(encoded_payload, secret)
    if not hmac.compare_digest(parts[2], expected_signature):
        return None
    try:
        payload = json.loads(_b64url_decode(encoded_payload))
        expires_at = datetime.fromisoformat(str(payload.get("expiresAt")))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    if payload.get("version") != SESSION_VERSION or not payload.get("operatorId") or not payload.get("email"):
        return None
    return payload


def _sign(encoded_payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")
