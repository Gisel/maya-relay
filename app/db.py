from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Any, Protocol

from supabase import Client, create_client

from app.config import Settings
from app.models import Channel, Contact, Conversation


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
    )


def _new_conversation_code() -> str:
    return token_hex(4).upper()


class RelayRepository(Protocol):
    def get_contact(self, phone_number: str) -> Contact | None:
        ...

    def get_or_create_contact(self, phone_number: str) -> Contact:
        ...

    def update_contact_lookup_name(self, phone_number: str, lookup_name: str | None) -> Contact:
        ...

    def upsert_contact_display_name(self, phone_number: str, display_name: str) -> Contact:
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
        result = (
            self.client.table("contacts")
            .select("id, phone_number, display_name, lookup_name")
            .eq("phone_number", phone_number)
            .limit(1)
            .execute()
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
        if recording_status == "completed" and not call.get("outcome"):
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
