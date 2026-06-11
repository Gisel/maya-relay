import logging
import time
from typing import Any

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import PlainTextResponse, Response
from twilio.twiml.voice_response import VoiceResponse

from app.config import Settings, get_settings, normalize_phone_number
from app.db import RelayRepository
from app.dependencies import get_repository
from app.routes.api import _download_twilio_recording, _generate_call_recap_with_openai, _transcribe_audio_with_assemblyai
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
    background_tasks: BackgroundTasks,
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
        if settings.enable_call_recording_automation and call and call.get("id") and call_sid and status == "completed":
            background_tasks.add_task(
                _sync_studio_recording,
                settings,
                repository,
                str(call["id"]),
                call_sid,
            )
    except Exception:
        logger.exception("Failed to complete Studio inbound voice call.")

    return Response(status_code=204)


@router.post("/recording")
async def voice_recording_status(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> Response:
    form_payload = await request.form()
    payload: dict[str, Any] = {key: str(value) for key, value in form_payload.multi_items()}
    if not await _validate_recording_request(request, settings, payload):
        return PlainTextResponse("Forbidden", status_code=403)

    call_sid = _payload_value(payload, "CallSid", "call_sid", "callSid")
    recording_status = _payload_value(payload, "RecordingStatus", "recording_status", "recordingStatus")
    recording_sid = _payload_value(payload, "RecordingSid", "recording_sid", "recordingSid")
    recording_url = _payload_value(payload, "RecordingUrl", "recording_url", "recordingUrl")
    recording_duration_seconds = _int_payload_value(
        payload,
        "RecordingDuration",
        "recording_duration",
        "recordingDuration",
    )
    recording_channels = _int_payload_value(payload, "RecordingChannels", "recording_channels", "recordingChannels")

    try:
        call = repository.update_call_recording_by_sid(
            twilio_call_sid=call_sid,
            recording_sid=recording_sid or None,
            recording_url=recording_url or None,
            recording_status=recording_status or None,
            recording_duration_seconds=recording_duration_seconds,
            recording_channels=recording_channels,
        )
        repository.create_call_event(
            call_id=call.get("id") if call else None,
            twilio_call_sid=call_sid or None,
            event_type="recording-status",
            call_status=recording_status or None,
            payload=payload,
        )
        if (
            settings.enable_call_recording_automation
            and call
            and call.get("id")
            and recording_status == "completed"
            and recording_url
        ):
            background_tasks.add_task(
                _automate_completed_recording,
                settings,
                repository,
                str(call["id"]),
            )
    except Exception:
        logger.exception("Failed to persist Twilio recording status for CallSid %s", call_sid)

    return Response(status_code=204)


def _automate_completed_recording(settings: Settings, repository: RelayRepository, call_id: str) -> None:
    call = repository.get_call(call_id)
    if not call:
        return
    recording_url = str(call.get("recording_url") or "").strip()
    if not recording_url:
        return

    transcription = str(call.get("transcription") or "").strip()
    if not transcription:
        if not settings.assemblyai_api_key:
            logger.info("Skipping automatic call transcription for %s because ASSEMBLYAI_API_KEY is not configured.", call_id)
            return
        try:
            audio_response = _download_twilio_recording(settings, recording_url)
            transcription = _transcribe_audio_with_assemblyai(settings, audio_response.content)
            updated_call = repository.update_call_transcription(call_id=call_id, transcription=transcription)
            call = updated_call or call
        except Exception:
            logger.exception("Automatic call transcription failed for call %s.", call_id)
            return

    if call.get("recap"):
        return
    if not settings.openai_api_key:
        logger.info("Skipping automatic call recap for %s because OPENAI_API_KEY is not configured.", call_id)
        return
    try:
        recap = _generate_call_recap_with_openai(settings, call=call, transcription=transcription)
        repository.update_call_recap(call_id=call_id, recap=recap)
    except Exception:
        logger.exception("Automatic call recap failed for call %s.", call_id)


def _sync_studio_recording(settings: Settings, repository: RelayRepository, call_id: str, call_sid: str) -> None:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.info("Skipping Studio recording sync for %s because Twilio credentials are not configured.", call_id)
        return

    recording = _fetch_latest_twilio_recording_for_call(settings, call_sid)
    if not recording:
        return

    call = repository.update_call_recording_by_sid(
        twilio_call_sid=call_sid,
        recording_sid=str(recording.get("sid") or "") or None,
        recording_url=_recording_url(settings, recording),
        recording_status=str(recording.get("status") or "") or None,
        recording_duration_seconds=_int_value(recording.get("duration")),
        recording_channels=_int_value(recording.get("channels")),
    )
    if call and call.get("id"):
        _automate_completed_recording(settings, repository, str(call["id"]))


def _fetch_latest_twilio_recording_for_call(settings: Settings, call_sid: str) -> dict[str, Any] | None:
    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}"
        f"/Calls/{call_sid}/Recordings.json"
    )
    for attempt in range(3):
        try:
            response = requests.get(url, auth=(settings.twilio_account_sid, settings.twilio_auth_token), timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Could not fetch Twilio recordings for CallSid %s.", call_sid)
            return None

        recordings = response.json().get("recordings") or []
        completed_recordings = [
            recording
            for recording in recordings
            if str(recording.get("status") or "").lower() == "completed"
        ]
        if completed_recordings:
            return max(completed_recordings, key=lambda recording: _int_value(recording.get("duration")) or 0)
        if attempt < 2:
            time.sleep(3)
    logger.info("No completed Twilio recording found yet for CallSid %s.", call_sid)
    return None


def _recording_url(settings: Settings, recording: dict[str, Any]) -> str | None:
    url = str(recording.get("media_url") or recording.get("uri") or "").strip()
    if not url:
        recording_sid = str(recording.get("sid") or "").strip()
        if not recording_sid:
            return None
        return f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Recordings/{recording_sid}"
    if url.startswith("/"):
        return f"https://api.twilio.com{url}"
    return url


def _int_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


async def _validate_recording_request(request: Request, settings: Settings, payload: dict[str, Any]) -> bool:
    if request.headers.get("X-Twilio-Signature"):
        return await _validate_twilio_request(request, settings)

    studio_secret = settings.twilio_studio_webhook_secret.strip()
    if studio_secret:
        provided_secret = _payload_value(payload, "access_key", "accessKey", "secret") or request.query_params.get("access_key", "")
        return provided_secret == studio_secret

    return not settings.verify_twilio_signature


def _payload_value(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value:
            return str(value).strip()
    return ""


def _int_payload_value(payload: dict[str, Any], *names: str) -> int | None:
    value = _payload_value(payload, *names)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _voice_phone_number(phone_number: str) -> str:
    prefix = "whatsapp:"
    if phone_number.lower().startswith(prefix):
        phone_number = phone_number[len(prefix):]
    return normalize_phone_number(phone_number)
