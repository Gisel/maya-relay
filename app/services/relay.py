import re

from app.attachments import AttachmentStore, NoopAttachmentStore
from app.config import Settings
from app.db import RelayRepository
from app.lookup import ContactNameLookup, NoopContactNameLookup
from app.models import IncomingMessage
from app.twilio_client import MessageSender


CONVERSATION_CODE_PATTERN = re.compile(r"(?:^|\s)#([A-Z0-9]{4,12})\b", re.IGNORECASE)


class RelayService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: RelayRepository,
        sender: MessageSender,
        attachment_store: AttachmentStore | None = None,
        contact_name_lookup: ContactNameLookup | None = None,
    ):
        self.settings = settings
        self.repository = repository
        self.sender = sender
        self.attachment_store = attachment_store or NoopAttachmentStore()
        self.contact_name_lookup = contact_name_lookup or NoopContactNameLookup()

    def handle_inbound_sms(self, message: IncomingMessage) -> dict[str, str | None]:
        if self._is_employee(message.from_phone):
            return self._handle_employee_reply(message)
        return self._handle_customer_message(message)

    def _handle_customer_message(self, message: IncomingMessage) -> dict[str, str | None]:
        conversation = self.repository.get_or_create_customer_conversation(
            customer_phone=message.from_phone,
            assigned_employee=self.settings.francisco_phone,
        )
        inbound_message = self.repository.create_message(
            conversation_id=conversation.id,
            direction="customer_to_employee",
            from_phone=message.from_phone,
            to_phone=message.to_phone,
            body=message.body,
            twilio_message_sid=message.message_sid,
            num_media=message.num_media,
            media_urls=message.media_urls,
            media_content_types=message.media_content_types,
        )
        media_urls = self._store_attachment_urls(
            message_id=inbound_message["id"],
            media_urls=message.media_urls,
            media_content_types=message.media_content_types,
        )

        from_label = self._contact_label(message.from_phone, default_prefix="customer")
        forwarded_body = self._format_forwarded_body(
            from_label=from_label,
            body=message.body,
            media_urls=media_urls,
            media_content_types=message.media_content_types,
            conversation_code=conversation.conversation_code,
        )
        outbound_sid = self.sender.send_sms(to_phone=conversation.assigned_employee, body=forwarded_body)
        self.repository.create_message(
            conversation_id=conversation.id,
            direction="system",
            from_phone=self.settings.maya_business_number,
            to_phone=conversation.assigned_employee,
            body=forwarded_body,
            twilio_message_sid=outbound_sid,
            num_media=len(media_urls),
            media_urls=media_urls,
            media_content_types=message.media_content_types,
        )

        return {"status": "forwarded_to_employee", "conversation_id": conversation.id}

    def _handle_employee_reply(self, message: IncomingMessage) -> dict[str, str | None]:
        conversation_code = self._extract_conversation_code(message.body)
        if conversation_code is None:
            self.sender.send_sms(
                to_phone=message.from_phone,
                body="Please include the customer code, like #A1B2C3D4 your reply.",
            )
            return {"status": "missing_conversation_code", "conversation_id": None}

        reply_body = self._remove_conversation_code(message.body).strip()
        if not reply_body:
            self.sender.send_sms(
                to_phone=message.from_phone,
                body=f"Please include a message after #{conversation_code}.",
            )
            return {"status": "missing_reply_body", "conversation_id": None}

        conversation = self.repository.get_open_conversation_by_code(conversation_code)
        if conversation is None:
            self.sender.send_sms(
                to_phone=message.from_phone,
                body=f"I could not find an open conversation for #{conversation_code}. Check the code and try again.",
            )
            return {"status": "no_open_conversation", "conversation_id": None}

        inbound_message = self.repository.create_message(
            conversation_id=conversation.id,
            direction="employee_to_customer",
            from_phone=message.from_phone,
            to_phone=conversation.customer_phone,
            body=reply_body,
            twilio_message_sid=message.message_sid,
            num_media=message.num_media,
            media_urls=message.media_urls,
            media_content_types=message.media_content_types,
        )
        media_urls = self._store_attachment_urls(
            message_id=inbound_message["id"],
            media_urls=message.media_urls,
            media_content_types=message.media_content_types,
        )
        forwarded_body = self._format_forwarded_body(
            from_label=self._contact_label(message.from_phone, default_prefix="Francisco"),
            body=reply_body,
            media_urls=media_urls,
            media_content_types=message.media_content_types,
        )
        outbound_sid = self.sender.send_sms(to_phone=conversation.customer_phone, body=forwarded_body)
        self.repository.create_message(
            conversation_id=conversation.id,
            direction="system",
            from_phone=self.settings.maya_business_number,
            to_phone=conversation.customer_phone,
            body=forwarded_body,
            twilio_message_sid=outbound_sid,
            num_media=len(media_urls),
            media_urls=media_urls,
            media_content_types=message.media_content_types,
        )

        return {"status": "forwarded_to_customer", "conversation_id": conversation.id}

    def _is_employee(self, phone_number: str) -> bool:
        return phone_number in self.settings.employee_phones

    def _format_forwarded_body(
        self,
        *,
        from_label: str,
        body: str,
        media_urls: tuple[str, ...],
        media_content_types: tuple[str, ...],
        conversation_code: str | None = None,
    ) -> str:
        suffix = f" [#{conversation_code}]" if conversation_code else ""
        lines = [f"From {from_label}{suffix}:"]
        if body:
            lines.append(body)
        for index, media_url in enumerate(media_urls):
            content_type = media_content_types[index] if index < len(media_content_types) else "attachment"
            lines.append(f"Attachment {index + 1} ({content_type}): {media_url}")
        if len(lines) == 1:
            lines.append("[No message body]")
        if conversation_code:
            lines.append(f"Reply with #{conversation_code} your message")
        return "\n".join(lines)

    def _extract_conversation_code(self, body: str) -> str | None:
        match = CONVERSATION_CODE_PATTERN.search(body)
        if match is None:
            return None
        return match.group(1).upper()

    def _remove_conversation_code(self, body: str) -> str:
        return CONVERSATION_CODE_PATTERN.sub(" ", body, count=1)

    def _contact_label(self, phone_number: str, *, default_prefix: str) -> str:
        contact = self.repository.get_or_create_contact(phone_number)
        name = contact.best_name
        if name is None and default_prefix == "customer":
            lookup_name = self.contact_name_lookup.lookup_name(phone_number)
            if lookup_name:
                contact = self.repository.update_contact_lookup_name(phone_number, lookup_name)
                name = contact.best_name

        if name:
            return f"{name} ({phone_number})"
        if default_prefix == "customer":
            return f"customer {phone_number}"
        return default_prefix

    def _store_attachment_urls(
        self,
        *,
        message_id: str,
        media_urls: tuple[str, ...],
        media_content_types: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not media_urls:
            return ()
        try:
            stored = self.attachment_store.store_message_attachments(
                message_id=message_id,
                source_urls=media_urls,
                content_types=media_content_types,
            )
        except Exception:
            return media_urls
        return tuple(attachment.public_url for attachment in stored)
