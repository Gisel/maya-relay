from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_relay_service, get_repository
from app.main import create_app
from app.services.relay import RelayService
from tests.fakes import FakeRepository, FakeSender


def make_client() -> tuple[TestClient, FakeRepository, FakeSender]:
    settings = Settings(
        FRANCISCO_PHONE="+15551234567",
        MAYA_BUSINESS_NUMBER="+13852208404",
        VERIFY_TWILIO_SIGNATURE=False,
    )
    repository = FakeRepository()
    sender = FakeSender()
    app = create_app()

    def relay_override() -> RelayService:
        return RelayService(settings=settings, repository=repository, sender=sender)

    app.dependency_overrides[get_relay_service] = relay_override
    app.dependency_overrides[get_repository] = lambda: repository
    return TestClient(app), repository, sender


def test_health():
    client, _, _ = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_twilio_sms_webhook_acknowledges_with_empty_twiml():
    client, repository, sender = make_client()

    response = client.post(
        "/webhooks/twilio/sms",
        data={
            "MessageSid": "SMinbound",
            "From": "+15550000001",
            "To": "+13852208404",
            "Body": "Need a quote",
            "NumMedia": "0",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/xml")
    assert "<Response" in response.text
    assert len(repository.conversations) == 1
    assert sender.sent_messages[0]["to_phone"] == "+15551234567"


def test_status_callback_updates_message_status():
    client, repository, _ = make_client()

    response = client.post(
        "/webhooks/twilio/status",
        data={
            "MessageSid": "SMoutbound",
            "MessageStatus": "delivered",
        },
    )

    assert response.status_code == 204
    assert repository.status_updates == [
        {
            "twilio_message_sid": "SMoutbound",
            "status": "delivered",
            "error_code": None,
            "error_message": None,
        }
    ]

