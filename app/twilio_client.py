from typing import Protocol

from twilio.rest import Client

from app.config import Settings


class MessageSender(Protocol):
    def send_sms(self, *, to_phone: str, body: str) -> str:
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
        message = self.client.messages.create(
            messaging_service_sid=self.settings.twilio_messaging_service_sid,
            to=to_phone,
            body=body,
        )
        return message.sid

