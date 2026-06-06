from datetime import UTC, datetime
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

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        ...

    def list_messages_for_conversation(self, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
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

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        result = (
            self.client.table("conversations")
            .select(
                "id, customer_phone, assigned_employee, customer_channel, "
                "conversation_code, status, created_at, updated_at"
            )
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        conversations: list[dict[str, Any]] = []
        for conversation in result.data:
            messages = (
                self.client.table("messages")
                .select("body, direction, delivery_status, delivery_error_code, created_at, num_media")
                .eq("conversation_id", conversation["id"])
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
            contacts = (
                self.client.table("contacts")
                .select("display_name, lookup_name")
                .eq("phone_number", conversation["customer_phone"])
                .limit(1)
                .execute()
            )
            contact = contacts.data[0] if contacts.data else {}
            conversations.append(
                {
                    **conversation,
                    "customer_display_name": contact.get("display_name"),
                    "customer_lookup_name": contact.get("lookup_name"),
                    "customer_name": contact.get("display_name") or contact.get("lookup_name"),
                    "last_message": messages.data[0] if messages.data else None,
                    "message_search_text": _message_search_text(messages.data),
                }
            )
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
