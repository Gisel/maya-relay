import base64
import json

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.db import RelayRepository
from app.dependencies import get_repository


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readiness")
def readiness(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    checks = {
        "verify_twilio_signature": settings.verify_twilio_signature,
        "enable_twilio_lookup": settings.enable_twilio_lookup,
        "twilio_account_sid": bool(settings.twilio_account_sid),
        "twilio_auth_token": bool(settings.twilio_auth_token),
        "twilio_messaging_service_sid": bool(settings.twilio_messaging_service_sid),
        "maya_business_number": bool(settings.maya_business_number),
        "francisco_phone": bool(settings.francisco_phone),
        "supabase_url": bool(settings.supabase_url),
        "supabase_service_role_key": bool(settings.supabase_service_role_key),
        "supabase_key_role": _jwt_role(settings.supabase_service_role_key),
    }
    return {"status": "ready" if all(checks.values()) else "missing_config", "checks": checks}


@router.get("/readiness/supabase")
def supabase_readiness(repository: RelayRepository = Depends(get_repository)) -> dict[str, object]:
    try:
        repository.get_latest_employee_conversation("__readiness_check__")
    except Exception as exc:
        return {
            "status": "error",
            "error_type": exc.__class__.__name__,
        }
    return {"status": "ok"}


def _jwt_role(token: str) -> str | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        claims = json.loads(decoded)
    except Exception:
        return None
    role = claims.get("role")
    return role if isinstance(role, str) else None
