from typing import Any, Protocol

from supabase import Client, create_client

from app.config import Settings
from app.models import Conversation


class RelayRepository(Protocol):
    def get_or_create_customer_conversation(self, customer_phone: str, assigned_employee: str) -> Conversation:
        ...

    def get_latest_employee_conversation(self, employee_phone: str) -> Conversation | None:
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
        existing = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status")
            .eq("customer_phone", customer_phone)
            .eq("assigned_employee", assigned_employee)
            .eq("status", "open")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            return Conversation(**row)

        created = (
            self.client.table("conversations")
            .insert(
                {
                    "customer_phone": customer_phone,
                    "assigned_employee": assigned_employee,
                    "status": "open",
                }
            )
            .select("id, customer_phone, assigned_employee, status")
            .execute()
        )
        return Conversation(**created.data[0])

    def get_latest_employee_conversation(self, employee_phone: str) -> Conversation | None:
        result = (
            self.client.table("conversations")
            .select("id, customer_phone, assigned_employee, status")
            .eq("assigned_employee", employee_phone)
            .eq("status", "open")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return Conversation(**result.data[0])

    def create_message(
        self,
        *,
        conversation_id: str,
        direction: str,
        from_phone: str,
        to_phone: str,
        body: str,
        twilio_message_sid: str | None = None,
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
                }
            )
            .select("*")
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

