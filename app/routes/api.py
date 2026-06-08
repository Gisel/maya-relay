import hmac
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from app.attachments import AttachmentStore
from app.auth import SESSION_COOKIE, admin_enabled, require_admin, session_value
from app.config import Settings, get_settings, normalize_phone_number
from app.db import RelayRepository
from app.dependencies import get_attachment_store, get_repository, get_sender, get_voice_caller
from app.models import Conversation
from app.reply_helpers import image_attachment_urls, read_uploads, reply_body_with_attachments
from app.twilio_client import MessageSender, VoiceCaller


router = APIRouter(prefix="/api", tags=["api"])
logger = logging.getLogger(__name__)


class ConversationUpdate(BaseModel):
    status: Literal["open", "closed"] | None = None


class NewCallRequest(BaseModel):
    phone_number: str
    display_name: str | None = None


class CallDetailsUpdate(BaseModel):
    outcome: Literal["connected", "voicemail", "no_answer", "follow_up_needed", "wrong_number", "cancelled"] | None = None
    follow_up_status: Literal["none", "needed", "scheduled", "done"] = "none"
    notes: str | None = None
    recap: str | None = None
    transcription: str | None = None


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
) -> dict[str, list[dict[str, str]]]:
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
            },
            {
                "id": "proof_approval",
                "label": "Send standard proof approval request",
                "body": "Please review the proof and reply approved or send any changes needed.",
            },
            {
                "id": "shop_hours",
                "label": "Provide shop hours and pickup info",
                "body": f"We are open {settings.business_hours_text}",
            },
        ]
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
    return {
        "conversation": _serialize_conversation_detail(conversation, conversation_row),
        "messages": [_serialize_message(message) for message in messages],
        "calls": [_serialize_call(call) for call in calls],
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
        "startedAt": call.get("started_at"),
        "answeredAt": call.get("answered_at"),
        "completedAt": call.get("completed_at"),
        "createdAt": call.get("created_at"),
        "updatedAt": call.get("updated_at"),
    }


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
