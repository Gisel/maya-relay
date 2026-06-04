from datetime import UTC, datetime
from secrets import token_hex
from typing import Any, Protocol

from supabase import Client, create_client

from app.config import Settings
from app.models import Contact, Conversation


def _conversation_from_row(row: dict[str, Any]) -> Conversation:
    conversation_code = row.get("conversation_code") or str(row["id"]).replace("-", "")[:8].upper()
    return Conversation(
        id=row["id"],
        customer_phone=row["customer_phone"],
        assigned_employee=row["assigned_employee"],
        status=row["status"],
        conversation_code=conversation_code,
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

    def get_or_create_customer_conversation(self, customer_phone: str, assigned_employee: str) -> Conversation:
        ...

    def get_latest_employee_conversation(self, employee_phone: str) -> Conversation | None:
        ...

    def get_open_conversation_by_code(self, employee_phone: str, conversation_code: str) -> Conversation | None:
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
    ) -> dict[str, Any]:
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


class SupabaseRelayRepository:
    def __init__(self, client: Client):
        self.client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> "SupabaseRelayRepository":
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
        return cls(create_client(settings.supabase_url, settings.supabase_service_role_key))

    def get_or_create_customer_conversation(self, customer_phone: str, assigned_employee: str) -> Conversation:
        self.get_or_create_contact(customer_phone)

        existing = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status, conversation_code")
            .eq("customer_phone", customer_phone)
            .eq("assigned_employee", assigned_employee)
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

    def get_latest_employee_conversation(self, employee_phone: str) -> Conversation | None:
        result = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status, conversation_code")
            .eq("assigned_employee", employee_phone)
            .eq("status", "open")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return _conversation_from_row(result.data[0])

    def get_open_conversation_by_code(self, employee_phone: str, conversation_code: str) -> Conversation | None:
        result = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status, conversation_code")
            .eq("assigned_employee", employee_phone)
            .eq("conversation_code", conversation_code.upper())
            .eq("status", "open")
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
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
    ) -> dict[str, Any]:
        result = (
            self.client.table("messages")
            .insert(
                {
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
            )
            .execute()
        )
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
