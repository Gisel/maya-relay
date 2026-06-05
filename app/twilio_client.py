from typing import Protocol

from twilio.rest import Client

from app.config import Settings
from app.models import Channel


class MessageSender(Protocol):
    def send_sms(self, *, to_phone: str, body: str) -> str:
        ...

    def send_message(self, *, to_phone: str, body: str, channel: Channel = "sms") -> str:
        ...


class TwilioMessageSender:
    def __init__(self, settings: Settings):
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required.")
        if not settings.twilio_messaging_service_sid:
            raise RuntimeError("TWILIO_MESSAGING_SERVICE_SID is required.")

        self.settings = settings
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    def send_sms(self, *, to_phone: str, body: str) -> str:
        return self.send_message(to_phone=to_phone, body=body, channel="sms")

    def send_message(self, *, to_phone: str, body: str, channel: Channel = "sms") -> str:
        message = self.client.messages.create(
            messaging_service_sid=self.settings.twilio_messaging_service_sid,
            to=_recipient_for_channel(to_phone, channel),
            body=body,
        )
        return message.sid


def _recipient_for_channel(phone_number: str, channel: Channel) -> str:
    if channel == "whatsapp":
        return phone_number if phone_number.lower().startswith("whatsapp:") else f"whatsapp:{phone_number}"
    return phone_number
