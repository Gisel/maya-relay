from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import PlainTextResponse, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from app.config import Settings, get_settings
from app.db import RelayRepository
from app.dependencies import get_relay_service, get_repository
from app.models import IncomingMessage
from app.services.relay import RelayService


router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])


def _empty_twiml() -> PlainTextResponse:
    return PlainTextResponse(str(MessagingResponse()), media_type="text/xml")


async def _validate_twilio_request(request: Request, settings: Settings) -> bool:
    if not settings.verify_twilio_signature:
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    form = dict(await request.form())
    validator = RequestValidator(settings.twilio_auth_token)
    return validator.validate(_public_request_url(request), form, signature)


def _public_request_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")

    if forwarded_proto and forwarded_host:
        url = f"{forwarded_proto}://{forwarded_host}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        return url

    return str(request.url)


async def _incoming_message_from_request(
    request: Request,
    *,
    message_sid: str,
    from_phone: str,
    to_phone: str,
    body: str,
    num_media: int,
) -> IncomingMessage:
    form = await request.form()
    media_urls: list[str] = []
    media_content_types: list[str] = []
    for index in range(num_media):
        media_url = form.get(f"MediaUrl{index}")
        media_content_type = form.get(f"MediaContentType{index}")
        if isinstance(media_url, str) and media_url:
            media_urls.append(media_url)
        if isinstance(media_content_type, str) and media_content_type:
            media_content_types.append(media_content_type)
    return IncomingMessage(
        message_sid=message_sid,
        from_phone=from_phone,
        to_phone=to_phone,
        body=body,
        num_media=num_media,
        media_urls=tuple(media_urls),
        media_content_types=tuple(media_content_types),
    )


@router.post("/sms")
async def inbound_sms(
    request: Request,
    MessageSid: str = Form(default=""),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(default=""),
    NumMedia: int = Form(default=0),
    settings: Settings = Depends(get_settings),
    relay_service: RelayService = Depends(get_relay_service),
) -> Response:
    if not await _validate_twilio_request(request, settings):
        return PlainTextResponse("Forbidden", status_code=403)

    relay_service.handle_inbound_sms(
        await _incoming_message_from_request(
            request,
            message_sid=MessageSid,
            from_phone=From,
            to_phone=To,
            body=Body,
            num_media=NumMedia,
        )
    )
    return _empty_twiml()


@router.post("/whatsapp")
async def inbound_whatsapp(
    request: Request,
    MessageSid: str = Form(default=""),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(default=""),
    NumMedia: int = Form(default=0),
    settings: Settings = Depends(get_settings),
    relay_service: RelayService = Depends(get_relay_service),
) -> Response:
    return await inbound_sms(
        request=request,
        MessageSid=MessageSid,
        From=_strip_whatsapp_prefix(From),
        To=_strip_whatsapp_prefix(To),
        Body=Body,
        NumMedia=NumMedia,
        settings=settings,
        relay_service=relay_service,
    )


@router.post("/employee")
async def employee_sms(
    request: Request,
    MessageSid: str = Form(default=""),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(default=""),
    NumMedia: int = Form(default=0),
    settings: Settings = Depends(get_settings),
    relay_service: RelayService = Depends(get_relay_service),
) -> Response:
    return await inbound_sms(
        request=request,
        MessageSid=MessageSid,
        From=From,
        To=To,
        Body=Body,
        NumMedia=NumMedia,
        settings=settings,
        relay_service=relay_service,
    )


@router.post("/status")
async def message_status(
    request: Request,
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    ErrorCode: str | None = Form(default=None),
    ErrorMessage: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> Response:
    if not await _validate_twilio_request(request, settings):
        return PlainTextResponse("Forbidden", status_code=403)

    repository.update_message_status(
        twilio_message_sid=MessageSid,
        status=MessageStatus,
        error_code=ErrorCode,
        error_message=ErrorMessage,
    )
    return Response(status_code=204)


def _strip_whatsapp_prefix(phone_number: str) -> str:
    prefix = "whatsapp:"
    if phone_number.lower().startswith(prefix):
        return phone_number[len(prefix):]
    return phone_number
