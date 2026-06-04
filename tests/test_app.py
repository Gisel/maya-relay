from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.config import Settings, get_settings
from app.dependencies import get_relay_service, get_repository
from app.main import create_app
from app.services.relay import RelayService
from tests.fakes import FakeRepository, FakeSender


def make_client(
    *, verify_twilio_signature: bool = False, twilio_auth_token: str = ""
) -> tuple[TestClient, FakeRepository, FakeSender]:
    settings = Settings(
        FRANCISCO_PHONE="+15551234567",
        MAYA_BUSINESS_NUMBER="+13852208404",
        VERIFY_TWILIO_SIGNATURE=verify_twilio_signature,
        TWILIO_ACCOUNT_SID="",
        TWILIO_AUTH_TOKEN=twilio_auth_token,
        TWILIO_MESSAGING_SERVICE_SID="",
        SUPABASE_URL="",
        SUPABASE_SERVICE_ROLE_KEY="",
    )
    repository = FakeRepository()
    sender = FakeSender()
    app = create_app()

    def relay_override() -> RelayService:
        return RelayService(settings=settings, repository=repository, sender=sender)

    app.dependency_overrides[get_relay_service] = relay_override
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app), repository, sender


def test_health():
    client, _, _ = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_required_config_presence():
    client, _, _ = make_client()

    response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "missing_config",
        "checks": {
            "verify_twilio_signature": False,
            "twilio_account_sid": False,
            "twilio_auth_token": False,
            "twilio_messaging_service_sid": False,
            "maya_business_number": True,
            "francisco_phone": True,
            "supabase_url": False,
            "supabase_service_role_key": False,
        },
    }


def test_supabase_readiness_reports_ok_when_repository_is_accessible():
    client, _, _ = make_client()

    response = client.get("/readiness/supabase")

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


def test_unsigned_sms_webhook_is_rejected_when_signature_validation_is_enabled():
    client, repository, sender = make_client(verify_twilio_signature=True)

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

    assert response.status_code == 403
    assert response.text == "Forbidden"
    assert repository.messages == []
    assert sender.sent_messages == []


def test_signed_sms_webhook_uses_forwarded_public_url_for_validation():
    client, repository, sender = make_client(verify_twilio_signature=True, twilio_auth_token="token")
    url = "https://maya-relay-production.up.railway.app/webhooks/twilio/sms"
    data = {
        "MessageSid": "SMinbound",
        "From": "+15550000001",
        "To": "+13852208404",
        "Body": "Need a quote",
        "NumMedia": "0",
    }
    signature = RequestValidator("token").compute_signature(url, data)

    response = client.post(
        "/webhooks/twilio/sms",
        data=data,
        headers={
            "X-Twilio-Signature": signature,
            "x-forwarded-proto": "https",
            "x-forwarded-host": "maya-relay-production.up.railway.app",
        },
    )

    assert response.status_code == 200
    assert len(repository.messages) == 2
    assert sender.sent_messages[0]["to_phone"] == "+15551234567"


def test_unsigned_status_callback_is_rejected_when_signature_validation_is_enabled():
    client, repository, _ = make_client(verify_twilio_signature=True)

    response = client.post(
        "/webhooks/twilio/status",
        data={
            "MessageSid": "SMoutbound",
            "MessageStatus": "delivered",
        },
    )

    assert response.status_code == 403
    assert response.text == "Forbidden"
    assert repository.status_updates == []
