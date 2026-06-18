import hmac
import logging
import time
from typing import Any, Literal

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.ai_triage import _extract_response_text
from app.attachments import AttachmentStore
from app.auth import SESSION_COOKIE, admin_enabled, require_admin, session_value
from app.config import Settings, get_settings, normalize_phone_number
from app.db import RelayRepository
from app.dependencies import (
    get_attachment_store,
    get_customer_action_service,
    get_repository,
    get_sender,
    get_voice_caller,
)
from app.models import Conversation
from app.reply_helpers import image_attachment_urls, read_uploads, reply_body_with_attachments
from app.services.contact_import import ContactImportValidationError, import_contacts_csv
from app.services.customer_actions import (
    CustomerActionNotFound,
    CustomerActionService,
    CustomerActionStateError,
    CustomerActionValidationError,
)
from app.twilio_client import MessageSender, VoiceCaller


router = APIRouter(prefix="/api", tags=["api"])
logger = logging.getLogger(__name__)


class ConversationUpdate(BaseModel):
    status: Literal["open", "closed"] | None = None


class ContactUpdate(BaseModel):
    displayName: str | None = None
    notes: str | None = None


class NewCallRequest(BaseModel):
    phone_number: str
    display_name: str | None = None


class CallDetailsUpdate(BaseModel):
    outcome: Literal["connected", "voicemail", "no_answer", "follow_up_needed", "wrong_number", "cancelled"] | None = None
    follow_up_status: Literal["none", "needed", "scheduled", "done"] = "none"
    notes: str | None = None
    recap: str | None = None
    transcription: str | None = None


class ProofRequestCreate(BaseModel):
    title: str | None = None
    operatorNote: str | None = None
    proofUrl: str


class ProofRequestChanges(BaseModel):
    comment: str


class ProofRequestApproval(BaseModel):
    comment: str | None = None


class LoginRequest(BaseModel):
    password: str


@router.post("/auth/login")
def api_login(
    payload: LoginRequest,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    admin_enabled(settings)
    if not hmac.compare_digest(payload.password, settings.admin_password):
        raise HTTPException(status_code=401)
    response = JSONResponse({"authenticated": True})
    response.set_cookie(SESSION_COOKIE, session_value(settings), httponly=True, secure=True, samesite="lax")
    return response


@router.post("/auth/logout")
def api_logout(settings: Settings = Depends(get_settings)) -> JSONResponse:
    admin_enabled(settings)
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/me")
def api_me(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_admin(request, settings)
    return {
        "authenticated": True,
        "session": {
            "cookieName": SESSION_COOKIE,
        },
        "app": {
            "name": "Maya Relay",
            "environment": settings.app_env,
        },
        "features": {
            "twilioLookup": settings.enable_twilio_lookup,
            "aiTriage": settings.enable_ai_triage,
        },
    }


@router.get("/readiness")
def api_readiness(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_admin(request, settings)
    checks = {
        "mayaBusinessNumber": bool(settings.maya_business_number),
        "franciscoPhone": bool(settings.francisco_phone_e164),
        "franciscoPhoneIsNotMayaNumber": settings.francisco_phone_e164 != settings.maya_business_number,
        "twilioMessagingServiceSid": bool(settings.twilio_messaging_service_sid),
        "supabaseUrl": bool(settings.supabase_url),
        "supabaseServiceRoleKey": bool(settings.supabase_service_role_key),
        "openaiApiKey": bool(settings.openai_api_key) if settings.enable_ai_triage else True,
    }
    return {
        "status": "ready" if all(checks.values()) else "missing_config",
        "checks": checks,
    }


@router.get("/metrics")
def api_metrics(
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, int]:
    require_admin(request, settings)
    return _conversation_metrics(repository.list_conversations())


@router.get("/quick-responses")
def api_quick_responses(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, list[dict[str, Any]]]:
    require_admin(request, settings)
    return {
        "quickResponses": [
            {
                "id": "missing_job_specs",
                "label": "Request missing job specs",
                "body": (
                    "Thanks. Can you send the size, quantity, material/finish, "
                    "artwork status, and when you need it?"
                ),
                "group": "quick_response",
                "channels": ["sms", "whatsapp"],
            },
            {
                "id": "proof_approval",
                "label": "Send standard proof approval request",
                "body": "Please review the proof and reply approved or send any changes needed.",
                "group": "quick_response",
                "channels": ["sms", "whatsapp"],
            },
            {
                "id": "shop_hours",
                "label": "Provide shop hours and pickup info",
                "body": f"We are open {settings.business_hours_text}",
                "group": "quick_response",
                "channels": ["sms", "whatsapp"],
            },
            {
                "id": "whatsapp_quote_follow_up",
                "label": "Quote follow-up",
                "body": (
                    "Hi - following up on your quote request. Please send size, quantity, "
                    "material/finish, artwork status, and deadline so we can confirm pricing."
                ),
                "group": "whatsapp_draft",
                "channels": ["whatsapp"],
                "requiresActiveWindow": True,
            },
            {
                "id": "whatsapp_proof_ready",
                "label": "Proof ready",
                "body": "Your proof is ready for review. Please reply approved or send any changes needed.",
                "group": "whatsapp_draft",
                "channels": ["whatsapp"],
                "requiresActiveWindow": True,
            },
            {
                "id": "whatsapp_pickup_reminder",
                "label": "Pickup reminder",
                "body": f"Your order is ready for pickup. We are open {settings.business_hours_text}",
                "group": "whatsapp_draft",
                "channels": ["whatsapp"],
                "requiresActiveWindow": True,
            },
            {
                "id": "whatsapp_payment_reminder",
                "label": "Payment reminder",
                "body": (
                    "Your order is ready. Please complete payment before pickup. "
                    "Let us know if you need the payment link resent."
                ),
                "group": "whatsapp_draft",
                "channels": ["whatsapp"],
                "requiresActiveWindow": True,
            },
        ]
    }


@router.get("/operations/status")
def api_operations_status(
    request: Request,
    limit: int = 10,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    safe_limit = min(max(limit, 1), 25)
    status = repository.get_operational_status(limit=safe_limit)
    message_failures = [_serialize_message_failure(message) for message in status["message_failures"]]
    call_attention = [_serialize_call_attention(item) for item in status["call_attention"]]
    return {
        "summary": {
            "messageFailures": len(message_failures),
            "callAttention": len(call_attention),
            "total": len(message_failures) + len(call_attention),
        },
        "messageFailures": message_failures,
        "callAttention": call_attention,
    }


@router.get("/conversations")
def api_conversations(
    request: Request,
    q: str = "",
    status: str = "",
    channel: str = "",
    limit: int = 50,
    offset: int = 0,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    safe_limit = min(max(limit, 1), 100)
    safe_offset = max(offset, 0)
    if q.strip():
        search_pool = repository.list_conversations(limit=500, offset=0, status=status, channel=channel)
        filtered = [
            conversation
            for conversation in search_pool
            if _matches_filters(conversation, q=q, status="", channel="")
        ]
        page_conversations = filtered[safe_offset: safe_offset + safe_limit]
        has_more = len(filtered) > safe_offset + safe_limit
    else:
        conversations = repository.list_conversations(
            limit=safe_limit + 1,
            offset=safe_offset,
            status=status,
            channel=channel,
        )
        has_more = len(conversations) > safe_limit
        page_conversations = conversations[:safe_limit]
    return {
        "metrics": _conversation_metrics(page_conversations),
        "conversations": [_serialize_conversation_list_item(conversation) for conversation in page_conversations],
        "pagination": {
            "limit": safe_limit,
            "offset": safe_offset,
            "nextOffset": safe_offset + safe_limit if has_more else None,
            "hasMore": has_more,
        },
    }


@router.get("/contacts")
def api_contacts(
    request: Request,
    q: str = "",
    limit: int = 25,
    offset: int = 0,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    safe_limit = min(max(limit, 1), 50)
    safe_offset = max(offset, 0)
    contacts, has_more = repository.search_contacts(q=q, limit=safe_limit, offset=safe_offset)
    return {
        "items": [_serialize_contact_search_item(contact) for contact in contacts],
        "pagination": {
            "limit": safe_limit,
            "offset": safe_offset,
            "nextOffset": safe_offset + safe_limit if has_more else None,
            "hasMore": has_more,
        },
    }


@router.patch("/contacts/{contact_id}")
def api_update_contact(
    contact_id: str,
    payload: ContactUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    existing = repository.get_contact_by_id(contact_id)
    if existing is None:
        raise HTTPException(status_code=404)
    contact = repository.update_contact_profile(
        contact_id=contact_id,
        display_name=(
            _clean_optional_text(payload.displayName)
            if "displayName" in payload.model_fields_set
            else existing.display_name
        ),
        notes=(
            _clean_optional_text(payload.notes)
            if "notes" in payload.model_fields_set
            else existing.notes
        ),
    )
    if contact is None:
        raise HTTPException(status_code=404)
    return {"contact": _serialize_contact(contact)}


@router.post("/contacts/import")
def api_import_contacts(
    request: Request,
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    content = file.file.read()
    try:
        result = import_contacts_csv(content=content, repository=repository, overwrite=overwrite)
    except ContactImportValidationError as exc:
        raise HTTPException(status_code=400, detail=[_serialize_contact_import_error(error) for error in exc.errors])
    return {
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
        "invalidRows": [_serialize_contact_import_error(error) for error in result.invalid_rows],
    }


@router.get("/conversations/{conversation_id}")
def api_conversation_detail(
    conversation_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404)

    conversation_row = _conversation_metadata(repository, conversation)
    messages = repository.list_messages_for_conversation(conversation_id)
    calls = repository.list_calls_for_conversation(conversation_id)
    customer_actions = repository.list_customer_actions_for_conversation(conversation_id)
    return {
        "conversation": _serialize_conversation_detail(conversation, conversation_row),
        "messages": [_serialize_message(message) for message in messages],
        "calls": [_serialize_call(call) for call in calls],
        "customerActions": [_serialize_customer_action_request(action) for action in customer_actions],
        "suggestedReply": _suggested_reply(messages, conversation.conversation_code),
    }


@router.get("/conversations/{conversation_id}/messages")
def api_conversation_messages(
    conversation_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, list[dict[str, Any]]]:
    require_admin(request, settings)
    if repository.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404)
    messages = repository.list_messages_for_conversation(conversation_id)
    return {"messages": [_serialize_message(message) for message in messages]}


@router.post("/conversations/{conversation_id}/proof-requests")
def api_create_proof_request(
    conversation_id: str,
    payload: ProofRequestCreate,
    request: Request,
    settings: Settings = Depends(get_settings),
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    require_admin(request, settings)
    try:
        result = service.create_proof_request(
            conversation_id=conversation_id,
            title=payload.title,
            operator_note=payload.operatorNote,
            proof_url=payload.proofUrl,
        )
    except CustomerActionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "proofRequest": _serialize_customer_action_request(result["request"]),
        "publicUrl": result["public_url"],
    }


@router.get("/proof/{public_token}")
def api_public_proof_request(
    public_token: str,
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    try:
        result = service.get_public_proof_request(public_token=public_token)
    except CustomerActionNotFound as exc:
        raise HTTPException(status_code=404) from exc
    return {"proofRequest": _serialize_public_customer_action(result)}


@router.post("/proof/{public_token}/approve")
def api_approve_public_proof_request(
    public_token: str,
    payload: ProofRequestApproval,
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    try:
        request_row = service.approve_proof_request(public_token=public_token, comment=payload.comment)
    except CustomerActionNotFound as exc:
        raise HTTPException(status_code=404) from exc
    except CustomerActionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"proofRequest": _serialize_customer_action_request(request_row)}


@router.post("/proof/{public_token}/changes")
def api_request_public_proof_changes(
    public_token: str,
    payload: ProofRequestChanges,
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    try:
        request_row = service.request_proof_changes(public_token=public_token, comment=payload.comment)
    except CustomerActionNotFound as exc:
        raise HTTPException(status_code=404) from exc
    except CustomerActionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CustomerActionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"proofRequest": _serialize_customer_action_request(request_row)}


@router.patch("/conversations/{conversation_id}")
def api_update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404)
    if payload.status is not None:
        conversation = repository.update_conversation_status(conversation_id, payload.status)
    return {"conversation": _serialize_conversation_detail(conversation, _conversation_metadata(repository, conversation))}


@router.post("/conversations/{conversation_id}/reply")
def api_send_conversation_reply(
    conversation_id: str,
    request: Request,
    body: str = Form(""),
    client_request_id: str = Form(""),
    reply_files: list[UploadFile] = File(default=[]),
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    sender: MessageSender = Depends(get_sender),
    attachment_store: AttachmentStore = Depends(get_attachment_store),
) -> dict[str, Any]:
    require_admin(request, settings)
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404)

    normalized_client_request_id = client_request_id.strip() or None
    if normalized_client_request_id:
        existing = repository.get_message_by_client_request_id(
            conversation_id=conversation.id,
            client_request_id=normalized_client_request_id,
        )
        if existing is not None:
            return {"status": "duplicate", "message": _serialize_message(existing)}

    reply_body = body.strip()
    uploads = read_uploads(reply_files)
    if not reply_body and not uploads:
        raise HTTPException(status_code=400, detail="Reply body or file is required.")

    stored_attachments = ()
    if uploads:
        stored_attachments = attachment_store.store_uploaded_attachments(
            object_prefix=f"api-replies/{conversation.id}",
            files=uploads,
        )

    outbound_body = reply_body_with_attachments(reply_body, stored_attachments)
    outbound_media_urls = image_attachment_urls(stored_attachments)
    outbound_sid = sender.send_message(
        to_phone=conversation.customer_phone,
        body=outbound_body,
        channel=conversation.customer_channel,
        media_urls=outbound_media_urls,
    )
    created_message = repository.create_message(
        conversation_id=conversation.id,
        direction="employee_to_customer",
        from_phone=settings.maya_business_number,
        to_phone=conversation.customer_phone,
        body=outbound_body,
        twilio_message_sid=outbound_sid,
        num_media=len(stored_attachments),
        media_urls=tuple(attachment.public_url for attachment in stored_attachments),
        media_content_types=tuple(attachment.content_type for attachment in stored_attachments),
        client_request_id=normalized_client_request_id,
    )
    for attachment in stored_attachments:
        repository.create_message_attachment(
            message_id=created_message["id"],
            bucket=attachment.bucket,
            object_path=attachment.object_path,
            public_url=attachment.public_url,
            source_url=attachment.source_url,
            content_type=attachment.content_type,
            size_bytes=None,
        )

    return {"status": "sent", "message": _serialize_message(created_message)}


@router.post("/conversations/{conversation_id}/call")
def api_call_conversation_customer(
    conversation_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    voice_caller: VoiceCaller = Depends(get_voice_caller),
) -> dict[str, str]:
    require_admin(request, settings)
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404)

    return _start_click_to_call(
        request=request,
        settings=settings,
        repository=repository,
        conversation=conversation,
        voice_caller=voice_caller,
        call_type="conversation_call",
    )


@router.get("/calls")
def api_calls(
    request: Request,
    q: str = "",
    direction: Literal["outgoing", "incoming", "all"] = "all",
    limit: int = 50,
    offset: int = 0,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    safe_limit = min(max(limit, 1), 100)
    safe_offset = max(offset, 0)
    storage_direction = {"outgoing": "outbound", "incoming": "inbound", "all": "all"}[direction]
    rows, has_more = repository.list_call_conversations(
        q=q,
        direction=storage_direction,
        limit=safe_limit,
        offset=safe_offset,
    )
    return {
        "calls": [_serialize_call_conversation(row) for row in rows],
        "pagination": {
            "limit": safe_limit,
            "offset": safe_offset,
            "nextOffset": safe_offset + safe_limit if has_more else None,
            "hasMore": has_more,
        },
    }


@router.post("/calls")
def api_start_new_call(
    payload: NewCallRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    voice_caller: VoiceCaller = Depends(get_voice_caller),
) -> dict[str, Any]:
    require_admin(request, settings)
    employee_phone = settings.francisco_phone_e164
    if not employee_phone:
        raise HTTPException(status_code=503, detail="FRANCISCO_PHONE is required for click-to-call.")

    customer_phone = _voice_phone_number(payload.phone_number)
    if not customer_phone:
        raise HTTPException(status_code=400, detail="Customer phone number is not callable.")
    if customer_phone == settings.maya_business_number_e164:
        raise HTTPException(status_code=400, detail="Customer phone number cannot be the Maya business number.")

    display_name = (payload.display_name or "").strip()
    if display_name:
        repository.upsert_contact_display_name(customer_phone, display_name)

    conversation = repository.get_or_create_customer_conversation(
        customer_phone=customer_phone,
        assigned_employee=employee_phone,
        customer_channel="sms",
    )
    call_response = _start_click_to_call(
        request=request,
        settings=settings,
        repository=repository,
        conversation=conversation,
        voice_caller=voice_caller,
        call_type="manual_outbound",
    )
    return {
        **call_response,
        "conversation": _serialize_conversation_detail(conversation, _conversation_metadata(repository, conversation)),
    }


@router.patch("/calls/{call_id}")
def api_update_call_details(
    call_id: str,
    payload: CallDetailsUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    call = repository.update_call_details(
        call_id=call_id,
        outcome=payload.outcome,
        follow_up_status=payload.follow_up_status,
        notes=_clean_optional_text(payload.notes),
        recap=_clean_optional_text(payload.recap),
        transcription=_clean_optional_text(payload.transcription),
    )
    if call is None:
        raise HTTPException(status_code=404)
    return {"call": _serialize_call(call)}


@router.get("/calls/{call_id}/recording")
def api_call_recording(
    call_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> Response:
    require_admin(request, settings)
    call = repository.get_call(call_id)
    if call is None:
        raise HTTPException(status_code=404)
    recording_url = call.get("recording_url")
    if not recording_url:
        raise HTTPException(status_code=404, detail="No recording is available for this call.")
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise HTTPException(status_code=503, detail="Twilio credentials are required to play recordings.")

    audio_response = _download_twilio_recording(settings, str(recording_url))
    return Response(
        content=audio_response.content,
        media_type=audio_response.headers.get("content-type") or "audio/mpeg",
    )


@router.post("/calls/{call_id}/transcribe")
def api_transcribe_call(
    call_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    if not settings.assemblyai_api_key:
        raise HTTPException(status_code=503, detail="ASSEMBLYAI_API_KEY is required for transcription.")

    call = repository.get_call(call_id)
    if call is None:
        raise HTTPException(status_code=404)
    recording_url = call.get("recording_url")
    if not recording_url:
        raise HTTPException(status_code=400, detail="No recording is available to transcribe.")

    audio_response = _download_twilio_recording(settings, str(recording_url))
    transcription = _transcribe_audio_with_assemblyai(settings, audio_response.content)
    updated_call = repository.update_call_transcription(call_id=call_id, transcription=transcription)
    if updated_call is None:
        raise HTTPException(status_code=404)
    return {"call": _serialize_call(updated_call)}


@router.post("/calls/{call_id}/recap")
def api_generate_call_recap(
    call_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is required to generate call recaps.")

    call = repository.get_call(call_id)
    if call is None:
        raise HTTPException(status_code=404)
    transcription = str(call.get("transcription") or "").strip()
    if not transcription:
        raise HTTPException(status_code=400, detail="Transcription is required before generating a recap.")

    recap = _generate_call_recap_with_openai(settings, call=call, transcription=transcription)
    updated_call = repository.update_call_recap(call_id=call_id, recap=recap)
    if updated_call is None:
        raise HTTPException(status_code=404)
    return {"call": _serialize_call(updated_call)}


def _start_click_to_call(
    *,
    request: Request,
    settings: Settings,
    repository: RelayRepository,
    conversation: Conversation,
    voice_caller: VoiceCaller,
    call_type: Literal["conversation_call", "manual_outbound"],
) -> dict[str, str]:
    employee_phone = settings.francisco_phone_e164
    customer_phone = _voice_phone_number(conversation.customer_phone)
    if not employee_phone:
        raise HTTPException(status_code=503, detail="FRANCISCO_PHONE is required for click-to-call.")
    if not settings.maya_business_number_e164:
        raise HTTPException(status_code=503, detail="MAYA_BUSINESS_NUMBER is required for click-to-call.")
    if not customer_phone:
        raise HTTPException(status_code=400, detail="Customer phone number is not callable.")

    recent_call = repository.get_recent_active_call(conversation_id=conversation.id)
    if recent_call is not None:
        raise HTTPException(status_code=409, detail="A call is already in progress for this conversation.")

    base_url = _public_base_url(request, settings)
    call_sid = voice_caller.start_click_to_call(
        employee_phone=employee_phone,
        bridge_url=f"{base_url}/webhooks/twilio/voice/bridge/{conversation.id}",
        status_callback_url=f"{base_url}/webhooks/twilio/voice/status",
    )
    try:
        repository.create_call(
            conversation_id=conversation.id,
            direction="outbound",
            call_type=call_type,
            customer_phone=customer_phone,
            employee_phone=employee_phone,
            twilio_call_sid=call_sid,
            status="initiated",
        )
    except Exception:
        logger.exception("Failed to persist outbound call log for conversation %s", conversation.id)

    return {
        "status": "calling",
        "callSid": call_sid,
        "to": customer_phone,
        "employeePhone": employee_phone,
    }


def _download_twilio_recording(settings: Settings, recording_url: str) -> requests.Response:
    media_url = _twilio_recording_media_url(recording_url)
    try:
        response = requests.get(
            media_url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Could not download Twilio recording.")
        raise HTTPException(status_code=502, detail="Could not download the Twilio recording.") from exc
    return response


def _twilio_recording_media_url(recording_url: str) -> str:
    cleaned = recording_url.strip()
    if cleaned.endswith(".mp3") or cleaned.endswith(".wav"):
        return cleaned
    if cleaned.endswith(".json"):
        return f"{cleaned[:-5]}.mp3"
    return f"{cleaned}.mp3"


def _transcribe_audio_with_assemblyai(settings: Settings, audio_content: bytes) -> str:
    headers = {"Authorization": settings.assemblyai_api_key}
    try:
        upload_response = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=audio_content,
            timeout=60,
        )
        upload_response.raise_for_status()
        upload_url = upload_response.json().get("upload_url")
        if not upload_url:
            raise HTTPException(status_code=502, detail="AssemblyAI did not return an upload URL.")

        transcript_response = requests.post(
            "https://api.assemblyai.com/v2/transcript",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "audio_url": upload_url,
                "speech_models": ["universal-3-pro", "universal-2"],
            },
            timeout=30,
        )
        transcript_response.raise_for_status()
        transcript_id = transcript_response.json().get("id")
        if not transcript_id:
            raise HTTPException(status_code=502, detail="AssemblyAI did not return a transcript ID.")

        poll_interval_seconds = max(settings.assemblyai_poll_interval_seconds, 1)
        deadline = time.monotonic() + max(settings.assemblyai_poll_timeout_seconds, poll_interval_seconds)
        while time.monotonic() < deadline:
            status_response = requests.get(
                f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                headers=headers,
                timeout=30,
            )
            status_response.raise_for_status()
            payload = status_response.json()
            status = payload.get("status")
            if status == "completed":
                return str(payload.get("text") or "").strip()
            if status == "error":
                raise HTTPException(status_code=502, detail=payload.get("error") or "AssemblyAI transcription failed.")
            time.sleep(poll_interval_seconds)
    except HTTPException:
        raise
    except requests.RequestException as exc:
        logger.exception("Could not transcribe call recording with AssemblyAI.")
        raise HTTPException(status_code=502, detail="Could not transcribe the call recording.") from exc

    raise HTTPException(status_code=504, detail="Transcription is still processing. Try again in a moment.")


def _generate_call_recap_with_openai(settings: Settings, *, call: dict[str, Any], transcription: str) -> str:
    prompt = (
        f"Call direction: {call.get('direction') or 'unknown'}\n"
        f"Customer phone: {call.get('customer_phone') or 'unknown'}\n"
        f"Outcome: {call.get('outcome') or 'not set'}\n"
        f"Follow-up status: {call.get('follow_up_status') or 'none'}\n"
        "\nTranscript:\n"
        f"{transcription[:12000]}"
    )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model,
                "instructions": (
                    "You summarize customer phone calls for Maya Graphics and Signs. "
                    "Write an internal recap for Francisco. Use 3 to 5 concise bullets. "
                    "Include the customer's request, any promised next step, missing details, "
                    "and urgency if it is clear. Do not invent prices, commitments, or timelines. "
                    "If the transcript is unclear or mostly silence, say that directly."
                ),
                "input": prompt,
                "max_output_tokens": 500,
                "reasoning": {"effort": "low"},
                "text": {"verbosity": "low"},
            },
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Could not generate call recap with OpenAI.")
        raise HTTPException(status_code=502, detail="Could not generate the call recap.") from exc

    recap = _extract_response_text(response.json())
    if not recap:
        raise HTTPException(status_code=502, detail="OpenAI did not return a call recap.")
    return recap.strip()


def _serialize_conversation_list_item(conversation: dict[str, Any]) -> dict[str, Any]:
    last_message = conversation.get("last_message") or {}
    return {
        "id": conversation["id"],
        "code": conversation.get("conversation_code"),
        "status": conversation.get("status"),
        "channel": conversation.get("customer_channel") or "sms",
        "customer": _serialize_customer(conversation),
        "lastMessage": _serialize_last_message(last_message),
        "updatedAt": conversation.get("updated_at"),
    }


def _serialize_conversation_detail(
    conversation: Conversation,
    conversation_row: dict[str, Any] | None,
) -> dict[str, Any]:
    source = conversation_row or {}
    return {
        "id": conversation.id,
        "code": conversation.conversation_code,
        "status": conversation.status,
        "channel": conversation.customer_channel,
        "customer": _serialize_customer(
            {
                "customer_phone": conversation.customer_phone,
                "customer_display_name": source.get("customer_display_name"),
                "customer_lookup_name": source.get("customer_lookup_name"),
                "customer_name": source.get("customer_name"),
            }
        ),
        "assignedEmployee": conversation.assigned_employee,
        "createdAt": source.get("created_at"),
        "updatedAt": source.get("updated_at"),
    }


def _serialize_customer(conversation: dict[str, Any]) -> dict[str, Any]:
    display_name = conversation.get("customer_display_name")
    lookup_name = conversation.get("customer_lookup_name")
    best_name = display_name or lookup_name or conversation.get("customer_name")
    return {
        "phone": conversation.get("customer_phone"),
        "displayName": display_name,
        "lookupName": lookup_name,
        "name": best_name,
    }


def _serialize_contact(contact: Any) -> dict[str, Any]:
    return {
        "id": contact.id,
        "phone": contact.phone_number,
        "displayName": contact.display_name,
        "lookupName": contact.lookup_name,
        "name": contact.best_name,
        "notes": contact.notes,
    }


def _serialize_contact_search_item(contact: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": contact.get("id"),
        "phone": contact.get("phone_number"),
        "displayName": contact.get("display_name"),
        "lookupName": contact.get("lookup_name"),
        "name": contact.get("name"),
        "notes": contact.get("notes"),
        "lastActivityAt": contact.get("last_activity_at"),
        "openConversationId": contact.get("open_conversation_id"),
        "lastConversationId": contact.get("last_conversation_id"),
        "latestCallId": contact.get("latest_call_id"),
    }


def _serialize_contact_import_error(error: Any) -> dict[str, Any]:
    return {
        "row": error.row,
        "code": error.code,
        "message": error.message,
    }


def _serialize_customer_action_request(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": request.get("id"),
        "conversationId": request.get("conversation_id"),
        "contactId": request.get("contact_id"),
        "type": request.get("request_type"),
        "status": request.get("status"),
        "title": request.get("title"),
        "operatorNote": request.get("operator_note"),
        "expiresAt": request.get("expires_at"),
        "completedAt": request.get("completed_at"),
        "canceledAt": request.get("canceled_at"),
        "createdBy": request.get("created_by"),
        "createdAt": request.get("created_at"),
        "updatedAt": request.get("updated_at"),
    }


def _serialize_public_customer_action(result: dict[str, Any]) -> dict[str, Any]:
    return {
        **_serialize_customer_action_request(result["request"]),
        "files": [_serialize_customer_action_file(file_row) for file_row in result["files"]],
        "events": [_serialize_customer_action_event(event) for event in result["events"]],
    }


def _serialize_customer_action_file(file_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": file_row.get("id"),
        "role": file_row.get("role"),
        "publicUrl": file_row.get("public_url"),
        "externalUrl": file_row.get("external_url"),
        "originalFilename": file_row.get("original_filename"),
        "contentType": file_row.get("content_type"),
        "sizeBytes": file_row.get("size_bytes"),
        "createdAt": file_row.get("created_at"),
    }


def _serialize_customer_action_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event.get("id"),
        "type": event.get("event_type"),
        "comment": event.get("comment"),
        "metadata": event.get("metadata") or {},
        "createdAt": event.get("created_at"),
    }


def _serialize_call_conversation(row: dict[str, Any]) -> dict[str, Any]:
    conversation = row.get("conversation") or {}
    latest_call = row.get("latest_call") or {}
    customer_source = {
        "customer_phone": row.get("customer_phone") or latest_call.get("customer_phone") or conversation.get("customer_phone"),
        "customer_display_name": row.get("customer_display_name"),
        "customer_lookup_name": row.get("customer_lookup_name"),
        "customer_name": row.get("customer_name"),
    }
    return {
        "id": row.get("id"),
        "conversation": _serialize_call_conversation_detail(conversation) if conversation else None,
        "customer": _serialize_customer(customer_source),
        "latestCall": _serialize_call(latest_call),
        "callCount": row.get("call_count") or 0,
        "workflowStatus": _call_workflow_status(latest_call),
    }


def _serialize_call_conversation_detail(conversation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": conversation.get("id"),
        "code": conversation.get("conversation_code"),
        "status": conversation.get("status"),
        "channel": conversation.get("customer_channel") or "sms",
        "assignedEmployee": conversation.get("assigned_employee"),
        "createdAt": conversation.get("created_at"),
        "updatedAt": conversation.get("updated_at"),
    }


def _call_workflow_status(call: dict[str, Any]) -> str:
    if not call.get("outcome") or call.get("follow_up_status") in {"needed", "scheduled"}:
        return "pending_follow_up"
    return "done"


def _serialize_last_message(message: dict[str, Any]) -> dict[str, Any] | None:
    if not message:
        return None
    return {
        "body": message.get("body"),
        "direction": message.get("direction"),
        "deliveryStatus": message.get("delivery_status") or "pending",
        "deliveryErrorCode": message.get("delivery_error_code"),
        "createdAt": message.get("created_at"),
        "hasAttachments": bool(message.get("num_media")),
    }


def _serialize_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("id"),
        "conversationId": message.get("conversation_id"),
        "direction": message.get("direction"),
        "body": message.get("body") or "",
        "fromPhone": message.get("from_phone"),
        "toPhone": message.get("to_phone"),
        "twilioMessageSid": message.get("twilio_message_sid"),
        "deliveryStatus": message.get("delivery_status") or "pending",
        "deliveryErrorCode": message.get("delivery_error_code"),
        "deliveryErrorMessage": message.get("delivery_error_message"),
        "clientRequestId": message.get("client_request_id"),
        "createdAt": message.get("created_at"),
        "attachments": _serialize_attachments(
            message.get("media_urls") or (),
            message.get("media_content_types") or (),
        ),
    }


def _serialize_call(call: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": call.get("id"),
        "conversationId": call.get("conversation_id"),
        "direction": call.get("direction"),
        "callType": call.get("call_type"),
        "customerPhone": call.get("customer_phone"),
        "employeePhone": call.get("employee_phone"),
        "twilioCallSid": call.get("twilio_call_sid"),
        "status": call.get("status"),
        "outcome": call.get("outcome"),
        "notes": call.get("notes"),
        "followUpStatus": call.get("follow_up_status") or "none",
        "recap": call.get("recap"),
        "transcription": call.get("transcription"),
        "recordingSid": call.get("recording_sid"),
        "recordingUrl": call.get("recording_url"),
        "recordingStatus": call.get("recording_status"),
        "recordingDurationSeconds": call.get("recording_duration_seconds"),
        "recordingChannels": call.get("recording_channels"),
        "startedAt": call.get("started_at"),
        "answeredAt": call.get("answered_at"),
        "completedAt": call.get("completed_at"),
        "createdAt": call.get("created_at"),
        "updatedAt": call.get("updated_at"),
    }


def _serialize_message_failure(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("id"),
        "conversationId": message.get("conversation_id"),
        "conversationCode": message.get("conversation_code"),
        "customerName": message.get("customer_name"),
        "customerPhone": message.get("to_phone") or message.get("from_phone"),
        "channel": _channel_from_message(message),
        "direction": message.get("direction"),
        "bodyPreview": _preview_text(str(message.get("body") or "")),
        "twilioMessageSid": message.get("twilio_message_sid"),
        "deliveryStatus": message.get("delivery_status"),
        "deliveryErrorCode": message.get("delivery_error_code"),
        "deliveryErrorMessage": message.get("delivery_error_message"),
        "createdAt": message.get("created_at"),
        "hint": _message_failure_hint(message),
    }


def _serialize_call_attention(item: dict[str, Any]) -> dict[str, Any]:
    call = item["call"]
    kind = item["kind"]
    return {
        "id": call.get("id"),
        "kind": kind,
        "conversationId": call.get("conversation_id"),
        "conversationCode": call.get("conversation_code"),
        "customerName": call.get("customer_name"),
        "customerPhone": call.get("customer_phone"),
        "direction": call.get("direction"),
        "callType": call.get("call_type"),
        "twilioCallSid": call.get("twilio_call_sid"),
        "status": call.get("status"),
        "recordingStatus": call.get("recording_status"),
        "recordingSid": call.get("recording_sid"),
        "startedAt": call.get("started_at"),
        "completedAt": call.get("completed_at"),
        "createdAt": call.get("created_at"),
        "hint": _call_attention_hint(kind),
    }


def _message_failure_hint(message: dict[str, Any]) -> str:
    error_code = str(message.get("delivery_error_code") or "").strip()
    if error_code == "30007":
        return "Carrier filtering. Check message wording, sender registration, and recent repeated sends."
    if error_code == "30034":
        return "Sender registration issue. Check A2P 10DLC/toll-free registration before retrying."
    if error_code in {"21610", "21614"}:
        return "Recipient cannot receive this message. Confirm opt-in and the phone number."
    if error_code:
        return f"Twilio returned error {error_code}. Open the message SID in Twilio logs for the exact cause."
    return "Twilio reported the send as failed or undelivered. Check the message SID and status callback details."


def _call_attention_hint(kind: str) -> str:
    if kind == "recording_failed":
        return "Twilio reported a recording problem. Check the recording callback payload and Twilio call logs."
    if kind == "recording_missing":
        return "The call completed but no recording is attached yet. Confirm recording callbacks and Studio recording settings."
    if kind == "transcription_missing":
        return "Recording is available but no transcription is saved. Check AssemblyAI configuration or run transcription."
    if kind == "recap_missing":
        return "Transcription is available but no recap is saved. Check OpenAI configuration or generate the recap."
    return "Review this call in Twilio logs and Maya Relay call details."


def _preview_text(value: str, max_length: int = 140) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[:max_length - 1].rstrip()}…"


def _channel_from_message(message: dict[str, Any]) -> str:
    return str(message.get("customer_channel") or ("whatsapp" if "whatsapp:" in str(message.get("to_phone") or "") else "sms"))


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _serialize_attachments(media_urls: tuple[str, ...] | list[str], content_types: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    attachments = []
    for index, url in enumerate(media_urls):
        content_type = content_types[index] if index < len(content_types) else "application/octet-stream"
        attachments.append(
            {
                "url": url,
                "contentType": content_type,
                "kind": "image" if content_type.lower().startswith("image/") else "file",
            }
        )
    return attachments


def _conversation_metadata(repository: RelayRepository, conversation: Conversation) -> dict[str, Any]:
    contact = repository.get_contact(conversation.customer_phone)
    customer_name = (contact.display_name or contact.lookup_name) if contact else None
    return {
        "customer_display_name": contact.display_name if contact else None,
        "customer_lookup_name": contact.lookup_name if contact else None,
        "customer_name": customer_name,
    }


def _conversation_metrics(conversations: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "open": sum(1 for conversation in conversations if conversation.get("status") == "open"),
        "failed": sum(
            1
            for conversation in conversations
            if ((conversation.get("last_message") or {}).get("delivery_status") in {"failed", "undelivered"})
        ),
        "recent": len(conversations),
        "withAttachments": sum(
            1 for conversation in conversations if ((conversation.get("last_message") or {}).get("num_media") or 0) > 0
        ),
    }


def _matches_filters(conversation: dict[str, Any], *, q: str, status: str, channel: str) -> bool:
    if status and conversation.get("status") != status:
        return False
    if channel and (conversation.get("customer_channel") or "sms") != channel:
        return False
    if not q.strip():
        return True
    needle = q.strip().lower()
    haystack = " ".join(
        str(value)
        for value in (
            conversation.get("conversation_code"),
            conversation.get("customer_phone"),
            conversation.get("customer_name"),
            conversation.get("customer_display_name"),
            conversation.get("customer_lookup_name"),
            conversation.get("customer_channel"),
            conversation.get("status"),
            conversation.get("message_search_text"),
        )
        if value
    ).lower()
    return needle in haystack


def _suggested_reply(messages: list[dict[str, Any]], conversation_code: str) -> str:
    prefix = f"#{conversation_code.upper()} "
    for message in reversed(messages):
        if message.get("direction") != "system":
            continue
        for line in reversed(str(message.get("body") or "").splitlines()):
            clean = line.strip()
            if clean.upper().startswith(prefix):
                return clean[len(prefix):].strip()
    return ""


def _public_base_url(request: Request, settings: Settings) -> str:
    if settings.app_base_url.strip():
        return settings.app_base_url.strip().rstrip("/")

    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}"

    return str(request.base_url).rstrip("/")


def _voice_phone_number(phone_number: str) -> str:
    prefix = "whatsapp:"
    if phone_number.lower().startswith(prefix):
        phone_number = phone_number[len(prefix):]
    return normalize_phone_number(phone_number)
