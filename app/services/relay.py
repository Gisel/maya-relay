from app.config import Settings
from app.db import RelayRepository
from app.models import IncomingMessage
from app.twilio_client import MessageSender


class RelayService:
    def __init__(self, *, settings: Settings, repository: RelayRepository, sender: MessageSender):
        self.settings = settings
        self.repository = repository
        self.sender = sender

    def handle_inbound_sms(self, message: IncomingMessage) -> dict[str, str | None]:
        if self._is_employee(message.from_phone):
            return self._handle_employee_reply(message)
        return self._handle_customer_message(message)

    def _handle_customer_message(self, message: IncomingMessage) -> dict[str, str | None]:
        conversation = self.repository.get_or_create_customer_conversation(
            customer_phone=message.from_phone,
            assigned_employee=self.settings.francisco_phone,
        )
        self.repository.create_message(
            conversation_id=conversation.id,
            direction="customer_to_employee",
            from_phone=message.from_phone,
            to_phone=message.to_phone,
            body=message.body,
            twilio_message_sid=message.message_sid,
        )

        forwarded_body = f"From customer {message.from_phone}:\n{message.body}"
        outbound_sid = self.sender.send_sms(to_phone=conversation.assigned_employee, body=forwarded_body)
        self.repository.create_message(
            conversation_id=conversation.id,
            direction="system",
            from_phone=self.settings.maya_business_number,
            to_phone=conversation.assigned_employee,
            body=forwarded_body,
            twilio_message_sid=outbound_sid,
        )

        return {"status": "forwarded_to_employee", "conversation_id": conversation.id}

    def _handle_employee_reply(self, message: IncomingMessage) -> dict[str, str | None]:
        conversation = self.repository.get_latest_employee_conversation(message.from_phone)
        if conversation is None:
            return {"status": "no_open_conversation", "conversation_id": None}

        self.repository.create_message(
            conversation_id=conversation.id,
            direction="employee_to_customer",
            from_phone=message.from_phone,
            to_phone=conversation.customer_phone,
            body=message.body,
            twilio_message_sid=message.message_sid,
        )
        outbound_sid = self.sender.send_sms(to_phone=conversation.customer_phone, body=message.body)
        self.repository.create_message(
            conversation_id=conversation.id,
            direction="system",
            from_phone=self.settings.maya_business_number,
            to_phone=conversation.customer_phone,
            body=message.body,
            twilio_message_sid=outbound_sid,
        )

        return {"status": "forwarded_to_customer", "conversation_id": conversation.id}

    def _is_employee(self, phone_number: str) -> bool:
        return phone_number == self.settings.francisco_phone

