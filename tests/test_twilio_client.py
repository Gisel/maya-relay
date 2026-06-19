from app.config import Settings
from app.twilio_client import TwilioMessageSender


def test_twilio_sender_passes_media_urls_to_messages_create(monkeypatch):
    captured = {}

    class FakeMessage:
        sid = "SMcreated"

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeMessage()

    class FakeClient:
        def __init__(self, *_args):
            self.messages = FakeMessages()

    monkeypatch.setattr("app.twilio_client.Client", FakeClient)
    sender = TwilioMessageSender(
        Settings(
            TWILIO_ACCOUNT_SID="ACtest",
            TWILIO_AUTH_TOKEN="token",
            TWILIO_MESSAGING_SERVICE_SID="MGtest",
        )
    )

    sid = sender.send_message(
        to_phone="+15550000001",
        body="Please review.",
        channel="whatsapp",
        media_urls=("https://files.example/proof.jpg",),
    )

    assert sid == "SMcreated"
    assert captured == {
        "messaging_service_sid": "MGtest",
        "to": "whatsapp:+15550000001",
        "body": "Please review.",
        "media_url": ["https://files.example/proof.jpg"],
    }


def test_twilio_sender_sends_content_template_without_body_or_media(monkeypatch):
    captured = {}

    class FakeMessage:
        sid = "SMtemplate"

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeMessage()

    class FakeClient:
        def __init__(self, *_args):
            self.messages = FakeMessages()

    monkeypatch.setattr("app.twilio_client.Client", FakeClient)
    sender = TwilioMessageSender(
        Settings(
            TWILIO_ACCOUNT_SID="ACtest",
            TWILIO_AUTH_TOKEN="token",
            TWILIO_MESSAGING_SERVICE_SID="MGtest",
        )
    )

    sid = sender.send_template_message(
        to_phone="+15550000001",
        channel="whatsapp",
        content_sid="HXtemplate",
        content_variables={"1": "Business cards", "2": "token"},
    )

    assert sid == "SMtemplate"
    assert captured == {
        "messaging_service_sid": "MGtest",
        "to": "whatsapp:+15550000001",
        "content_sid": "HXtemplate",
        "content_variables": '{"1": "Business cards", "2": "token"}',
    }
