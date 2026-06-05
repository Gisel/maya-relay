import hmac

from fastapi import HTTPException, Request

from app.config import Settings


SESSION_COOKIE = "maya_admin"


def admin_enabled(settings: Settings) -> None:
    if not settings.admin_password:
        raise HTTPException(status_code=404)


def session_value(settings: Settings) -> str:
    return hmac.new(
        settings.admin_password.encode("utf-8"),
        b"maya-admin-session",
        "sha256",
    ).hexdigest()


def is_authenticated(request: Request, settings: Settings) -> bool:
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return hmac.compare_digest(cookie, session_value(settings))


def require_admin(request: Request, settings: Settings) -> None:
    admin_enabled(settings)
    if not is_authenticated(request, settings):
        raise HTTPException(status_code=401)
