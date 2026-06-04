from typing import Protocol

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import Settings


class ContactNameLookup(Protocol):
    def lookup_name(self, phone_number: str) -> str | None:
        ...


class NoopContactNameLookup:
    def lookup_name(self, phone_number: str) -> str | None:
        return None


class TwilioContactNameLookup:
    def __init__(self, settings: Settings):
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required.")
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    def lookup_name(self, phone_number: str) -> str | None:
        try:
            result = self.client.lookups.v2.phone_numbers(phone_number).fetch(fields="caller_name")
        except TwilioRestException:
            return None

        caller_name = getattr(result, "caller_name", None)
        if not isinstance(caller_name, dict):
            return None

        name = caller_name.get("caller_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return None
