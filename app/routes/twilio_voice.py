from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import PlainTextResponse, Response
from twilio.twiml.voice_response import VoiceResponse

from app.config import Settings, get_settings, normalize_phone_number
from app.db import RelayRepository
from app.dependencies import get_repository
from app.routes.twilio_sms import _validate_twilio_request


router = APIRouter(prefix="/webhooks/twilio/voice", tags=["twilio"])


@router.post("/bridge/{conversation_id}")
async def bridge_click_to_call(
    conversation_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> Response:
    if not await _validate_twilio_request(request, settings):
        return PlainTextResponse("Forbidden", status_code=403)

    response = VoiceResponse()
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        response.say("Sorry, Maya Relay could not find this customer conversation.")
        return PlainTextResponse(str(response), media_type="text/xml")

    customer_phone = _voice_phone_number(conversation.customer_phone)
    if not customer_phone:
        response.say("Sorry, Maya Relay could not find a callable customer phone number.")
        return PlainTextResponse(str(response), media_type="text/xml")

    response.say("Connecting you to the customer.")
    dial = response.dial(caller_id=settings.maya_business_number_e164, answer_on_bridge=True)
    dial.number(customer_phone)
    return PlainTextResponse(str(response), media_type="text/xml")


@router.post("/status")
async def voice_call_status(
    request: Request,
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default=""),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not await _validate_twilio_request(request, settings):
        return PlainTextResponse("Forbidden", status_code=403)

    # CallSid/CallStatus are accepted for observability; a dedicated calls table can persist them later.
    _ = (CallSid, CallStatus)
    return Response(status_code=204)


def _voice_phone_number(phone_number: str) -> str:
    prefix = "whatsapp:"
    if phone_number.lower().startswith(prefix):
        phone_number = phone_number[len(prefix):]
    return normalize_phone_number(phone_number)
