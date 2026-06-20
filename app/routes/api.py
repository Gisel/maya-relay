import hmac
import logging
import mimetypes
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.ai_triage import MessageTriage, _extract_response_text
from app.attachments import AttachmentStore, StoredAttachment, UploadedAttachment
from app.auth import SESSION_COOKIE, admin_enabled, current_operator, operator_session_value, require_admin, session_value
from app.config import Settings, get_settings, normalize_phone_number
from app.customer_actions import CustomerActionFileInput
from app.db import RelayRepository
from app.dependencies import (
    get_attachment_store,
    get_customer_action_service,
    get_message_triage,
    get_operator_auth_service,
    get_repository,
    get_sender,
    get_voice_caller,
)
from app.models import Conversation
from app.operator_auth import OperatorAuthService
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

PROOF_MAX_FILE_SIZE_BYTES = 32 * 1024 * 1024
PROOF_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
ASSET_MAX_FILES = 8
ASSET_MAX_FILE_SIZE_BYTES = 32 * 1024 * 1024
ASSET_MAX_TOTAL_SIZE_BYTES = 100 * 1024 * 1024
ASSET_ALLOWED_CONTENT_TYPES = {
    "application/illustrator",
    "application/msword",
    "application/pdf",
    "application/postscript",
    "application/vnd.adobe.photoshop",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-photoshop",
    "application/zip",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/svg+xml",
    "image/tiff",
    "image/vnd.adobe.photoshop",
    "image/webp",
}
ASSET_ALLOWED_EXTENSIONS = {
    ".ai",
    ".doc",
    ".docx",
    ".eps",
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".psd",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
    ".zip",
}


class ConversationUpdate(BaseModel):
    status: Literal["open", "closed"] | None = None


class ContactUpdate(BaseModel):
    displayName: str | None = None
    notes: str | None = None


class NewCallRequest(BaseModel):
    phone_number: str
    display_name: str | None = None


class NewConversationRequest(BaseModel):
    phone_number: str
    display_name: str | None = None
    channel: Literal["sms", "whatsapp"] = "sms"
    body: str | None = None
    template_key: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    client_request_id: str | None = None


class CallDetailsUpdate(BaseModel):
    outcome: Literal["connected", "voicemail", "no_answer", "follow_up_needed", "wrong_number", "cancelled"] | None = None
    follow_up_status: Literal["none", "needed", "scheduled", "done"] = "none"
    notes: str | None = None
    recap: str | None = None
    transcription: str | None = None


class ProofRequestChanges(BaseModel):
    comment: str


class ProofRequestApproval(BaseModel):
    comment: str | None = None


class QuickResponseSendRequest(BaseModel):
    variables: dict[str, str] = Field(default_factory=dict)
    client_request_id: str | None = None


class LoginRequest(BaseModel):
    email: str | None = None
    password: str


@router.post("/auth/login")
def api_login(
    payload: LoginRequest,
    settings: Settings = Depends(get_settings),
    operator_auth: OperatorAuthService = Depends(get_operator_auth_service),
) -> JSONResponse:
    admin_enabled(settings)
    email = (payload.email or "").strip().lower()
    if email:
        operator = operator_auth.authenticate(email=email, password=payload.password)
        response = JSONResponse(
            {
                "authenticated": True,
                "user": _serialize_operator(operator),
            }
        )
        response.set_cookie(
            SESSION_COOKIE,
            operator_session_value(settings, operator),
            httponly=True,
            secure=True,
            samesite="lax",
        )
        return response

    if not settings.enable_admin_password_fallback or not settings.admin_password:
        raise HTTPException(status_code=401)
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
    operator = current_operator(request, settings)
    return {
        "authenticated": True,
        "session": {
            "cookieName": SESSION_COOKIE,
        },
        "user": _serialize_operator(operator) if operator else None,
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
        "operatorAuth": settings.operator_auth_configured,
        "authSessionSecret": bool(settings.auth_cookie_secret),
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
    return {"quickResponses": _quick_response_payloads(settings)}


def _quick_response_payloads(settings: Settings) -> list[dict[str, Any]]:
    return [_public_quick_response(response) for response in _quick_response_definitions(settings)]


def _serialize_operator(operator: Any) -> dict[str, Any]:
    return {
        "id": operator.id,
        "email": operator.email,
        "displayName": operator.display_name,
        "role": operator.role,
        "routingLine": operator.routing_line,
        "clickToCallPhone": operator.click_to_call_phone,
        "callRoutingReady": bool(operator.click_to_call_phone),
    }


def _quick_response_by_id(settings: Settings, quick_response_id: str) -> dict[str, Any] | None:
    return next(
        (response for response in _quick_response_definitions(settings) if response["id"] == quick_response_id),
        None,
    )


def _new_conversation_template(settings: Settings, template_key: str | None) -> dict[str, Any] | None:
    clean_template_key = (template_key or "").strip()
    if not clean_template_key:
        return None
    return next(
        (
            response
            for response in _quick_response_definitions(settings)
            if response.get("templateKey") == clean_template_key or response["id"] == clean_template_key
        ),
        None,
    )


def _quick_response_definitions(settings: Settings) -> list[dict[str, Any]]:
    hours = settings.business_hours_text.strip() or "M-F: 9:00am - 5:30pm | SAT: By Appointment"
    return [
        {
            "id": "missing_job_specs",
            "label": "Request missing job specs",
            "bodyTemplate": (
                "Thanks. Can you send the size, quantity, material/finish, artwork status, "
                "and when you need it?"
            ),
            "group": "quick_response",
            "channels": ["sms", "whatsapp"],
        },
        {
            "id": "shop_hours",
            "label": "Shop hours",
            "bodyTemplate": f"Maya hours\n{hours}",
            "group": "quick_response",
            "channels": ["sms", "whatsapp"],
        },
        {
            "id": "maya_owner_message",
            "label": "Custom WhatsApp message",
            "bodyTemplate": "Maya Graphics:\n{message}",
            "group": "template_response",
            "channels": ["whatsapp"],
            "templateKey": "owner_message",
            "variables": [
                {
                    "key": "message",
                    "label": "Message",
                    "placeholder": "Can you send the size, quantity, deadline, and artwork?",
                    "required": True,
                    "defaultValue": "",
                    "contentIndex": "1",
                }
            ],
        },
        {
            "id": "maya_new_customer_intro",
            "label": "New customer intro",
            "bodyTemplate": (
                "Thanks for contacting Maya Graphics. Tell us what you need printed, "
                "the size, quantity, deadline, and whether you already have artwork."
            ),
            "group": "template_response",
            "channels": ["sms", "whatsapp"],
            "templateKey": "new_customer_intro",
            "variables": [],
        },
        {
            "id": "maya_quote_follow_up",
            "label": "Quote follow-up",
            "bodyTemplate": (
                "Hi {customer_name}, following up on your quote request. "
                "Reply here with any questions or updates."
            ),
            "group": "template_response",
            "channels": ["sms", "whatsapp"],
            "templateKey": "quote_follow_up",
            "variables": [
                {
                    "key": "customer_name",
                    "label": "Customer name",
                    "placeholder": "Customer name",
                    "required": True,
                    "defaultValue": "there",
                    "defaultSource": "customer_name",
                    "contentIndex": "1",
                }
            ],
        },
        {
            "id": "maya_pickup_reminder",
            "label": "Pickup reminder",
            "bodyTemplate": "Your order for {order_name} is ready for pickup.",
            "group": "template_response",
            "channels": ["sms", "whatsapp"],
            "templateKey": "pickup_reminder",
            "variables": [
                {
                    "key": "order_name",
                    "label": "Order name",
                    "placeholder": "Business cards",
                    "required": True,
                    "defaultValue": "your order",
                    "contentIndex": "1",
                }
            ],
        },
        {
            "id": "maya_payment_reminder",
            "label": "Payment reminder",
            "bodyTemplate": (
                "Your order is ready. Please complete payment before pickup. "
                "Let us know if you need the payment link resent."
            ),
            "group": "template_response",
            "channels": ["sms", "whatsapp"],
            "templateKey": "payment_reminder",
            "variables": [],
        },
    ]


def _public_quick_response(response: dict[str, Any]) -> dict[str, Any]:
    public_response = dict(response)
    public_response["body"] = _render_quick_response_body(response, {})
    return public_response


def _quick_response_variables(response: dict[str, Any], submitted_variables: dict[str, str]) -> dict[str, str]:
    variables: dict[str, str] = {}
    for variable in response.get("variables", []):
        key = str(variable["key"])
        value = _clean_optional_text(submitted_variables.get(key))
        if not value:
            value = str(variable.get("defaultValue") or "")
        if variable.get("required") and not value:
            raise HTTPException(status_code=400, detail=f"{variable['label']} is required.")
        variables[key] = value
    return variables


def _render_quick_response_body(response: dict[str, Any], variables: dict[str, str]) -> str:
    body = str(response.get("bodyTemplate") or "")
    for variable in response.get("variables", []):
        key = str(variable["key"])
        value = variables.get(key) or str(variable.get("defaultValue") or "")
        body = body.replace("{" + key + "}", value)
    return body


def _quick_response_content_variables(response: dict[str, Any], variables: dict[str, str]) -> dict[str, str]:
    content_variables: dict[str, str] = {}
    for variable in response.get("variables", []):
        content_index = str(variable.get("contentIndex") or "")
        if content_index:
            key = str(variable["key"])
            content_variables[content_index] = variables.get(key) or str(variable.get("defaultValue") or "")
    return content_variables


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


@router.post("/conversations/{conversation_id}/suggested-reply")
def api_generate_suggested_reply(
    conversation_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    message_triage: MessageTriage = Depends(get_message_triage),
) -> dict[str, str]:
    require_admin(request, settings)
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404)

    messages = repository.list_messages_for_conversation(conversation_id)
    suggestion = _generate_live_suggested_reply(
        conversation=conversation,
        messages=messages,
        message_triage=message_triage,
    )
    return {"suggestedReply": suggestion or ""}


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


@router.post("/conversations/start")
def api_start_conversation(
    payload: NewConversationRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    sender: MessageSender = Depends(get_sender),
) -> dict[str, Any]:
    require_admin(request, settings)
    assigned_employee = settings.francisco_phone_e164
    if not assigned_employee:
        raise HTTPException(status_code=503, detail="FRANCISCO_PHONE is required to start a conversation.")

    customer_phone = normalize_phone_number(payload.phone_number.replace("whatsapp:", ""))
    if not customer_phone:
        raise HTTPException(status_code=400, detail="Customer phone number is required.")
    if customer_phone == settings.maya_business_number_e164:
        raise HTTPException(status_code=400, detail="Customer phone number cannot be the Maya business number.")

    display_name = (payload.display_name or "").strip()
    if display_name:
        repository.upsert_contact_display_name(customer_phone, display_name)

    conversation = repository.get_or_create_customer_conversation(
        customer_phone=customer_phone,
        assigned_employee=assigned_employee,
        customer_channel=payload.channel,
    )

    normalized_client_request_id = (payload.client_request_id or "").strip() or None
    if normalized_client_request_id:
        existing = repository.get_message_by_client_request_id(
            conversation_id=conversation.id,
            client_request_id=normalized_client_request_id,
        )
        if existing is not None:
            return {
                "status": "duplicate",
                "sendMode": "duplicate",
                "templateKey": None,
                "contentSid": None,
                "conversation": _serialize_conversation_detail(conversation, _conversation_metadata(repository, conversation)),
                "message": _serialize_message(existing),
            }

    quick_response = _new_conversation_template(settings, payload.template_key)
    if payload.template_key and quick_response is None:
        raise HTTPException(status_code=404, detail="Conversation starter template not found.")

    if payload.channel == "whatsapp":
        if quick_response is None:
            raise HTTPException(
                status_code=400,
                detail="Starting a WhatsApp conversation requires an approved template.",
            )
        variables = _quick_response_variables(quick_response, payload.variables)
        body = _render_quick_response_body(quick_response, variables)
        content_sid = _quick_response_template_content_sid(settings, str(quick_response["templateKey"]))
        try:
            outbound_sid = sender.send_template_message(
                to_phone=customer_phone,
                channel="whatsapp",
                content_sid=content_sid,
                content_variables=_quick_response_content_variables(quick_response, variables),
            )
        except Exception as exc:
            logger.exception("Could not start WhatsApp conversation with %s.", customer_phone)
            raise HTTPException(status_code=502, detail="Could not send the WhatsApp conversation starter.") from exc
        send_mode = "template"
        template_key = str(quick_response["templateKey"])
    else:
        if quick_response is not None:
            variables = _quick_response_variables(quick_response, payload.variables)
            body = _render_quick_response_body(quick_response, variables)
            template_key = str(quick_response.get("templateKey") or quick_response["id"])
        else:
            body = (payload.body or "").strip()
            template_key = None
        if not body:
            raise HTTPException(status_code=400, detail="Message body is required to start an SMS conversation.")
        try:
            outbound_sid = sender.send_message(to_phone=customer_phone, body=body, channel="sms")
        except Exception as exc:
            logger.exception("Could not start SMS conversation with %s.", customer_phone)
            raise HTTPException(status_code=502, detail="Could not send the SMS conversation starter.") from exc
        send_mode = "free_form"
        content_sid = None

    created_message = repository.create_message(
        conversation_id=conversation.id,
        direction="employee_to_customer",
        from_phone=settings.maya_business_number,
        to_phone=customer_phone,
        body=body,
        twilio_message_sid=outbound_sid,
        client_request_id=normalized_client_request_id,
    )
    conversation = repository.get_conversation(conversation.id) or conversation
    return {
        "status": "sent",
        "sendMode": send_mode,
        "templateKey": template_key,
        "contentSid": content_sid,
        "conversation": _serialize_conversation_detail(conversation, _conversation_metadata(repository, conversation)),
        "message": _serialize_message(created_message),
    }


@router.post("/conversations/{conversation_id}/proof-requests")
def api_create_proof_request(
    conversation_id: str,
    request: Request,
    title: str = Form(""),
    operator_note: str = Form(""),
    customer_message: str = Form(""),
    proof_file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    sender: MessageSender = Depends(get_sender),
    attachment_store: AttachmentStore = Depends(get_attachment_store),
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    require_admin(request, settings)
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404)
    public_base_url = _public_base_url(request, settings)
    if _is_local_base_url(public_base_url):
        raise HTTPException(
            status_code=503,
            detail="APP_BASE_URL must be set to the public Maya Relay URL before sending proof links.",
        )
    uploads = read_uploads([proof_file])
    if not uploads:
        raise HTTPException(status_code=400, detail="Proof file is required.")
    proof_upload = _validated_proof_upload(uploads[0])
    try:
        stored_files = attachment_store.store_uploaded_attachments(
            object_prefix=f"proof-requests/{conversation.id}",
            files=(proof_upload,),
        )
    except Exception as exc:
        logger.exception("Could not store proof file for conversation %s.", conversation.id)
        raise HTTPException(status_code=502, detail="Could not store proof file.") from exc
    if not stored_files:
        raise HTTPException(status_code=400, detail="Proof file is required.")

    stored_proof = stored_files[0]
    proof_file_input = CustomerActionFileInput(
        role="proof",
        bucket=stored_proof.bucket,
        object_path=stored_proof.object_path,
        public_url=stored_proof.public_url,
        original_filename=proof_upload.filename,
        content_type=stored_proof.content_type,
        size_bytes=len(proof_upload.content),
    )
    try:
        result = service.create_proof_request(
            conversation_id=conversation_id,
            title=title,
            operator_note=operator_note,
            proof_file=proof_file_input,
            public_base_url=public_base_url,
        )
    except CustomerActionValidationError as exc:
        attachment_store.delete_uploaded_attachments(stored_files)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        attachment_store.delete_uploaded_attachments(stored_files)
        logger.exception("Could not create proof request for conversation %s.", conversation.id)
        raise HTTPException(status_code=502, detail="Proof file was uploaded, but the request could not be created.") from exc

    message_body = _proof_request_message_body(
        public_url=result["public_url"],
        customer_message=customer_message,
    )
    try:
        send_result = _send_customer_action_request_message(
            sender=sender,
            settings=settings,
            conversation=conversation,
            body=message_body,
            public_url=result["public_url"],
            template_kind="proof_ready",
            title=(result["request"].get("title") or "Proof approval"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not send proof request %s.", result["request"].get("id"))
        raise HTTPException(
            status_code=502,
            detail="Proof request was created, but the customer message could not be sent.",
        ) from exc

    created_message = repository.create_message(
        conversation_id=conversation.id,
        direction="employee_to_customer",
        from_phone=settings.maya_business_number,
        to_phone=conversation.customer_phone,
        body=send_result["body"],
        twilio_message_sid=send_result["sid"],
    )
    repository.create_customer_action_event(
        request_id=result["request"]["id"],
        conversation_id=conversation.id,
        event_type="sent",
        comment=None,
        metadata={
            "message_id": created_message["id"],
            "twilio_message_sid": send_result["sid"],
            "channel": _effective_customer_channel(conversation.customer_channel, conversation.customer_phone),
            **send_result["metadata"],
        },
    )
    return {
        "proofRequest": _serialize_customer_action_request(result["request"]),
        "publicUrl": result["public_url"],
        "message": _serialize_message(created_message),
    }


@router.post("/conversations/{conversation_id}/asset-requests")
def api_create_asset_request(
    conversation_id: str,
    request: Request,
    title: str = Form(""),
    operator_note: str = Form(""),
    customer_message: str = Form(""),
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    sender: MessageSender = Depends(get_sender),
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    require_admin(request, settings)
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404)
    public_base_url = _public_base_url(request, settings)
    if _is_local_base_url(public_base_url):
        raise HTTPException(
            status_code=503,
            detail="APP_BASE_URL must be set to the public Maya Relay URL before sending asset links.",
        )
    try:
        result = service.create_assets_request(
            conversation_id=conversation_id,
            title=title,
            operator_note=operator_note,
            public_base_url=public_base_url,
        )
    except CustomerActionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    message_body = _asset_request_message_body(
        public_url=result["public_url"],
        customer_message=customer_message,
    )
    try:
        send_result = _send_customer_action_request_message(
            sender=sender,
            settings=settings,
            conversation=conversation,
            body=message_body,
            public_url=result["public_url"],
            template_kind="assets_needed",
            title=(result["request"].get("title") or "Asset upload"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not send asset request %s.", result["request"].get("id"))
        raise HTTPException(
            status_code=502,
            detail="Asset request was created, but the customer message could not be sent.",
        ) from exc

    created_message = repository.create_message(
        conversation_id=conversation.id,
        direction="employee_to_customer",
        from_phone=settings.maya_business_number,
        to_phone=conversation.customer_phone,
        body=send_result["body"],
        twilio_message_sid=send_result["sid"],
    )
    repository.create_customer_action_event(
        request_id=result["request"]["id"],
        conversation_id=conversation.id,
        event_type="sent",
        comment=None,
        metadata={
            "message_id": created_message["id"],
            "twilio_message_sid": send_result["sid"],
            "channel": _effective_customer_channel(conversation.customer_channel, conversation.customer_phone),
            **send_result["metadata"],
        },
    )
    return {
        "assetRequest": _serialize_customer_action_request(result["request"]),
        "publicUrl": result["public_url"],
        "message": _serialize_message(created_message),
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


@router.get("/assets/{public_token}")
def api_public_assets_request(
    public_token: str,
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    try:
        result = service.get_public_assets_request(public_token=public_token)
    except CustomerActionNotFound as exc:
        raise HTTPException(status_code=404) from exc
    return {"assetRequest": _serialize_public_customer_action(result)}


@router.post("/customer-actions/{request_id}/cancel")
def api_cancel_customer_action_request(
    request_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    require_admin(request, settings)
    try:
        request_row = service.cancel_request(request_id=request_id)
    except CustomerActionNotFound as exc:
        raise HTTPException(status_code=404) from exc
    except CustomerActionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"customerAction": _serialize_customer_action_request(request_row)}


@router.post("/assets/{public_token}/submit")
def api_submit_public_assets(
    public_token: str,
    note: str = Form(""),
    asset_files: list[UploadFile] = File(default=[]),
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    attachment_store: AttachmentStore = Depends(get_attachment_store),
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    try:
        existing = service.get_public_assets_request(public_token=public_token)["request"]
    except CustomerActionNotFound as exc:
        raise HTTPException(status_code=404) from exc

    uploads = _validated_asset_uploads(read_uploads(asset_files))
    try:
        stored_files = attachment_store.store_uploaded_attachments(
            object_prefix=f"customer-assets/{existing['id']}",
            files=uploads,
        )
    except Exception as exc:
        logger.exception("Could not store asset files for request %s.", existing["id"])
        raise HTTPException(status_code=502, detail="Could not store uploaded assets.") from exc

    file_inputs = tuple(
        CustomerActionFileInput(
            role="customer_asset",
            bucket=stored_file.bucket,
            object_path=stored_file.object_path,
            public_url=stored_file.public_url,
            original_filename=upload.filename,
            content_type=stored_file.content_type,
            size_bytes=len(upload.content),
        )
        for stored_file, upload in zip(stored_files, uploads, strict=True)
    )
    try:
        request_row = service.submit_assets(public_token=public_token, files=file_inputs, comment=note)
    except CustomerActionNotFound as exc:
        attachment_store.delete_uploaded_attachments(stored_files)
        raise HTTPException(status_code=404) from exc
    except CustomerActionValidationError as exc:
        attachment_store.delete_uploaded_attachments(stored_files)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CustomerActionStateError as exc:
        attachment_store.delete_uploaded_attachments(stored_files)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        attachment_store.delete_uploaded_attachments(stored_files)
        logger.exception("Could not submit asset request %s.", existing["id"])
        raise HTTPException(status_code=502, detail="Assets were uploaded, but the request could not be submitted.") from exc

    _record_customer_action_message(
        repository=repository,
        settings=settings,
        request_row=request_row,
        body=_assets_submitted_message(file_count=len(stored_files), note=note),
        attachments=stored_files,
    )
    result = service.get_public_assets_request(public_token=public_token)
    return {"assetRequest": _serialize_public_customer_action(result)}


@router.post("/proof/{public_token}/approve")
def api_approve_public_proof_request(
    public_token: str,
    payload: ProofRequestApproval,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    try:
        existing = service.get_public_proof_request(public_token=public_token)["request"]
        previous_status = existing["status"]
        request_row = service.approve_proof_request(public_token=public_token, comment=payload.comment)
    except CustomerActionNotFound as exc:
        raise HTTPException(status_code=404) from exc
    except CustomerActionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if previous_status == "pending":
        _record_customer_action_message(
            repository=repository,
            settings=settings,
            request_row=request_row,
            body=_proof_approved_message(payload.comment),
        )
    return {"proofRequest": _serialize_customer_action_request(request_row)}


@router.post("/proof/{public_token}/changes")
def api_request_public_proof_changes(
    public_token: str,
    payload: ProofRequestChanges,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    service: CustomerActionService = Depends(get_customer_action_service),
) -> dict[str, Any]:
    try:
        existing = service.get_public_proof_request(public_token=public_token)["request"]
        previous_status = existing["status"]
        request_row = service.request_proof_changes(public_token=public_token, comment=payload.comment)
    except CustomerActionNotFound as exc:
        raise HTTPException(status_code=404) from exc
    except CustomerActionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CustomerActionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if previous_status == "pending":
        _record_customer_action_message(
            repository=repository,
            settings=settings,
            request_row=request_row,
            body=_proof_changes_message(payload.comment),
        )
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


@router.post("/conversations/{conversation_id}/quick-responses/{quick_response_id}/send")
def api_send_quick_response(
    conversation_id: str,
    quick_response_id: str,
    payload: QuickResponseSendRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
    sender: MessageSender = Depends(get_sender),
) -> dict[str, Any]:
    require_admin(request, settings)
    conversation = repository.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404)

    quick_response = _quick_response_by_id(settings, quick_response_id)
    if quick_response is None:
        raise HTTPException(status_code=404, detail="Quick response not found.")

    normalized_client_request_id = (payload.client_request_id or "").strip() or None
    if normalized_client_request_id:
        existing = repository.get_message_by_client_request_id(
            conversation_id=conversation.id,
            client_request_id=normalized_client_request_id,
        )
        if existing is not None:
            return {"status": "duplicate", "message": _serialize_message(existing)}

    channel = _effective_customer_channel(conversation.customer_channel, conversation.customer_phone)
    variables = _quick_response_variables(quick_response, payload.variables)
    body = _render_quick_response_body(quick_response, variables)
    template_key = quick_response.get("templateKey")
    use_template = bool(template_key) and channel == "whatsapp" and not _has_active_whatsapp_window(repository, conversation.id)

    if use_template:
        content_sid = _quick_response_template_content_sid(settings, str(template_key))
        outbound_sid = sender.send_template_message(
            to_phone=conversation.customer_phone,
            channel="whatsapp",
            content_sid=content_sid,
            content_variables=_quick_response_content_variables(quick_response, variables),
        )
        send_mode = "template"
    else:
        outbound_sid = sender.send_message(
            to_phone=conversation.customer_phone,
            body=body,
            channel=channel,
        )
        content_sid = None
        send_mode = "free_form"

    created_message = repository.create_message(
        conversation_id=conversation.id,
        direction="employee_to_customer",
        from_phone=settings.maya_business_number,
        to_phone=conversation.customer_phone,
        body=body,
        twilio_message_sid=outbound_sid,
        client_request_id=normalized_client_request_id,
    )
    return {
        "status": "sent",
        "sendMode": send_mode,
        "templateKey": template_key if use_template else None,
        "contentSid": content_sid,
        "message": _serialize_message(created_message),
    }


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
        employee_phone=_resolve_click_to_call_employee_phone(request, settings),
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
    employee_phone = _resolve_click_to_call_employee_phone(request, settings)

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
        employee_phone=employee_phone,
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
    employee_phone: str,
) -> dict[str, str]:
    customer_phone = _voice_phone_number(conversation.customer_phone)
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


def _resolve_click_to_call_employee_phone(request: Request, settings: Settings) -> str:
    operator = current_operator(request, settings)
    if operator is not None:
        employee_phone = _voice_phone_number(operator.click_to_call_phone)
        if not employee_phone:
            raise HTTPException(status_code=503, detail="Logged-in operator does not have a call phone configured.")
        return employee_phone

    employee_phone = settings.francisco_phone_e164
    if not employee_phone:
        raise HTTPException(status_code=503, detail="FRANCISCO_PHONE is required for click-to-call.")
    return employee_phone


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
        "channel": _effective_customer_channel(conversation.get("customer_channel"), conversation.get("customer_phone")),
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
        "channel": _effective_customer_channel(conversation.customer_channel, conversation.customer_phone),
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


def _proof_request_message_body(*, public_url: str, customer_message: str | None) -> str:
    base = f"Your proof is ready. Review here: {public_url}"
    note = _clean_optional_text(customer_message)
    if not note:
        return base
    return f"{note}\n\n{base}"


def _asset_request_message_body(*, public_url: str, customer_message: str | None) -> str:
    base = f"Please upload your files here: {public_url}"
    note = _clean_optional_text(customer_message)
    if not note:
        return base
    return f"{note}\n\n{base}"


def _send_customer_action_request_message(
    *,
    sender: MessageSender,
    settings: Settings,
    conversation: Conversation,
    body: str,
    public_url: str,
    template_kind: Literal["proof_ready", "assets_needed"],
    title: str,
) -> dict[str, Any]:
    channel = _effective_customer_channel(conversation.customer_channel, conversation.customer_phone)
    if channel != "whatsapp":
        sid = sender.send_message(
            to_phone=conversation.customer_phone,
            body=body,
            channel=channel,
        )
        return {"sid": sid, "body": body, "metadata": {"send_mode": "free_form"}}

    content_sid = _customer_action_template_content_sid(settings, template_kind)
    token = _public_action_token(public_url)
    template_title = _clean_template_value(title)
    sid = sender.send_template_message(
        to_phone=conversation.customer_phone,
        channel=channel,
        content_sid=content_sid,
        content_variables={
            "1": template_title,
            "2": token,
        },
    )
    return {
        "sid": sid,
        "body": _customer_action_template_timeline_body(
            template_kind=template_kind,
            title=template_title,
            public_url=public_url,
        ),
        "metadata": {
            "send_mode": "template",
            "template_key": template_kind,
            "content_sid": content_sid,
            "content_variables": {"1": template_title, "2": token},
        },
    }


def _customer_action_template_content_sid(settings: Settings, template_kind: str) -> str:
    if template_kind == "proof_ready":
        content_sid = settings.whatsapp_template_proof_ready_content_sid.strip()
        template_label = "WHATSAPP_TEMPLATE_PROOF_READY_CONTENT_SID"
    elif template_kind == "assets_needed":
        content_sid = settings.whatsapp_template_assets_needed_content_sid.strip()
        template_label = "WHATSAPP_TEMPLATE_ASSETS_NEEDED_CONTENT_SID"
    else:
        content_sid = ""
        template_label = "WhatsApp template Content SID"
    if content_sid:
        return content_sid
    raise HTTPException(
        status_code=503,
        detail=f"{template_label} must be configured before sending this WhatsApp request.",
    )


def _quick_response_template_content_sid(settings: Settings, template_key: str) -> str:
    template_config = {
        "new_customer_intro": (
            settings.whatsapp_template_new_customer_intro_content_sid.strip(),
            "WHATSAPP_TEMPLATE_NEW_CUSTOMER_INTRO_CONTENT_SID",
        ),
        "quote_follow_up": (
            settings.whatsapp_template_quote_follow_up_content_sid.strip(),
            "WHATSAPP_TEMPLATE_QUOTE_FOLLOW_UP_CONTENT_SID",
        ),
        "pickup_reminder": (
            settings.whatsapp_template_pickup_reminder_content_sid.strip(),
            "WHATSAPP_TEMPLATE_PICKUP_REMINDER_CONTENT_SID",
        ),
        "payment_reminder": (
            settings.whatsapp_template_payment_reminder_content_sid.strip(),
            "WHATSAPP_TEMPLATE_PAYMENT_REMINDER_CONTENT_SID",
        ),
        "owner_message": (
            settings.whatsapp_template_owner_message_content_sid.strip(),
            "WHATSAPP_TEMPLATE_OWNER_MESSAGE_CONTENT_SID",
        ),
    }
    content_sid, template_label = template_config.get(template_key, ("", "WhatsApp quick response template Content SID"))
    if content_sid:
        return content_sid
    raise HTTPException(
        status_code=503,
        detail=f"{template_label} must be configured before sending this WhatsApp quick response.",
    )


def _public_action_token(public_url: str) -> str:
    parsed = urlparse(public_url)
    path = parsed.path.rstrip("/")
    token = path.rsplit("/", 1)[-1] if path else ""
    return token or public_url.rstrip("/").rsplit("/", 1)[-1]


def _clean_template_value(value: str) -> str:
    cleaned = _clean_optional_text(value)
    return cleaned or "your order"


def _has_active_whatsapp_window(repository: RelayRepository, conversation_id: str) -> bool:
    latest_inbound = next(
        (
            message
            for message in reversed(repository.list_messages_for_conversation(conversation_id, limit=100))
            if message.get("direction") == "customer_to_employee"
        ),
        None,
    )
    if latest_inbound is None:
        return False

    created_at = _parse_iso_datetime(str(latest_inbound.get("created_at") or ""))
    if created_at is None:
        return False
    return datetime.now(UTC) - created_at < timedelta(hours=24)


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _customer_action_template_timeline_body(
    *,
    template_kind: Literal["proof_ready", "assets_needed"],
    title: str,
    public_url: str,
) -> str:
    if template_kind == "assets_needed":
        return (
            f"We need your files for {title}. Please upload them using the secure Maya Graphics link below.\n\n"
            f"Upload files: {public_url}"
        )
    return (
        f"Your proof for {title} is ready. Please review it using the secure Maya Graphics link below.\n\n"
        f"Review proof: {public_url}"
    )


def _effective_customer_channel(channel: str | None, customer_phone: str | None) -> Literal["sms", "whatsapp"]:
    if str(customer_phone or "").lower().startswith("whatsapp:"):
        return "whatsapp"
    return "whatsapp" if channel == "whatsapp" else "sms"


def _record_customer_action_message(
    *,
    repository: RelayRepository,
    settings: Settings,
    request_row: dict[str, Any],
    body: str,
    attachments: tuple[StoredAttachment, ...] = (),
) -> None:
    conversation = repository.get_conversation(str(request_row["conversation_id"]))
    if conversation is None:
        logger.warning("Could not record customer action message for missing conversation %s.", request_row["conversation_id"])
        return
    message = repository.create_message(
        conversation_id=conversation.id,
        direction="system",
        from_phone=settings.maya_business_number,
        to_phone=conversation.assigned_employee,
        body=body,
        num_media=len(attachments),
        media_urls=tuple(attachment.public_url for attachment in attachments),
        media_content_types=tuple(attachment.content_type for attachment in attachments),
    )
    for attachment in attachments:
        repository.create_message_attachment(
            message_id=message["id"],
            bucket=attachment.bucket,
            object_path=attachment.object_path,
            public_url=attachment.public_url,
            source_url=attachment.source_url,
            content_type=attachment.content_type,
            size_bytes=None,
        )


def _proof_approved_message(comment: str | None) -> str:
    body = "Proof approved by customer."
    clean_comment = _clean_optional_text(comment)
    if clean_comment:
        return f"{body}\nComment: {clean_comment}"
    return body


def _proof_changes_message(comment: str) -> str:
    clean_comment = _clean_optional_text(comment)
    if clean_comment:
        return f"Proof changes requested by customer:\n{clean_comment}"
    return "Proof changes requested by customer."


def _assets_submitted_message(*, file_count: int, note: str | None) -> str:
    file_label = "file" if file_count == 1 else "files"
    body = f"Assets uploaded by customer: {file_count} {file_label}."
    clean_note = _clean_optional_text(note)
    if clean_note:
        return f"{body}\nNote: {clean_note}"
    return body


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


def _validated_proof_upload(upload: UploadedAttachment) -> UploadedAttachment:
    if len(upload.content) > PROOF_MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Proof file must be 32 MB or smaller.")
    content_type = _proof_content_type(upload)
    if content_type not in PROOF_ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Proof file must be a PDF or image file: PDF, JPG, PNG, GIF, WebP, or TIFF.",
        )
    if not _proof_content_matches_type(upload.content, content_type):
        raise HTTPException(status_code=400, detail="Proof file content does not match the selected file type.")
    return UploadedAttachment(filename=upload.filename, content=upload.content, content_type=content_type)


def _proof_content_type(upload: UploadedAttachment) -> str:
    content_type = upload.content_type.split(";")[0].strip().lower()
    if content_type and content_type != "application/octet-stream":
        return content_type
    guessed_type = mimetypes.guess_type(upload.filename)[0]
    return (guessed_type or content_type).split(";")[0].strip().lower()


def _proof_content_matches_type(content: bytes, content_type: str) -> bool:
    if content_type == "application/pdf":
        return content.startswith(b"%PDF")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if content_type == "image/tiff":
        return content.startswith((b"II*\x00", b"MM\x00*"))
    return False


def _validated_asset_uploads(uploads: tuple[UploadedAttachment, ...]) -> tuple[UploadedAttachment, ...]:
    if not uploads:
        raise HTTPException(status_code=400, detail="At least one asset file is required.")
    if len(uploads) > ASSET_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Upload {ASSET_MAX_FILES} files or fewer.")
    total_size = sum(len(upload.content) for upload in uploads)
    if total_size > ASSET_MAX_TOTAL_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Asset upload total must be 100 MB or smaller.")

    validated: list[UploadedAttachment] = []
    for upload in uploads:
        if len(upload.content) > ASSET_MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Each asset file must be 32 MB or smaller.")
        content_type = _asset_content_type(upload)
        extension = _filename_extension(upload.filename)
        if content_type not in ASSET_ALLOWED_CONTENT_TYPES and extension not in ASSET_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Asset files must be PDF, image, design, document, or ZIP files.",
            )
        validated.append(UploadedAttachment(filename=upload.filename, content=upload.content, content_type=content_type))
    return tuple(validated)


def _asset_content_type(upload: UploadedAttachment) -> str:
    content_type = upload.content_type.split(";")[0].strip().lower()
    if content_type and content_type != "application/octet-stream":
        return content_type
    guessed_type = mimetypes.guess_type(upload.filename)[0]
    return (guessed_type or content_type or "application/octet-stream").split(";")[0].strip().lower()


def _filename_extension(filename: str) -> str:
    name = filename.lower().strip().replace("\\", "/").split("/")[-1]
    if "." not in name:
        return ""
    return f".{name.rsplit('.', 1)[-1]}"


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


def _generate_live_suggested_reply(
    *,
    conversation: Conversation,
    messages: list[dict[str, Any]],
    message_triage: MessageTriage,
) -> str:
    latest_visible = next(
        (message for message in reversed(messages) if message.get("direction") in {"customer_to_employee", "employee_to_customer"}),
        None,
    )
    if latest_visible is None or latest_visible.get("direction") != "customer_to_employee":
        return ""

    recent_lines: list[str] = []
    for message in messages:
        body = str(message.get("body") or "").strip()
        if not body:
            continue
        direction = message.get("direction")
        if direction == "customer_to_employee":
            recent_lines.append(f"Customer: {body}")
        elif direction == "employee_to_customer":
            recent_lines.append(f"Maya: {body}")
    recent_context = "\n".join(recent_lines[-6:])
    has_attachments = bool(latest_visible.get("num_media") or latest_visible.get("media_urls"))
    triage_note = message_triage.summarize(
        body=recent_context or str(latest_visible.get("body") or ""),
        has_attachments=has_attachments,
        conversation_code=conversation.conversation_code,
    )
    suggested_reply = _suggested_reply_from_triage_note(triage_note, conversation.conversation_code)
    return _strip_conversation_code(suggested_reply, conversation.conversation_code)


def _suggested_reply_from_triage_note(triage_note: str | None, conversation_code: str) -> str:
    if not triage_note:
        return ""
    prefix = f"#{conversation_code.upper()} "
    for line in reversed(triage_note.splitlines()):
        clean = line.strip()
        if clean.upper().startswith(prefix):
            return clean
    return ""


def _strip_conversation_code(reply: str, conversation_code: str) -> str:
    prefix = f"#{conversation_code.upper()} "
    clean = reply.strip()
    if clean.upper().startswith(prefix):
        return clean[len(prefix):].strip()
    return clean


def _public_base_url(request: Request, settings: Settings) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        request_base_url = f"{forwarded_proto}://{forwarded_host}"
    else:
        request_base_url = str(request.base_url).rstrip("/")

    configured_base_url = settings.app_base_url.strip().rstrip("/")
    if configured_base_url and not _is_local_base_url(configured_base_url):
        return configured_base_url
    if request_base_url:
        return request_base_url

    return configured_base_url or "http://localhost:8000"


def _is_local_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0"}


def _voice_phone_number(phone_number: str) -> str:
    prefix = "whatsapp:"
    if phone_number.lower().startswith(prefix):
        phone_number = phone_number[len(prefix):]
    return normalize_phone_number(phone_number)
