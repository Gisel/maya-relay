import json
from typing import Protocol

from twilio.rest import Client

from app.config import Settings
from app.models import Channel


class MessageSender(Protocol):
    def send_sms(self, *, to_phone: str, body: str, media_urls: tuple[str, ...] = ()) -> str:
        ...

    def send_message(
        self,
        *,
        to_phone: str,
        body: str,
        channel: Channel = "sms",
        media_urls: tuple[str, ...] = (),
    ) -> str:
        ...

    def send_template_message(
        self,
        *,
        to_phone: str,
        channel: Channel,
        content_sid: str,
        content_variables: dict[str, str] | None = None,
    ) -> str:
        ...


class VoiceCaller(Protocol):
    def start_click_to_call(
        self,
        *,
        employee_phone: str,
        bridge_url: str,
        status_callback_url: str,
    ) -> str:
        ...


class TwilioMessageSender:
    def __init__(self, settings: Settings):
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required.")
        if not settings.twilio_messaging_service_sid:
            raise RuntimeError("TWILIO_MESSAGING_SERVICE_SID is required.")

        self.settings = settings
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

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
        message_kwargs = {
            "messaging_service_sid": self.settings.twilio_messaging_service_sid,
            "to": _recipient_for_channel(to_phone, channel),
            "body": body,
        }
        if media_urls:
            message_kwargs["media_url"] = list(media_urls)

        message = self.client.messages.create(**message_kwargs)
        return message.sid

    def send_template_message(
        self,
        *,
        to_phone: str,
        channel: Channel,
        content_sid: str,
        content_variables: dict[str, str] | None = None,
    ) -> str:
        message_kwargs = {
            "messaging_service_sid": self.settings.twilio_messaging_service_sid,
            "from_": _sender_for_channel(self.settings.maya_business_number_e164, channel),
            "to": _recipient_for_channel(to_phone, channel),
            "content_sid": content_sid,
        }
        if content_variables:
            message_kwargs["content_variables"] = json.dumps(content_variables)

        message = self.client.messages.create(**message_kwargs)
        return message.sid


class TwilioVoiceCaller:
    def __init__(self, settings: Settings):
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required.")
        if not settings.maya_business_number_e164:
            raise RuntimeError("MAYA_BUSINESS_NUMBER is required.")

        self.settings = settings
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    def start_click_to_call(
        self,
        *,
        employee_phone: str,
        bridge_url: str,
        status_callback_url: str,
    ) -> str:
        call = self.client.calls.create(
            to=employee_phone,
            from_=self.settings.maya_business_number_e164,
            url=bridge_url,
            method="POST",
            status_callback=status_callback_url,
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )
        return call.sid


def _recipient_for_channel(phone_number: str, channel: Channel) -> str:
    if channel == "whatsapp":
        return phone_number if phone_number.lower().startswith("whatsapp:") else f"whatsapp:{phone_number}"
    return phone_number


def _sender_for_channel(phone_number: str, channel: Channel) -> str:
    if channel == "whatsapp":
        return phone_number if phone_number.lower().startswith("whatsapp:") else f"whatsapp:{phone_number}"
    return phone_number
