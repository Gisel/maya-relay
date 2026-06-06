from typing import Any

from app.attachments import StoredAttachment
from app.models import Channel, Contact, Conversation


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

    def upsert_contact_display_name(self, phone_number: str, display_name: str) -> Contact:
        existing = self.get_or_create_contact(phone_number)
        updated = Contact(
            id=existing.id,
            phone_number=existing.phone_number,
            display_name=display_name,
            lookup_name=existing.lookup_name,
        )
        self.contacts = [updated if contact.phone_number == phone_number else contact for contact in self.contacts]
        return updated

    def get_or_create_customer_conversation(
        self,
        customer_phone: str,
        assigned_employee: str,
        customer_channel: Channel = "sms",
    ) -> Conversation:
        for conversation in self.conversations:
            if (
                conversation.customer_phone == customer_phone
                and conversation.assigned_employee == assigned_employee
                and conversation.customer_channel == customer_channel
                and conversation.status == "open"
            ):
                return conversation

        conversation = Conversation(
            id=f"conversation-{len(self.conversations) + 1}",
            customer_phone=customer_phone,
            assigned_employee=assigned_employee,
            status="open",
            conversation_code=f"C{len(self.conversations) + 1:04d}",
            customer_channel=customer_channel,
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

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        for conversation in self.conversations:
            if conversation.id == conversation_id:
                return conversation
        return None

    def update_conversation_status(self, conversation_id: str, status: str) -> Conversation:
        for index, conversation in enumerate(self.conversations):
            if conversation.id == conversation_id:
                updated = Conversation(
                    id=conversation.id,
                    customer_phone=conversation.customer_phone,
                    assigned_employee=conversation.assigned_employee,
                    status=status,
                    conversation_code=conversation.conversation_code,
                    customer_channel=conversation.customer_channel,
                )
                self.conversations[index] = updated
                return updated
        raise AssertionError(f"conversation not found: {conversation_id}")

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
            "client_request_id": client_request_id,
        }
        self.messages.append(message)
        return message

    def get_message_by_client_request_id(
        self,
        *,
        conversation_id: str,
        client_request_id: str,
    ) -> dict[str, Any] | None:
        for message in self.messages:
            if (
                message["conversation_id"] == conversation_id
                and message.get("client_request_id") == client_request_id
            ):
                return message
        return None

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

    def list_conversations(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = []
        for conversation in self.conversations[offset: offset + limit]:
            messages = [
                message
                for message in self.messages
                if message["conversation_id"] == conversation.id
            ]
            last_message = next(
                (message for message in reversed(messages)),
                None,
            )
            contact = self.get_contact(conversation.customer_phone)
            rows.append(
                {
                    "id": conversation.id,
                    "customer_phone": conversation.customer_phone,
                    "assigned_employee": conversation.assigned_employee,
                    "customer_channel": conversation.customer_channel,
                    "conversation_code": conversation.conversation_code,
                    "status": conversation.status,
                    "created_at": "",
                    "updated_at": "",
                    "customer_name": contact.best_name if contact else None,
                    "customer_display_name": contact.display_name if contact else None,
                    "customer_lookup_name": contact.lookup_name if contact else None,
                    "last_message": last_message,
                    "message_search_text": _message_search_text(messages),
                }
            )
        return rows

    def list_messages_for_conversation(self, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return [message for message in self.messages if message["conversation_id"] == conversation_id][:limit]


class FakeSender:
    def __init__(self):
        self.sent_messages: list[dict[str, object]] = []

    def send_sms(self, *, to_phone: str, body: str, media_urls: tuple[str, ...] = ()) -> str:
        return self.send_message(to_phone=to_phone, body=body, channel="sms", media_urls=media_urls)

    def send_message(
        self,
        *,
        to_phone: str,
        body: str,
        channel: Channel = "sms",
        media_urls: tuple[str, ...] = (),
    ) -> str:
        sid = f"SMfake{len(self.sent_messages) + 1}"
        message: dict[str, object] = {"sid": sid, "to_phone": to_phone, "body": body}
        if channel != "sms":
            message["channel"] = channel
        if media_urls:
            message["media_urls"] = media_urls
        self.sent_messages.append(message)
        return sid


class FakeVoiceCaller:
    def __init__(self):
        self.calls: list[dict[str, str]] = []

    def start_click_to_call(self, *, employee_phone: str, bridge_url: str, status_callback_url: str) -> str:
        sid = f"CAfake{len(self.calls) + 1}"
        self.calls.append(
            {
                "employee_phone": employee_phone,
                "bridge_url": bridge_url,
                "status_callback_url": status_callback_url,
            }
        )
        return sid


class FakeAttachmentStore:
    def __init__(self):
        self.uploads: list[dict[str, object]] = []

    def store_uploaded_attachments(
        self,
        *,
        object_prefix: str,
        files: tuple[object, ...],
    ) -> tuple[StoredAttachment, ...]:
        self.uploads.append({"object_prefix": object_prefix, "files": files})
        return tuple(
            StoredAttachment(
                source_url=f"upload:{file.filename}",
                public_url=f"https://files.example/{object_prefix}/{file.filename}",
                content_type=file.content_type,
                bucket="attachments",
                object_path=f"{object_prefix}/{file.filename}",
            )
            for file in files
        )


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
