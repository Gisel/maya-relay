from urllib.parse import urlparse

from fastapi import HTTPException, Request

from app.config import Settings


def public_base_url(request: Request, settings: Settings) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        request_base_url = f"{forwarded_proto}://{forwarded_host}"
    else:
        request_base_url = str(request.base_url).rstrip("/")

    configured_base_url = settings.app_base_url.strip().rstrip("/")
    if configured_base_url and not is_local_base_url(configured_base_url):
        return configured_base_url
    if request_base_url:
        return request_base_url

    return configured_base_url or "http://localhost:8000"


def required_public_base_url(request: Request, settings: Settings) -> str:
    base_url = public_base_url(request, settings)
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or is_local_base_url(base_url):
        raise HTTPException(
            status_code=503,
            detail="APP_BASE_URL must be set to the public HTTPS Maya Relay URL before sending password reset links.",
        )
    return base_url


def is_local_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0"}
