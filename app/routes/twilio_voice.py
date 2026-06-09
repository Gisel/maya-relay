import logging
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import PlainTextResponse, Response
from twilio.twiml.voice_response import VoiceResponse

from app.config import Settings, get_settings, normalize_phone_number
from app.db import RelayRepository
from app.dependencies import get_repository
from app.routes.twilio_sms import _validate_twilio_request


router = APIRouter(prefix="/webhooks/twilio/voice", tags=["twilio"])
logger = logging.getLogger(__name__)


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
    repository: RelayRepository = Depends(get_repository),
) -> Response:
    if not await _validate_twilio_request(request, settings):
        return PlainTextResponse("Forbidden", status_code=403)

    try:
        form_payload = await request.form()
        payload: dict[str, Any] = {key: str(value) for key, value in form_payload.multi_items()}
        call = repository.update_call_status_by_sid(
            twilio_call_sid=CallSid,
            status=CallStatus or "unknown",
        )
        repository.create_call_event(
            call_id=call.get("id") if call else None,
            twilio_call_sid=CallSid or None,
            event_type=CallStatus or "status",
            call_status=CallStatus or None,
            payload=payload,
        )
    except Exception:
        logger.exception("Failed to persist Twilio voice status for CallSid %s", CallSid)

    return Response(status_code=204)


@router.post("/studio/incoming")
async def studio_incoming_voice_call(
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
):
    form_payload = await request.form()
    payload: dict[str, Any] = {key: str(value) for key, value in form_payload.multi_items()}
    if not await _validate_studio_or_twilio_request(request, settings, payload):
        return PlainTextResponse("Forbidden", status_code=403)

    employee_phone = settings.francisco_phone_e164
    call_sid = _payload_value(payload, "CallSid", "call_sid", "callSid", "trigger.call.CallSid")
    call_status = _payload_value(payload, "CallStatus", "call_status", "callStatus") or "ringing"
    customer_phone = _voice_phone_number(_payload_value(payload, "From", "from", "customer_phone", "customerPhone"))
    if not employee_phone:
        return {"status": "missing_employee_phone"}
    if not customer_phone:
        return {"status": "missing_customer_phone"}

    call: dict[str, Any] | None = None
    try:
        conversation = repository.get_or_create_customer_conversation(
            customer_phone=customer_phone,
            assigned_employee=employee_phone,
            customer_channel="sms",
        )
        call = repository.update_call_status_by_sid(twilio_call_sid=call_sid, status=call_status) if call_sid else None
        if call is None:
            call = repository.create_call(
                conversation_id=conversation.id,
                direction="inbound",
                call_type="inbound",
                customer_phone=customer_phone,
                employee_phone=employee_phone,
                twilio_call_sid=call_sid or None,
                status=call_status,
            )
        repository.create_call_event(
            call_id=call.get("id"),
            twilio_call_sid=call_sid or None,
            event_type=call_status or "incoming",
            call_status=call_status,
            payload=payload,
        )
    except Exception:
        logger.exception("Failed to persist Studio inbound voice call for CallSid %s", call_sid)
        return {"status": "error"}

    return {
        "status": "logged",
        "callId": call.get("id") if call else None,
        "conversationId": call.get("conversation_id") if call else None,
    }


@router.post("/studio/complete")
async def studio_incoming_voice_complete(
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> Response:
    form_payload = await request.form()
    payload: dict[str, Any] = {key: str(value) for key, value in form_payload.multi_items()}
    if not await _validate_studio_or_twilio_request(request, settings, payload):
        return PlainTextResponse("Forbidden", status_code=403)

    try:
        call_sid = _payload_value(payload, "CallSid", "call_sid", "callSid", "trigger.call.CallSid")
        status = _inbound_dial_status(
            _payload_value(payload, "DialCallStatus", "dial_call_status", "CallStatus", "call_status")
        )
        call = repository.update_call_status_by_sid(
            twilio_call_sid=call_sid,
            status=status,
        )
        repository.create_call_event(
            call_id=call.get("id") if call else None,
            twilio_call_sid=call_sid or None,
            event_type="studio-complete",
            call_status=status,
            payload=payload,
        )
    except Exception:
        logger.exception("Failed to complete Studio inbound voice call.")

    return Response(status_code=204)


def _inbound_dial_status(dial_call_status: str) -> str:
    normalized = (dial_call_status or "").strip().lower()
    if normalized in {"completed", "busy", "failed", "no-answer", "canceled", "cancelled"}:
        return normalized
    if normalized in {"answered", "in-progress"}:
        return "answered"
    return normalized or "completed"


async def _validate_studio_or_twilio_request(request: Request, settings: Settings, payload: dict[str, Any]) -> bool:
    studio_secret = settings.twilio_studio_webhook_secret.strip()
    if studio_secret:
        return _payload_value(payload, "access_key", "accessKey", "secret") == studio_secret
    if request.headers.get("X-Twilio-Signature"):
        return await _validate_twilio_request(request, settings)
    return not settings.verify_twilio_signature


def _payload_value(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value:
            return str(value).strip()
    return ""


def _voice_phone_number(phone_number: str) -> str:
    prefix = "whatsapp:"
    if phone_number.lower().startswith(prefix):
        phone_number = phone_number[len(prefix):]
    return normalize_phone_number(phone_number)
