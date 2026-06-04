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
    return validator.validate(str(request.url), form, signature)


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
        IncomingMessage(
            message_sid=MessageSid,
            from_phone=From,
            to_phone=To,
            body=Body,
            num_media=NumMedia,
        )
    )
    return _empty_twiml()


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
