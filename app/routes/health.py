from fastapi import APIRouter, Depends

from app.config import Settings, get_settings


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readiness")
def readiness(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    checks = {
        "verify_twilio_signature": settings.verify_twilio_signature,
        "twilio_account_sid": bool(settings.twilio_account_sid),
        "twilio_auth_token": bool(settings.twilio_auth_token),
        "twilio_messaging_service_sid": bool(settings.twilio_messaging_service_sid),
        "maya_business_number": bool(settings.maya_business_number),
        "francisco_phone": bool(settings.francisco_phone),
        "supabase_url": bool(settings.supabase_url),
        "supabase_service_role_key": bool(settings.supabase_service_role_key),
    }
    return {"status": "ready" if all(checks.values()) else "missing_config", "checks": checks}
