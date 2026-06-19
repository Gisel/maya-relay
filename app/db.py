from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Any, Protocol

from supabase import Client, create_client

from app.config import Settings
from app.models import Channel, Contact, Conversation

CONTACT_COLUMNS = "id, phone_number, display_name, lookup_name, notes"
CONTACT_COLUMNS_WITH_CREATED_AT = f"{CONTACT_COLUMNS}, created_at"
CONTACT_COLUMNS_LEGACY = "id, phone_number, display_name, lookup_name"
CONTACT_COLUMNS_LEGACY_WITH_CREATED_AT = f"{CONTACT_COLUMNS_LEGACY}, created_at"


def _is_missing_contact_notes_column(error: Exception) -> bool:
    message = str(error).lower()
    return "42703" in message and "contacts" in message and "notes" in message


def _execute_contact_query_with_optional_notes(
    build_query,
    *,
    include_created_at: bool = False,
):
    columns = CONTACT_COLUMNS_WITH_CREATED_AT if include_created_at else CONTACT_COLUMNS
    legacy_columns = CONTACT_COLUMNS_LEGACY_WITH_CREATED_AT if include_created_at else CONTACT_COLUMNS_LEGACY
    try:
        return build_query(columns).execute()
    except Exception as error:
        if not _is_missing_contact_notes_column(error):
            raise
        return build_query(legacy_columns).execute()


def _conversation_from_row(row: dict[str, Any]) -> Conversation:
    conversation_code = row.get("conversation_code") or str(row["id"]).replace("-", "")[:8].upper()
    return Conversation(
        id=row["id"],
        customer_phone=row["customer_phone"],
        assigned_employee=row["assigned_employee"],
        status=row["status"],
        conversation_code=conversation_code,
        customer_channel=row.get("customer_channel") or "sms",
    )


def _contact_from_row(row: dict[str, Any]) -> Contact:
    return Contact(
        id=row["id"],
        phone_number=row["phone_number"],
        display_name=row.get("display_name"),
        lookup_name=row.get("lookup_name"),
        notes=row.get("notes"),
    )


def _new_conversation_code() -> str:
    return token_hex(4).upper()


class RelayRepository(Protocol):
    def get_contact(self, phone_number: str) -> Contact | None:
        ...

    def get_contact_by_id(self, contact_id: str) -> Contact | None:
        ...

    def get_or_create_contact(self, phone_number: str) -> Contact:
        ...

    def update_contact_lookup_name(self, phone_number: str, lookup_name: str | None) -> Contact:
        ...

    def upsert_contact_display_name(self, phone_number: str, display_name: str) -> Contact:
        ...

    def update_contact_profile(
        self,
        *,
        contact_id: str,
        display_name: str | None,
        notes: str | None,
    ) -> Contact | None:
        ...

    def search_contacts(
        self,
        *,
        q: str = "",
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        ...

    def import_contact_display_name(
        self,
        *,
        phone_number: str,
        display_name: str,
        overwrite: bool = False,
    ) -> tuple[Contact, str]:
        ...

    def get_or_create_customer_conversation(
        self,
        customer_phone: str,
        assigned_employee: str,
        customer_channel: Channel = "sms",
    ) -> Conversation:
        ...

    def get_latest_employee_conversation(self, employee_phone: str) -> Conversation | None:
        ...

    def get_open_conversation_by_code(self, conversation_code: str) -> Conversation | None:
        ...

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        ...

    def update_conversation_status(self, conversation_id: str, status: str) -> Conversation:
        ...

    def create_message(
        self,
        *,
        conversation_id: str,
        direction: str,
        from_phone: str,
        to_phone: str,
        body: str,
        twilio_message_sid: str | None = None,
        num_media: int = 0,
        media_urls: tuple[str, ...] = (),
        media_content_types: tuple[str, ...] = (),
        client_request_id: str | None = None,
    ) -> dict[str, Any]:
        ...

    def get_message_by_client_request_id(
        self,
        *,
        conversation_id: str,
        client_request_id: str,
    ) -> dict[str, Any] | None:
        ...

    def create_message_attachment(
        self,
        *,
        message_id: str,
        bucket: str,
        object_path: str,
        public_url: str,
        source_url: str,
        content_type: str,
        size_bytes: int | None = None,
    ) -> dict[str, Any]:
        ...

    def update_message_status(
        self,
        *,
        twilio_message_sid: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        ...

    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = "",
        channel: str = "",
    ) -> list[dict[str, Any]]:
        ...

    def list_messages_for_conversation(self, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        ...

    def list_calls_for_conversation(self, conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
        ...

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        ...

    def list_call_conversations(
        self,
        *,
        q: str = "",
        direction: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        ...

    def update_call_details(
        self,
        *,
        call_id: str,
        outcome: str | None,
        follow_up_status: str,
        notes: str | None,
        recap: str | None,
        transcription: str | None,
    ) -> dict[str, Any] | None:
        ...

    def update_call_transcription(
        self,
        *,
        call_id: str,
        transcription: str | None,
    ) -> dict[str, Any] | None:
        ...

    def update_call_recap(
        self,
        *,
        call_id: str,
        recap: str | None,
    ) -> dict[str, Any] | None:
        ...

    def get_recent_active_call(
        self,
        *,
        conversation_id: str,
        max_age_seconds: int = 30,
    ) -> dict[str, Any] | None:
        ...

    def create_call(
        self,
        *,
        conversation_id: str | None,
        direction: str,
        call_type: str,
        customer_phone: str,
        employee_phone: str | None,
        twilio_call_sid: str | None,
        status: str,
    ) -> dict[str, Any]:
        ...

    def update_call_status_by_sid(
        self,
        *,
        twilio_call_sid: str,
        status: str,
    ) -> dict[str, Any] | None:
        ...

    def update_call_recording_by_sid(
        self,
        *,
        twilio_call_sid: str,
        recording_sid: str | None,
        recording_url: str | None,
        recording_status: str | None,
        recording_duration_seconds: int | None,
        recording_channels: int | None,
    ) -> dict[str, Any] | None:
        ...

    def create_call_event(
        self,
        *,
        call_id: str | None,
        twilio_call_sid: str | None,
        event_type: str,
        call_status: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def get_operational_status(self, *, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
        ...

    def create_customer_action_request(
        self,
        *,
        conversation_id: str,
        contact_id: str | None,
        request_type: str,
        status: str,
        title: str | None,
        operator_note: str | None,
        public_token_hash: str,
        expires_at: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        ...

    def create_customer_action_file(
        self,
        *,
        request_id: str,
        role: str,
        bucket: str | None = None,
        object_path: str | None = None,
        public_url: str | None = None,
        external_url: str | None = None,
        original_filename: str | None = None,
        content_type: str | None = None,
        size_bytes: int | None = None,
    ) -> dict[str, Any]:
        ...

    def create_customer_action_event(
        self,
        *,
        request_id: str,
        conversation_id: str,
        event_type: str,
        comment: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    def get_customer_action_by_token_hash(self, public_token_hash: str) -> dict[str, Any] | None:
        ...

    def get_customer_action_request(self, request_id: str) -> dict[str, Any] | None:
        ...

    def list_customer_actions_for_conversation(self, conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
        ...

    def list_customer_action_files(self, request_id: str) -> list[dict[str, Any]]:
        ...

    def list_customer_action_events(self, request_id: str) -> list[dict[str, Any]]:
        ...

    def update_customer_action_request_status(
        self,
        *,
        request_id: str,
        status: str,
        completed_at: str | None = None,
        canceled_at: str | None = None,
    ) -> dict[str, Any] | None:
        ...


class SupabaseRelayRepository:
    def __init__(self, client: Client):
        self.client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> "SupabaseRelayRepository":
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
        return cls(create_client(settings.supabase_url, settings.supabase_service_role_key))

    def get_or_create_customer_conversation(
        self,
        customer_phone: str,
        assigned_employee: str,
        customer_channel: Channel = "sms",
    ) -> Conversation:
        self.get_or_create_contact(customer_phone)

        existing = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status, conversation_code, customer_channel")
            .eq("customer_phone", customer_phone)
            .eq("assigned_employee", assigned_employee)
            .eq("customer_channel", customer_channel)
            .eq("status", "open")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            return _conversation_from_row(row)

        created = (
            self.client.table("conversations")
            .insert(
                {
                    "customer_phone": customer_phone,
                    "assigned_employee": assigned_employee,
                    "customer_channel": customer_channel,
                    "status": "open",
                    "conversation_code": _new_conversation_code(),
                }
            )
            .execute()
        )
        return _conversation_from_row(created.data[0])

    def get_contact(self, phone_number: str) -> Contact | None:
        result = _execute_contact_query_with_optional_notes(
            lambda columns: (
                self.client.table("contacts")
                .select(columns)
                .eq("phone_number", phone_number)
                .limit(1)
            )
        )
        if not result.data:
            return None
        return _contact_from_row(result.data[0])

    def get_contact_by_id(self, contact_id: str) -> Contact | None:
        result = _execute_contact_query_with_optional_notes(
            lambda columns: (
                self.client.table("contacts")
                .select(columns)
                .eq("id", contact_id)
                .limit(1)
            )
        )
        if not result.data:
            return None
        return _contact_from_row(result.data[0])

    def get_or_create_contact(self, phone_number: str) -> Contact:
        existing = self.get_contact(phone_number)
        if existing is not None:
            return existing

        created = self.client.table("contacts").insert({"phone_number": phone_number}).execute()
        return _contact_from_row(created.data[0])

    def update_contact_lookup_name(self, phone_number: str, lookup_name: str | None) -> Contact:
        result = (
            self.client.table("contacts")
            .upsert(
                {
                    "phone_number": phone_number,
                    "lookup_name": lookup_name,
                    "lookup_checked_at": datetime.now(UTC).isoformat(),
                },
                on_conflict="phone_number",
            )
            .execute()
        )
        return _contact_from_row(result.data[0])

    def upsert_contact_display_name(self, phone_number: str, display_name: str) -> Contact:
        result = (
            self.client.table("contacts")
            .upsert(
                {
                    "phone_number": phone_number,
                    "display_name": display_name,
                },
                on_conflict="phone_number",
            )
            .execute()
        )
        return _contact_from_row(result.data[0])

    def update_contact_profile(
        self,
        *,
        contact_id: str,
        display_name: str | None,
        notes: str | None,
    ) -> Contact | None:
        payload = {
            "display_name": display_name,
            "notes": notes,
        }
        try:
            result = self.client.table("contacts").update(payload).eq("id", contact_id).execute()
        except Exception as error:
            if not _is_missing_contact_notes_column(error):
                raise
            result = self.client.table("contacts").update({"display_name": display_name}).eq("id", contact_id).execute()
        if not result.data:
            return None
        return _contact_from_row(result.data[0])

    def import_contact_display_name(
        self,
        *,
        phone_number: str,
        display_name: str,
        overwrite: bool = False,
    ) -> tuple[Contact, str]:
        existing = self.get_contact(phone_number)
        if existing is None:
            created = (
                self.client.table("contacts")
                .insert(
                    {
                        "phone_number": phone_number,
                        "display_name": display_name,
                    }
                )
                .execute()
            )
            return _contact_from_row(created.data[0]), "created"

        if existing.display_name and not overwrite:
            return existing, "skipped"

        if existing.display_name == display_name:
            return existing, "skipped"

        result = (
            self.client.table("contacts")
            .update({"display_name": display_name})
            .eq("phone_number", phone_number)
            .execute()
        )
        if not result.data:
            return existing, "skipped"
        return _contact_from_row(result.data[0]), "updated"

    def search_contacts(
        self,
        *,
        q: str = "",
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        safe_limit = max(limit, 1)
        safe_offset = max(offset, 0)
        search_limit = safe_limit + safe_offset + 1
        contact_scan_limit = max(search_limit * 5, 500 if q.strip() else search_limit)
        contacts = _execute_contact_query_with_optional_notes(
            lambda columns: (
                self.client.table("contacts")
                .select(columns)
                .order("created_at", desc=True)
                .limit(contact_scan_limit)
            ),
            include_created_at=True,
        ).data
        needle = q.strip().lower()
        if needle:
            contacts = [contact for contact in contacts if _contact_matches(contact, needle)]

        phones = sorted({contact["phone_number"] for contact in contacts})
        conversations_by_phone: dict[str, list[dict[str, Any]]] = {phone: [] for phone in phones}
        calls_by_phone: dict[str, list[dict[str, Any]]] = {phone: [] for phone in phones}

        if phones:
            conversations = (
                self.client.table("conversations")
                .select(
                    "id, customer_phone, assigned_employee, customer_channel, "
                    "conversation_code, status, created_at, updated_at"
                )
                .in_("customer_phone", phones)
                .order("updated_at", desc=True)
                .limit(max(len(phones) * 5, 1))
                .execute()
                .data
            )
            for conversation in conversations:
                conversations_by_phone.setdefault(conversation["customer_phone"], []).append(conversation)

            calls = (
                self.client.table("calls")
                .select("id, conversation_id, customer_phone, status, outcome, created_at, updated_at, started_at")
                .in_("customer_phone", phones)
                .order("created_at", desc=True)
                .limit(max(len(phones) * 5, 1))
                .execute()
                .data
            )
            for call in calls:
                calls_by_phone.setdefault(call["customer_phone"], []).append(call)

        rows = [
            _contact_search_row(
                contact,
                conversations_by_phone.get(contact["phone_number"], []),
                calls_by_phone.get(contact["phone_number"], []),
            )
            for contact in contacts
        ]
        rows.sort(key=lambda row: row.get("last_activity_at") or row.get("created_at") or "", reverse=True)
        page_rows = rows[safe_offset: safe_offset + safe_limit + 1]
        has_more = len(page_rows) > safe_limit
        return page_rows[:safe_limit], has_more

    def get_latest_employee_conversation(self, employee_phone: str) -> Conversation | None:
        result = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status, conversation_code, customer_channel")
            .eq("assigned_employee", employee_phone)
            .eq("status", "open")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return _conversation_from_row(result.data[0])

    def get_open_conversation_by_code(self, conversation_code: str) -> Conversation | None:
        result = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status, conversation_code, customer_channel")
            .eq("conversation_code", conversation_code.upper())
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return _conversation_from_row(result.data[0])

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        result = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status, conversation_code, customer_channel")
            .eq("id", conversation_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return _conversation_from_row(result.data[0])

    def update_conversation_status(self, conversation_id: str, status: str) -> Conversation:
        result = (
            self.client.table("conversations")
            .update({"status": status})
            .eq("id", conversation_id)
            .execute()
        )
        return _conversation_from_row(result.data[0])

    def create_message(
        self,
        *,
        conversation_id: str,
        direction: str,
        from_phone: str,
        to_phone: str,
        body: str,
        twilio_message_sid: str | None = None,
        num_media: int = 0,
        media_urls: tuple[str, ...] = (),
        media_content_types: tuple[str, ...] = (),
        client_request_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "conversation_id": conversation_id,
            "direction": direction,
            "from_phone": from_phone,
            "to_phone": to_phone,
            "body": body,
            "twilio_message_sid": twilio_message_sid,
            "num_media": num_media,
            "media_urls": list(media_urls),
            "media_content_types": list(media_content_types),
        }
        if client_request_id:
            payload["client_request_id"] = client_request_id

        result = (
            self.client.table("messages")
            .insert(payload)
            .execute()
        )
        self.client.table("conversations").update(
            {"updated_at": datetime.now(UTC).isoformat()}
        ).eq("id", conversation_id).execute()
        return result.data[0]

    def get_message_by_client_request_id(
        self,
        *,
        conversation_id: str,
        client_request_id: str,
    ) -> dict[str, Any] | None:
        result = (
            self.client.table("messages")
            .select(
                "id, conversation_id, direction, from_phone, to_phone, body, twilio_message_sid, "
                "num_media, media_urls, media_content_types, delivery_status, delivery_error_code, "
                "delivery_error_message, client_request_id, created_at"
            )
            .eq("conversation_id", conversation_id)
            .eq("client_request_id", client_request_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def create_message_attachment(
        self,
        *,
        message_id: str,
        bucket: str,
        object_path: str,
        public_url: str,
        source_url: str,
        content_type: str,
        size_bytes: int | None = None,
    ) -> dict[str, Any]:
        result = (
            self.client.table("message_attachments")
            .insert(
                {
                    "message_id": message_id,
                    "bucket": bucket,
                    "object_path": object_path,
                    "public_url": public_url,
                    "source_url": source_url,
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                }
            )
            .execute()
        )
        return result.data[0]

    def update_message_status(
        self,
        *,
        twilio_message_sid: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        (
            self.client.table("messages")
            .update(
                {
                    "delivery_status": status,
                    "delivery_error_code": error_code,
                    "delivery_error_message": error_message,
                }
            )
            .eq("twilio_message_sid", twilio_message_sid)
            .execute()
        )

    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = "",
        channel: str = "",
    ) -> list[dict[str, Any]]:
        query = (
            self.client.table("conversations")
            .select(
                "id, customer_phone, assigned_employee, customer_channel, "
                "conversation_code, status, created_at, updated_at"
            )
        )
        if status:
            query = query.eq("status", status)
        if channel:
            query = query.eq("customer_channel", channel)
        result = query.order("updated_at", desc=True).range(offset, offset + limit - 1).execute()
        if not result.data:
            return []

        conversation_ids = [conversation["id"] for conversation in result.data]
        customer_phones = sorted({conversation["customer_phone"] for conversation in result.data})
        messages = (
            self.client.table("messages")
            .select("conversation_id, body, direction, delivery_status, delivery_error_code, created_at, num_media")
            .in_("conversation_id", conversation_ids)
            .order("created_at", desc=True)
            .limit(limit * 50)
            .execute()
        )
        contacts = (
            self.client.table("contacts")
            .select("phone_number, display_name, lookup_name")
            .in_("phone_number", customer_phones)
            .execute()
        )

        messages_by_conversation: dict[str, list[dict[str, Any]]] = {conversation_id: [] for conversation_id in conversation_ids}
        for message in messages.data:
            conversation_messages = messages_by_conversation.get(message["conversation_id"])
            if conversation_messages is not None and len(conversation_messages) < 50:
                conversation_messages.append(message)

        contacts_by_phone = {contact["phone_number"]: contact for contact in contacts.data}
        conversations: list[dict[str, Any]] = []
        for conversation in result.data:
            conversation_messages = messages_by_conversation[conversation["id"]]
            last_message = _latest_customer_visible_message(conversation_messages)
            contact = contacts_by_phone.get(conversation["customer_phone"], {})
            conversations.append(
                {
                    **conversation,
                    "updated_at": _conversation_activity_at(conversation, last_message),
                    "customer_display_name": contact.get("display_name"),
                    "customer_lookup_name": contact.get("lookup_name"),
                    "customer_name": contact.get("display_name") or contact.get("lookup_name"),
                    "last_message": last_message,
                    "message_search_text": _message_search_text(conversation_messages),
                }
            )
        conversations.sort(key=lambda conversation: conversation.get("updated_at") or "", reverse=True)
        return conversations

    def list_messages_for_conversation(self, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        result = (
            self.client.table("messages")
            .select(
                "id, conversation_id, direction, from_phone, to_phone, body, twilio_message_sid, "
                "num_media, media_urls, media_content_types, delivery_status, delivery_error_code, "
                "delivery_error_message, client_request_id, created_at"
            )
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data

    def list_calls_for_conversation(self, conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
        result = (
            self.client.table("calls")
            .select(
                "id, conversation_id, direction, call_type, customer_phone, employee_phone, twilio_call_sid, "
                "status, outcome, notes, follow_up_status, recap, transcription, "
                "recording_sid, recording_url, recording_status, recording_duration_seconds, recording_channels, "
                "started_at, answered_at, completed_at, created_at, updated_at"
            )
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        result = (
            self.client.table("calls")
            .select(
                "id, conversation_id, direction, call_type, customer_phone, employee_phone, twilio_call_sid, "
                "status, outcome, notes, follow_up_status, recap, transcription, "
                "recording_sid, recording_url, recording_status, recording_duration_seconds, recording_channels, "
                "started_at, answered_at, completed_at, created_at, updated_at"
            )
            .eq("id", call_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def list_call_conversations(
        self,
        *,
        q: str = "",
        direction: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        query = self.client.table("calls").select(
            "id, conversation_id, direction, call_type, customer_phone, employee_phone, twilio_call_sid, "
            "status, outcome, notes, follow_up_status, recap, transcription, "
            "recording_sid, recording_url, recording_status, recording_duration_seconds, recording_channels, "
            "started_at, answered_at, completed_at, created_at, updated_at"
        )
        if direction in {"inbound", "outbound"}:
            query = query.eq("direction", direction)

        calls = query.order("created_at", desc=True).limit(max(limit + offset, 1) * 10).execute().data
        if not calls:
            return [], False

        conversation_ids = sorted({call["conversation_id"] for call in calls if call.get("conversation_id")})
        customer_phone_set = {call["customer_phone"] for call in calls if call.get("customer_phone")}
        conversations_by_id: dict[str, dict[str, Any]] = {}
        contacts_by_phone: dict[str, dict[str, Any]] = {}

        if conversation_ids:
            conversations = (
                self.client.table("conversations")
                .select(
                    "id, customer_phone, assigned_employee, customer_channel, "
                    "conversation_code, status, created_at, updated_at"
                )
                .in_("id", conversation_ids)
                .execute()
            )
            conversations_by_id = {conversation["id"]: conversation for conversation in conversations.data}
            customer_phone_set.update(conversation["customer_phone"] for conversation in conversations.data)

        customer_phones = sorted(customer_phone_set)
        if customer_phones:
            contacts = (
                self.client.table("contacts")
                .select("phone_number, display_name, lookup_name")
                .in_("phone_number", customer_phones)
                .execute()
            )
            contacts_by_phone = {contact["phone_number"]: contact for contact in contacts.data}

        grouped: dict[str, dict[str, Any]] = {}
        for call in calls:
            key = call.get("conversation_id") or f"phone:{call.get('customer_phone')}"
            if not key:
                continue
            conversation = conversations_by_id.get(call.get("conversation_id") or "")
            phone = (conversation or {}).get("customer_phone") or call.get("customer_phone")
            contact = contacts_by_phone.get(phone or "", {})
            row = grouped.setdefault(
                key,
                {
                    "id": key,
                    "conversation": conversation,
                    "customer_phone": phone,
                    "customer_display_name": contact.get("display_name"),
                    "customer_lookup_name": contact.get("lookup_name"),
                    "customer_name": contact.get("display_name") or contact.get("lookup_name"),
                    "latest_call": call,
                    "call_count": 0,
                },
            )
            row["call_count"] += 1
            if str(call.get("created_at") or "") > str((row["latest_call"] or {}).get("created_at") or ""):
                row["latest_call"] = call

        rows = list(grouped.values())
        rows.sort(key=lambda row: row.get("latest_call", {}).get("created_at") or "", reverse=True)
        needle = q.strip().lower()
        if needle:
            rows = [row for row in rows if _call_conversation_matches(row, needle)]

        page_rows = rows[offset: offset + limit + 1]
        has_more = len(page_rows) > limit
        return page_rows[:limit], has_more

    def update_call_details(
        self,
        *,
        call_id: str,
        outcome: str | None,
        follow_up_status: str,
        notes: str | None,
        recap: str | None,
        transcription: str | None,
    ) -> dict[str, Any] | None:
        result = (
            self.client.table("calls")
            .update(
                {
                    "outcome": outcome,
                    "follow_up_status": follow_up_status,
                    "notes": notes,
                    "recap": recap,
                    "transcription": transcription,
                }
            )
            .eq("id", call_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def update_call_transcription(
        self,
        *,
        call_id: str,
        transcription: str | None,
    ) -> dict[str, Any] | None:
        result = (
            self.client.table("calls")
            .update({"transcription": transcription})
            .eq("id", call_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def update_call_recap(
        self,
        *,
        call_id: str,
        recap: str | None,
    ) -> dict[str, Any] | None:
        result = (
            self.client.table("calls")
            .update({"recap": recap})
            .eq("id", call_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def get_recent_active_call(
        self,
        *,
        conversation_id: str,
        max_age_seconds: int = 30,
    ) -> dict[str, Any] | None:
        cutoff = (datetime.now(UTC) - timedelta(seconds=max_age_seconds)).isoformat()
        result = (
            self.client.table("calls")
            .select("id, conversation_id, status, twilio_call_sid, created_at")
            .eq("conversation_id", conversation_id)
            .in_("status", ["initiated", "ringing", "in-progress", "queued"])
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def create_call(
        self,
        *,
        conversation_id: str | None,
        direction: str,
        call_type: str,
        customer_phone: str,
        employee_phone: str | None,
        twilio_call_sid: str | None,
        status: str,
    ) -> dict[str, Any]:
        result = (
            self.client.table("calls")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "direction": direction,
                    "call_type": call_type,
                    "customer_phone": customer_phone,
                    "employee_phone": employee_phone,
                    "twilio_call_sid": twilio_call_sid,
                    "status": status,
                }
            )
            .execute()
        )
        return result.data[0]

    def update_call_status_by_sid(
        self,
        *,
        twilio_call_sid: str,
        status: str,
    ) -> dict[str, Any] | None:
        if not twilio_call_sid:
            return None

        timestamp_updates: dict[str, Any] = {}
        now = datetime.now(UTC).isoformat()
        if status in {"answered", "in-progress"}:
            timestamp_updates["answered_at"] = now
        if status == "completed":
            timestamp_updates["completed_at"] = now

        result = (
            self.client.table("calls")
            .update({"status": status, **timestamp_updates})
            .eq("twilio_call_sid", twilio_call_sid)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def update_call_recording_by_sid(
        self,
        *,
        twilio_call_sid: str,
        recording_sid: str | None,
        recording_url: str | None,
        recording_status: str | None,
        recording_duration_seconds: int | None,
        recording_channels: int | None,
    ) -> dict[str, Any] | None:
        if not twilio_call_sid:
            return None

        result = (
            self.client.table("calls")
            .update(
                {
                    "recording_sid": recording_sid,
                    "recording_url": recording_url,
                    "recording_status": recording_status,
                    "recording_duration_seconds": recording_duration_seconds,
                    "recording_channels": recording_channels,
                }
            )
            .eq("twilio_call_sid", twilio_call_sid)
            .execute()
        )
        if not result.data:
            return None
        call = result.data[0]
        if recording_status == "completed" and not call.get("outcome") and call.get("status") != "completed":
            result = (
                self.client.table("calls")
                .update({"outcome": "voicemail", "follow_up_status": "needed"})
                .eq("twilio_call_sid", twilio_call_sid)
                .execute()
            )
            if result.data:
                return result.data[0]
        return call

    def create_call_event(
        self,
        *,
        call_id: str | None,
        twilio_call_sid: str | None,
        event_type: str,
        call_status: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = (
            self.client.table("call_events")
            .insert(
                {
                    "call_id": call_id,
                    "twilio_call_sid": twilio_call_sid,
                    "event_type": event_type,
                    "call_status": call_status,
                    "payload": payload,
                }
            )
            .execute()
        )
        return result.data[0]

    def get_operational_status(self, *, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
        safe_limit = min(max(limit, 1), 25)
        failed_messages = (
            self.client.table("messages")
            .select(
                "id, conversation_id, direction, from_phone, to_phone, body, twilio_message_sid, "
                "delivery_status, delivery_error_code, delivery_error_message, created_at"
            )
            .in_("delivery_status", ["failed", "undelivered"])
            .order("created_at", desc=True)
            .limit(safe_limit)
            .execute()
            .data
        )

        calls = (
            self.client.table("calls")
            .select(
                "id, conversation_id, direction, call_type, customer_phone, employee_phone, twilio_call_sid, "
                "status, outcome, notes, follow_up_status, recap, transcription, "
                "recording_sid, recording_url, recording_status, recording_duration_seconds, recording_channels, "
                "started_at, answered_at, completed_at, created_at, updated_at"
            )
            .order("created_at", desc=True)
            .limit(max(safe_limit * 20, 50))
            .execute()
            .data
        )
        call_attention = [
            item
            for item in (_call_attention_item(call) for call in calls)
            if item is not None
        ][:safe_limit]

        conversation_ids = sorted(
            {
                str(row.get("conversation_id"))
                for row in [*failed_messages, *(item["call"] for item in call_attention)]
                if row.get("conversation_id")
            }
        )
        conversations_by_id: dict[str, dict[str, Any]] = {}
        if conversation_ids:
            conversations = (
                self.client.table("conversations")
                .select("id, customer_phone, customer_channel, conversation_code, status, updated_at")
                .in_("id", conversation_ids)
                .execute()
                .data
            )
            conversations_by_id = {conversation["id"]: conversation for conversation in conversations}

        customer_phones = sorted(
            {
                str(value)
                for row in [*failed_messages, *(item["call"] for item in call_attention)]
                for value in (
                    row.get("customer_phone"),
                    row.get("from_phone"),
                    row.get("to_phone"),
                    (conversations_by_id.get(str(row.get("conversation_id") or "")) or {}).get("customer_phone"),
                )
                if value
            }
        )
        contacts_by_phone: dict[str, dict[str, Any]] = {}
        if customer_phones:
            contacts = (
                self.client.table("contacts")
                .select("phone_number, display_name, lookup_name")
                .in_("phone_number", customer_phones)
                .execute()
                .data
            )
            contacts_by_phone = {contact["phone_number"]: contact for contact in contacts}

        return {
            "message_failures": [
                _with_operational_context(message, conversations_by_id, contacts_by_phone)
                for message in failed_messages
            ],
            "call_attention": [
                {
                    **item,
                    "call": _with_operational_context(item["call"], conversations_by_id, contacts_by_phone),
                }
                for item in call_attention
            ],
        }

    def create_customer_action_request(
        self,
        *,
        conversation_id: str,
        contact_id: str | None,
        request_type: str,
        status: str,
        title: str | None,
        operator_note: str | None,
        public_token_hash: str,
        expires_at: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        result = (
            self.client.table("customer_action_requests")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "contact_id": contact_id,
                    "request_type": request_type,
                    "status": status,
                    "title": title,
                    "operator_note": operator_note,
                    "public_token_hash": public_token_hash,
                    "expires_at": expires_at,
                    "created_by": created_by,
                }
            )
            .execute()
        )
        return result.data[0]

    def create_customer_action_file(
        self,
        *,
        request_id: str,
        role: str,
        bucket: str | None = None,
        object_path: str | None = None,
        public_url: str | None = None,
        external_url: str | None = None,
        original_filename: str | None = None,
        content_type: str | None = None,
        size_bytes: int | None = None,
    ) -> dict[str, Any]:
        result = (
            self.client.table("customer_action_files")
            .insert(
                {
                    "request_id": request_id,
                    "role": role,
                    "bucket": bucket,
                    "object_path": object_path,
                    "public_url": public_url,
                    "external_url": external_url,
                    "original_filename": original_filename,
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                }
            )
            .execute()
        )
        return result.data[0]

    def create_customer_action_event(
        self,
        *,
        request_id: str,
        conversation_id: str,
        event_type: str,
        comment: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = (
            self.client.table("customer_action_events")
            .insert(
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "event_type": event_type,
                    "comment": comment,
                    "metadata": metadata or {},
                }
            )
            .execute()
        )
        return result.data[0]

    def get_customer_action_by_token_hash(self, public_token_hash: str) -> dict[str, Any] | None:
        result = (
            self.client.table("customer_action_requests")
            .select("*")
            .eq("public_token_hash", public_token_hash)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def get_customer_action_request(self, request_id: str) -> dict[str, Any] | None:
        result = (
            self.client.table("customer_action_requests")
            .select("*")
            .eq("id", request_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    def list_customer_actions_for_conversation(self, conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
        result = (
            self.client.table("customer_action_requests")
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data

    def list_customer_action_files(self, request_id: str) -> list[dict[str, Any]]:
        result = (
            self.client.table("customer_action_files")
            .select("*")
            .eq("request_id", request_id)
            .order("created_at", desc=False)
            .execute()
        )
        return result.data

    def list_customer_action_events(self, request_id: str) -> list[dict[str, Any]]:
        result = (
            self.client.table("customer_action_events")
            .select("*")
            .eq("request_id", request_id)
            .order("created_at", desc=False)
            .execute()
        )
        return result.data

    def update_customer_action_request_status(
        self,
        *,
        request_id: str,
        status: str,
        completed_at: str | None = None,
        canceled_at: str | None = None,
    ) -> dict[str, Any] | None:
        result = (
            self.client.table("customer_action_requests")
            .update(
                {
                    "status": status,
                    "completed_at": completed_at,
                    "canceled_at": canceled_at,
                }
            )
            .eq("id", request_id)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]


def _message_search_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        parts.extend(
            str(value)
            for value in (
                message.get("body"),
                message.get("direction"),
                message.get("delivery_status"),
                message.get("delivery_error_code"),
            )
            if value
        )
    return " ".join(parts)


def _latest_customer_visible_message(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for message in messages:
        if message.get("direction") != "system":
            return message
    return None


def _conversation_activity_at(conversation: dict[str, Any], last_message: dict[str, Any] | None) -> str | None:
    conversation_updated_at = conversation.get("updated_at")
    message_created_at = last_message.get("created_at") if last_message else None
    if conversation_updated_at and message_created_at:
        return max(str(conversation_updated_at), str(message_created_at))
    return message_created_at or conversation_updated_at


def _call_conversation_matches(row: dict[str, Any], needle: str) -> bool:
    conversation = row.get("conversation") or {}
    latest_call = row.get("latest_call") or {}
    haystack = " ".join(
        str(value)
        for value in (
            row.get("customer_phone"),
            row.get("customer_name"),
            row.get("customer_display_name"),
            row.get("customer_lookup_name"),
            conversation.get("conversation_code"),
            conversation.get("customer_phone"),
            latest_call.get("customer_phone"),
            latest_call.get("direction"),
            latest_call.get("call_type"),
            latest_call.get("status"),
            latest_call.get("outcome"),
            latest_call.get("follow_up_status"),
            latest_call.get("notes"),
            latest_call.get("recap"),
        )
        if value
    ).lower()
    return needle in haystack


def _contact_matches(contact: dict[str, Any], needle: str) -> bool:
    haystack = " ".join(
        str(value)
        for value in (
            contact.get("phone_number"),
            contact.get("display_name"),
            contact.get("lookup_name"),
            contact.get("notes"),
        )
        if value
    ).lower()
    return needle in haystack


def _contact_search_row(
    contact: dict[str, Any],
    conversations: list[dict[str, Any]],
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    sorted_conversations = sorted(conversations, key=lambda row: row.get("updated_at") or "", reverse=True)
    sorted_calls = sorted(calls, key=lambda row: row.get("created_at") or row.get("started_at") or "", reverse=True)
    open_conversation = next((conversation for conversation in sorted_conversations if conversation.get("status") == "open"), None)
    latest_conversation = sorted_conversations[0] if sorted_conversations else None
    latest_call = sorted_calls[0] if sorted_calls else None
    conversation_activity = (latest_conversation or {}).get("updated_at") or (latest_conversation or {}).get("created_at")
    call_activity = (latest_call or {}).get("created_at") or (latest_call or {}).get("started_at")
    last_activity_at = max(
        [str(value) for value in (conversation_activity, call_activity, contact.get("created_at")) if value],
        default=None,
    )
    return {
        "id": contact.get("id"),
        "phone_number": contact.get("phone_number"),
        "display_name": contact.get("display_name"),
        "lookup_name": contact.get("lookup_name"),
        "name": contact.get("display_name") or contact.get("lookup_name"),
        "notes": contact.get("notes"),
        "created_at": contact.get("created_at"),
        "last_activity_at": last_activity_at,
        "open_conversation_id": (open_conversation or {}).get("id"),
        "last_conversation_id": (latest_conversation or {}).get("id"),
        "latest_call_id": (latest_call or {}).get("id"),
    }


def _call_attention_item(call: dict[str, Any]) -> dict[str, Any] | None:
    recording_status = str(call.get("recording_status") or "").lower()
    call_status = str(call.get("status") or "").lower()
    has_recording = bool(call.get("recording_sid") or call.get("recording_url"))
    has_transcription = bool(str(call.get("transcription") or "").strip())
    has_recap = bool(str(call.get("recap") or "").strip())

    if recording_status in {"failed", "absent", "canceled"}:
        return {"kind": "recording_failed", "call": call}
    if call_status == "completed" and not has_recording:
        return {"kind": "recording_missing", "call": call}
    if recording_status == "completed" and has_recording and not has_transcription:
        return {"kind": "transcription_missing", "call": call}
    if has_transcription and not has_recap:
        return {"kind": "recap_missing", "call": call}
    return None


def _with_operational_context(
    row: dict[str, Any],
    conversations_by_id: dict[str, dict[str, Any]],
    contacts_by_phone: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    conversation = conversations_by_id.get(str(row.get("conversation_id") or "")) or {}
    phone = row.get("customer_phone") or conversation.get("customer_phone") or row.get("to_phone") or row.get("from_phone")
    contact = contacts_by_phone.get(str(phone or ""), {})
    return {
        **row,
        "conversation_code": conversation.get("conversation_code"),
        "customer_channel": conversation.get("customer_channel"),
        "customer_name": contact.get("display_name") or contact.get("lookup_name"),
    }
