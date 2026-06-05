import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from app.attachments import AttachmentStore
from app.auth import SESSION_COOKIE, admin_enabled, require_admin, session_value
from app.config import Settings, get_settings
from app.db import RelayRepository
from app.dependencies import get_attachment_store, get_repository, get_sender
from app.models import Conversation
from app.reply_helpers import image_attachment_urls, read_uploads, reply_body_with_attachments
from app.twilio_client import MessageSender


router = APIRouter(prefix="/api", tags=["api"])


class ConversationUpdate(BaseModel):
    status: Literal["open", "closed"] | None = None


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
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> dict[str, Any]:
    require_admin(request, settings)
    conversations = repository.list_conversations()
    filtered = [
        conversation
        for conversation in conversations
        if _matches_filters(conversation, q=q, status=status, channel=channel)
    ]
    return {
        "metrics": _conversation_metrics(conversations),
        "conversations": [_serialize_conversation_list_item(conversation) for conversation in filtered],
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

    conversation_row = _conversation_row(repository, conversation)
    messages = repository.list_messages_for_conversation(conversation_id)
    return {
        "conversation": _serialize_conversation_detail(conversation, conversation_row),
        "messages": [_serialize_message(message) for message in messages],
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
    return {"conversation": _serialize_conversation_detail(conversation, _conversation_row(repository, conversation))}


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


def _conversation_row(repository: RelayRepository, conversation: Conversation) -> dict[str, Any] | None:
    for row in repository.list_conversations():
        if row["id"] == conversation.id:
            return row
    return None


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
