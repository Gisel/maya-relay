from typing import Any

from app.models import Contact, Conversation


class FakeRepository:
    def __init__(self):
        self.conversations: list[Conversation] = []
        self.contacts: list[Contact] = []
        self.messages: list[dict[str, Any]] = []
        self.attachments: list[dict[str, Any]] = []
        self.status_updates: list[dict[str, Any]] = []

    def get_contact(self, phone_number: str) -> Contact | None:
        for contact in self.contacts:
            if contact.phone_number == phone_number:
                return contact
        return None

    def get_or_create_contact(self, phone_number: str) -> Contact:
        existing = self.get_contact(phone_number)
        if existing is not None:
            return existing
        contact = Contact(id=f"contact-{len(self.contacts) + 1}", phone_number=phone_number)
        self.contacts.append(contact)
        return contact

    def update_contact_lookup_name(self, phone_number: str, lookup_name: str | None) -> Contact:
        existing = self.get_or_create_contact(phone_number)
        updated = Contact(
            id=existing.id,
            phone_number=existing.phone_number,
            display_name=existing.display_name,
            lookup_name=lookup_name,
        )
        self.contacts = [updated if contact.phone_number == phone_number else contact for contact in self.contacts]
        return updated

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
            conversation_code=f"C{len(self.conversations) + 1:04d}",
        )
        self.conversations.append(conversation)
        return conversation

    def get_latest_employee_conversation(self, employee_phone: str) -> Conversation | None:
        for conversation in reversed(self.conversations):
            if conversation.assigned_employee == employee_phone and conversation.status == "open":
                return conversation
        return None

    def get_open_conversation_by_code(self, conversation_code: str) -> Conversation | None:
        for conversation in self.conversations:
            if (
                conversation.conversation_code == conversation_code.upper()
                and conversation.status == "open"
            ):
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
            "id": f"message-{len(self.messages) + 1}",
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
        attachment = {
            "id": f"attachment-{len(self.attachments) + 1}",
            "message_id": message_id,
            "bucket": bucket,
            "object_path": object_path,
            "public_url": public_url,
            "source_url": source_url,
            "content_type": content_type,
            "size_bytes": size_bytes,
        }
        self.attachments.append(attachment)
        return attachment

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


class FakeLookup:
    def __init__(self, names: dict[str, str | None] | None = None):
        self.names = names or {}
        self.looked_up: list[str] = []

    def lookup_name(self, phone_number: str) -> str | None:
        self.looked_up.append(phone_number)
        return self.names.get(phone_number)


class FakeTriage:
    def __init__(self, note: str | None = None, should_raise: bool = False):
        self.note = note
        self.should_raise = should_raise
        self.calls: list[dict[str, object]] = []

    def summarize(self, *, body: str, has_attachments: bool, conversation_code: str | None = None) -> str | None:
        self.calls.append(
            {"body": body, "has_attachments": has_attachments, "conversation_code": conversation_code}
        )
        if self.should_raise:
            raise RuntimeError("triage failed")
        return self.note
