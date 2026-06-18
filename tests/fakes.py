from datetime import UTC, datetime, timedelta
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
        self.calls: list[dict[str, Any]] = []
        self.call_events: list[dict[str, Any]] = []

    def get_contact(self, phone_number: str) -> Contact | None:
        for contact in self.contacts:
            if contact.phone_number == phone_number:
                return contact
        return None

    def get_contact_by_id(self, contact_id: str) -> Contact | None:
        for contact in self.contacts:
            if contact.id == contact_id:
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
            notes=existing.notes,
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
            notes=existing.notes,
        )
        self.contacts = [updated if contact.phone_number == phone_number else contact for contact in self.contacts]
        return updated

    def update_contact_profile(
        self,
        *,
        contact_id: str,
        display_name: str | None,
        notes: str | None,
    ) -> Contact | None:
        for index, contact in enumerate(self.contacts):
            if contact.id != contact_id:
                continue
            updated = Contact(
                id=contact.id,
                phone_number=contact.phone_number,
                display_name=display_name,
                lookup_name=contact.lookup_name,
                notes=notes,
            )
            self.contacts[index] = updated
            return updated
        return None

    def search_contacts(
        self,
        *,
        q: str = "",
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        needle = q.strip().lower()
        rows: list[dict[str, Any]] = []
        for contact in self.contacts:
            if needle and needle not in " ".join(
                str(value)
                for value in (contact.phone_number, contact.display_name, contact.lookup_name, contact.notes)
                if value
            ).lower():
                continue
            conversations = [conversation for conversation in self.conversations if conversation.customer_phone == contact.phone_number]
            calls = [call for call in self.calls if call.get("customer_phone") == contact.phone_number]
            open_conversation = next((conversation for conversation in reversed(conversations) if conversation.status == "open"), None)
            latest_conversation = conversations[-1] if conversations else None
            latest_call = calls[-1] if calls else None
            rows.append(
                {
                    "id": contact.id,
                    "phone_number": contact.phone_number,
                    "display_name": contact.display_name,
                    "lookup_name": contact.lookup_name,
                    "name": contact.best_name,
                    "notes": contact.notes,
                    "created_at": "",
                    "last_activity_at": (latest_call or {}).get("created_at") or "",
                    "open_conversation_id": open_conversation.id if open_conversation else None,
                    "last_conversation_id": latest_conversation.id if latest_conversation else None,
                    "latest_call_id": (latest_call or {}).get("id"),
                }
            )
        page_rows = rows[offset: offset + limit + 1]
        return page_rows[:limit], len(page_rows) > limit

    def import_contact_display_name(
        self,
        *,
        phone_number: str,
        display_name: str,
        overwrite: bool = False,
    ) -> tuple[Contact, str]:
        existing = self.get_contact(phone_number)
        if existing is None:
            contact = Contact(id=f"contact-{len(self.contacts) + 1}", phone_number=phone_number, display_name=display_name)
            self.contacts.append(contact)
            return contact, "created"
        if existing.display_name and not overwrite:
            return existing, "skipped"
        if existing.display_name == display_name:
            return existing, "skipped"
        updated = Contact(
            id=existing.id,
            phone_number=existing.phone_number,
            display_name=display_name,
            lookup_name=existing.lookup_name,
            notes=existing.notes,
        )
        self.contacts = [updated if contact.phone_number == phone_number else contact for contact in self.contacts]
        return updated, "updated"

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
        for message in self.messages:
            if message.get("twilio_message_sid") == twilio_message_sid:
                message["delivery_status"] = status
                message["delivery_error_code"] = error_code
                message["delivery_error_message"] = error_message

    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = "",
        channel: str = "",
    ) -> list[dict[str, Any]]:
        rows = []
        filtered_conversations = [
            conversation
            for conversation in self.conversations
            if (not status or conversation.status == status)
            and (not channel or conversation.customer_channel == channel)
        ]
        for conversation in filtered_conversations[offset: offset + limit]:
            messages = [
                message
                for message in self.messages
                if message["conversation_id"] == conversation.id
            ]
            last_message = next(
                (message for message in reversed(messages) if message.get("direction") != "system"),
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

    def list_calls_for_conversation(self, conversation_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return [
            call
            for call in reversed(self.calls)
            if call["conversation_id"] == conversation_id
        ][:limit]

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        for call in self.calls:
            if call["id"] == call_id:
                return call
        return None

    def list_call_conversations(
        self,
        *,
        q: str = "",
        direction: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        calls = [
            call
            for call in reversed(self.calls)
            if direction == "all" or call.get("direction") == direction
        ]
        grouped: dict[str, dict[str, Any]] = {}
        for call in calls:
            key = call.get("conversation_id") or f"phone:{call.get('customer_phone')}"
            conversation = self.get_conversation(call.get("conversation_id") or "")
            contact = self.get_contact((conversation.customer_phone if conversation else call.get("customer_phone")) or "")
            row = grouped.setdefault(
                key,
                {
                    "id": key,
                    "conversation": {
                        "id": conversation.id,
                        "customer_phone": conversation.customer_phone,
                        "assigned_employee": conversation.assigned_employee,
                        "customer_channel": conversation.customer_channel,
                        "conversation_code": conversation.conversation_code,
                        "status": conversation.status,
                        "created_at": "",
                        "updated_at": "",
                    } if conversation else None,
                    "customer_phone": conversation.customer_phone if conversation else call.get("customer_phone"),
                    "customer_display_name": contact.display_name if contact else None,
                    "customer_lookup_name": contact.lookup_name if contact else None,
                    "customer_name": contact.best_name if contact else None,
                    "latest_call": call,
                    "call_count": 0,
                },
            )
            row["call_count"] += 1

        rows = list(grouped.values())
        needle = q.strip().lower()
        if needle:
            rows = [
                row for row in rows
                if needle in " ".join(
                    str(value)
                    for value in (
                        row.get("customer_phone"),
                        row.get("customer_name"),
                        row.get("customer_display_name"),
                        row.get("customer_lookup_name"),
                        (row.get("conversation") or {}).get("conversation_code"),
                        (row.get("latest_call") or {}).get("status"),
                        (row.get("latest_call") or {}).get("direction"),
                    )
                    if value
                ).lower()
            ]
        page_rows = rows[offset: offset + limit + 1]
        return page_rows[:limit], len(page_rows) > limit

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
        for call in self.calls:
            if call["id"] != call_id:
                continue
            call["outcome"] = outcome
            call["follow_up_status"] = follow_up_status
            call["notes"] = notes
            call["recap"] = recap
            call["transcription"] = transcription
            return call
        return None

    def update_call_transcription(
        self,
        *,
        call_id: str,
        transcription: str | None,
    ) -> dict[str, Any] | None:
        for call in self.calls:
            if call["id"] != call_id:
                continue
            call["transcription"] = transcription
            return call
        return None

    def update_call_recap(
        self,
        *,
        call_id: str,
        recap: str | None,
    ) -> dict[str, Any] | None:
        for call in self.calls:
            if call["id"] != call_id:
                continue
            call["recap"] = recap
            return call
        return None

    def get_recent_active_call(
        self,
        *,
        conversation_id: str,
        max_age_seconds: int = 30,
    ) -> dict[str, Any] | None:
        active_statuses = {"initiated", "ringing", "in-progress", "queued"}
        for call in reversed(self.calls):
            if (
                call["conversation_id"] == conversation_id
                and call["status"] in active_statuses
            ):
                created_at = call.get("created_at")
                if created_at:
                    cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
                    if datetime.fromisoformat(created_at) < cutoff:
                        continue
                return call
        return None

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
        call = {
            "id": f"call-{len(self.calls) + 1}",
            "conversation_id": conversation_id,
            "direction": direction,
            "call_type": call_type,
            "customer_phone": customer_phone,
            "employee_phone": employee_phone,
            "twilio_call_sid": twilio_call_sid,
            "status": status,
            "outcome": None,
            "notes": None,
            "follow_up_status": "none",
            "recap": None,
            "transcription": None,
            "recording_sid": None,
            "recording_url": None,
            "recording_status": None,
            "recording_duration_seconds": None,
            "recording_channels": None,
            "answered_at": None,
            "completed_at": None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.calls.append(call)
        return call

    def update_call_status_by_sid(
        self,
        *,
        twilio_call_sid: str,
        status: str,
    ) -> dict[str, Any] | None:
        for call in self.calls:
            if call["twilio_call_sid"] != twilio_call_sid:
                continue
            call["status"] = status
            if status in {"answered", "in-progress"}:
                call["answered_at"] = datetime.now(UTC).isoformat()
            if status == "completed":
                call["completed_at"] = datetime.now(UTC).isoformat()
            return call
        return None

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
        for call in self.calls:
            if call["twilio_call_sid"] != twilio_call_sid:
                continue
            call["recording_sid"] = recording_sid
            call["recording_url"] = recording_url
            call["recording_status"] = recording_status
            call["recording_duration_seconds"] = recording_duration_seconds
            call["recording_channels"] = recording_channels
            if recording_status == "completed" and not call.get("outcome") and call.get("status") != "completed":
                call["outcome"] = "voicemail"
                call["follow_up_status"] = "needed"
            return call
        return None

    def create_call_event(
        self,
        *,
        call_id: str | None,
        twilio_call_sid: str | None,
        event_type: str,
        call_status: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "id": f"call-event-{len(self.call_events) + 1}",
            "call_id": call_id,
            "twilio_call_sid": twilio_call_sid,
            "event_type": event_type,
            "call_status": call_status,
            "payload": payload,
        }
        self.call_events.append(event)
        return event

    def get_operational_status(self, *, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
        safe_limit = min(max(limit, 1), 25)
        message_failures = [
            self._with_operational_context(message)
            for message in reversed(self.messages)
            if message.get("delivery_status") in {"failed", "undelivered"}
        ][:safe_limit]
        call_attention = [
            {"kind": kind, "call": self._with_operational_context(call)}
            for call in reversed(self.calls)
            for kind in [self._call_attention_kind(call)]
            if kind is not None
        ][:safe_limit]
        return {
            "message_failures": message_failures,
            "call_attention": call_attention,
        }

    def _with_operational_context(self, row: dict[str, Any]) -> dict[str, Any]:
        conversation = self.get_conversation(str(row.get("conversation_id") or ""))
        phone = row.get("customer_phone") or (conversation.customer_phone if conversation else None) or row.get("to_phone") or row.get("from_phone")
        contact = self.get_contact(str(phone or ""))
        return {
            **row,
            "conversation_code": conversation.conversation_code if conversation else None,
            "customer_channel": conversation.customer_channel if conversation else None,
            "customer_name": contact.best_name if contact else None,
        }

    @staticmethod
    def _call_attention_kind(call: dict[str, Any]) -> str | None:
        recording_status = str(call.get("recording_status") or "").lower()
        call_status = str(call.get("status") or "").lower()
        has_recording = bool(call.get("recording_sid") or call.get("recording_url"))
        has_transcription = bool(str(call.get("transcription") or "").strip())
        has_recap = bool(str(call.get("recap") or "").strip())
        if recording_status in {"failed", "absent", "canceled"}:
            return "recording_failed"
        if call_status == "completed" and not has_recording:
            return "recording_missing"
        if recording_status == "completed" and has_recording and not has_transcription:
            return "transcription_missing"
        if has_transcription and not has_recap:
            return "recap_missing"
        return None


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
