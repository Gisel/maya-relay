from typing import Any

from app.models import Conversation


class FakeRepository:
    def __init__(self):
        self.conversations: list[Conversation] = []
        self.messages: list[dict[str, Any]] = []
        self.status_updates: list[dict[str, Any]] = []

    def get_or_create_customer_conversation(self, customer_phone: str, assigned_employee: str) -> Conversation:
        for conversation in self.conversations:
            if (
                conversation.customer_phone == customer_phone
                and conversation.assigned_employee == assigned_employee
                and conversation.status == "open"
            ):
                return conversation

        conversation = Conversation(
            id=f"conversation-{len(self.conversations) + 1}",
            customer_phone=customer_phone,
            assigned_employee=assigned_employee,
            status="open",
        )
        self.conversations.append(conversation)
        return conversation

    def get_latest_employee_conversation(self, employee_phone: str) -> Conversation | None:
        for conversation in reversed(self.conversations):
            if conversation.assigned_employee == employee_phone and conversation.status == "open":
                return conversation
        return None

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
        message = {
            "conversation_id": conversation_id,
            "direction": direction,
            "from_phone": from_phone,
            "to_phone": to_phone,
            "body": body,
            "twilio_message_sid": twilio_message_sid,
            "num_media": num_media,
            "media_urls": media_urls,
            "media_content_types": media_content_types,
        }
        self.messages.append(message)
        return message

    def update_message_status(
        self,
        *,
        twilio_message_sid: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.status_updates.append(
            {
                "twilio_message_sid": twilio_message_sid,
                "status": status,
                "error_code": error_code,
                "error_message": error_message,
            }
        )


class FakeSender:
    def __init__(self):
        self.sent_messages: list[dict[str, str]] = []

    def send_sms(self, *, to_phone: str, body: str) -> str:
        sid = f"SMfake{len(self.sent_messages) + 1}"
        self.sent_messages.append({"sid": sid, "to_phone": to_phone, "body": body})
        return sid
