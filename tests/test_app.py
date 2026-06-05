from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.config import Settings, get_settings
from app.dependencies import get_attachment_store, get_relay_service, get_repository, get_sender
from app.main import create_app
from app.services.relay import RelayService
from tests.fakes import FakeAttachmentStore, FakeRepository, FakeSender


def make_client(
    *, verify_twilio_signature: bool = False, twilio_auth_token: str = "", admin_password: str = ""
) -> tuple[TestClient, FakeRepository, FakeSender]:
    settings = Settings(
        FRANCISCO_PHONE="+15551234567",
        MAYA_BUSINESS_NUMBER="+13852208404",
        VERIFY_TWILIO_SIGNATURE=verify_twilio_signature,
        ENABLE_AI_TRIAGE=False,
        OPENAI_API_KEY="",
        OPENAI_MODEL="gpt-5-mini",
        ADMIN_PASSWORD=admin_password,
        TWILIO_ACCOUNT_SID="",
        TWILIO_AUTH_TOKEN=twilio_auth_token,
        TWILIO_MESSAGING_SERVICE_SID="",
        SUPABASE_URL="",
        SUPABASE_SERVICE_ROLE_KEY="",
    )
    repository = FakeRepository()
    sender = FakeSender()
    attachment_store = FakeAttachmentStore()
    app = create_app()

    def relay_override() -> RelayService:
        return RelayService(settings=settings, repository=repository, sender=sender)

    app.dependency_overrides[get_relay_service] = relay_override
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_sender] = lambda: sender
    app.dependency_overrides[get_attachment_store] = lambda: attachment_store
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
            "enable_twilio_lookup": False,
            "enable_ai_triage": False,
            "openai_api_key": True,
            "openai_model": True,
            "twilio_account_sid": False,
            "twilio_auth_token": False,
            "twilio_messaging_service_sid": False,
            "maya_business_number": True,
            "francisco_phone": True,
            "francisco_phone_is_not_maya_number": True,
            "employee_phones": True,
            "supabase_url": False,
            "supabase_service_role_key": False,
            "supabase_key_role": None,
        },
    }


def test_readiness_rejects_francisco_phone_matching_maya_number():
    client, _, _ = make_client()
    settings = Settings(
        FRANCISCO_PHONE="+13852208404",
        MAYA_BUSINESS_NUMBER="+13852208404",
        VERIFY_TWILIO_SIGNATURE=False,
    )
    client.app.dependency_overrides[get_settings] = lambda: settings

    response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json()["status"] == "missing_config"
    assert response.json()["checks"]["francisco_phone_is_not_maya_number"] is False


def test_supabase_readiness_reports_ok_when_repository_is_accessible():
    client, _, _ = make_client()

    response = client.get("/readiness/supabase")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_admin_is_hidden_when_password_is_not_configured():
    client, _, _ = make_client()

    response = client.get("/admin")

    assert response.status_code == 404


def test_admin_login_and_conversations_page():
    client, repository, sender = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    repository.create_message(
        conversation_id="conversation-1",
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+13852208404",
        body="Necesito cotización",
    )
    repository.create_message(
        conversation_id="conversation-1",
        direction="system",
        from_phone="+13852208404",
        to_phone="+15551234567",
        body=(
            "Reply with #C0001 your message\n"
            "---\n"
            "AI note:\n"
            "Intent: quote request.\n"
            "---\n"
            "#C0001 Hi! What size and material do you need?"
        ),
    )
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000002",
        assigned_employee="+15551234567",
    )
    repository.create_message(
        conversation_id="conversation-2",
        direction="customer_to_employee",
        from_phone="+15550000002",
        to_phone="+13852208404",
        body="Are you open today?",
    )

    login_page = client.get("/admin")
    assert login_page.status_code == 200
    assert "Admin password" in login_page.text

    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    assert login.status_code == 303
    cookie = login.headers["set-cookie"]

    dashboard = client.get("/admin", headers={"cookie": cookie})
    assert dashboard.status_code == 200
    assert "Logout" in dashboard.text
    assert "Open conversations" in dashboard.text
    assert "#C0001" in dashboard.text
    assert "Reply with #C0001 your message" in dashboard.text

    search = client.get("/admin?q=cotización", headers={"cookie": cookie})
    assert search.status_code == 200
    assert "1 of 2 conversations" in search.text
    assert "#C0001" in search.text
    assert "Are you open today?" not in search.text
    assert "href='/admin'>Clear</a>" in search.text

    detail = client.get("/admin/conversations/conversation-1", headers={"cookie": cookie})
    assert detail.status_code == 200
    assert "Reply to customer" in detail.text
    assert "Hi! What size and material do you need?" in detail.text
    assert "#C0001 Hi! What size and material do you need?" in detail.text

    send_reply = client.post(
        "/admin/conversations/conversation-1/reply",
        data={"reply_body": "We are open today until 6 PM."},
        headers={"cookie": cookie},
        follow_redirects=False,
    )
    assert send_reply.status_code == 303
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "body": "We are open today until 6 PM.",
    }
    assert repository.messages[-1]["direction"] == "employee_to_customer"
    assert repository.messages[-1]["twilio_message_sid"] == "SMfake1"

    send_file_reply = client.post(
        "/admin/conversations/conversation-1/reply",
        data={"reply_body": "Please review this proof."},
        files=[("reply_files", ("proof.pdf", b"fake pdf", "application/pdf"))],
        headers={"cookie": cookie},
        follow_redirects=False,
    )
    assert send_file_reply.status_code == 303
    assert sender.sent_messages[-1] == {
        "sid": "SMfake2",
        "to_phone": "+15550000001",
        "body": (
            "Please review this proof.\n"
            "Attachment 1 (application/pdf): "
            "https://files.example/admin-replies/conversation-1/proof.pdf"
        ),
    }
    assert repository.messages[-1]["num_media"] == 1
    assert repository.messages[-1]["media_urls"] == (
        "https://files.example/admin-replies/conversation-1/proof.pdf",
    )
    assert repository.attachments[-1]["public_url"] == (
        "https://files.example/admin-replies/conversation-1/proof.pdf"
    )

    send_image_reply = client.post(
        "/admin/conversations/conversation-1/reply",
        data={"reply_body": "Please review this image."},
        files=[("reply_files", ("proof.jpg", b"fake jpg", "image/jpeg"))],
        headers={"cookie": cookie},
        follow_redirects=False,
    )
    assert send_image_reply.status_code == 303
    assert sender.sent_messages[-1] == {
        "sid": "SMfake3",
        "to_phone": "+15550000001",
        "body": "Please review this image.",
        "media_urls": ("https://files.example/admin-replies/conversation-1/proof.jpg",),
    }
    assert repository.messages[-1]["media_urls"] == (
        "https://files.example/admin-replies/conversation-1/proof.jpg",
    )

    logout = client.get("/admin/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert "maya_admin" in logout.headers["set-cookie"]


def test_admin_reply_uses_conversation_customer_channel():
    client, repository, sender = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )

    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]
    send_reply = client.post(
        "/admin/conversations/conversation-1/reply",
        data={"reply_body": "Replying through WhatsApp."},
        headers={"cookie": cookie},
        follow_redirects=False,
    )

    assert send_reply.status_code == 303
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "body": "Replying through WhatsApp.",
        "channel": "whatsapp",
    }


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


def test_twilio_sms_webhook_parses_media_fields():
    client, repository, sender = make_client()

    response = client.post(
        "/webhooks/twilio/sms",
        data={
            "MessageSid": "SMinbound",
            "From": "+15550000001",
            "To": "+13852208404",
            "Body": "See attached",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/image.jpg",
            "MediaContentType0": "image/jpeg",
        },
    )

    assert response.status_code == 200
    assert repository.messages[0]["num_media"] == 1
    assert repository.messages[0]["media_urls"] == ("https://api.twilio.com/media/image.jpg",)
    assert repository.messages[0]["media_content_types"] == ("image/jpeg",)
    assert "Attachment 1 (image/jpeg)" not in sender.sent_messages[0]["body"]
    assert sender.sent_messages[0]["media_urls"] == ("https://api.twilio.com/media/image.jpg",)


def test_twilio_whatsapp_webhook_normalizes_channel_addresses():
    client, repository, sender = make_client()

    response = client.post(
        "/webhooks/twilio/whatsapp",
        data={
            "MessageSid": "WMinbound",
            "From": "whatsapp:+15550000001",
            "To": "whatsapp:+13852208404",
            "Body": "Hola por WhatsApp",
            "NumMedia": "0",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/xml")
    assert repository.conversations[0].customer_channel == "whatsapp"
    assert repository.messages[0]["from_phone"] == "+15550000001"
    assert repository.messages[0]["to_phone"] == "+13852208404"
    assert sender.sent_messages[0]["to_phone"] == "+15551234567"
    assert "Hola por WhatsApp" in sender.sent_messages[0]["body"]


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
    assert repository.conversations[0].customer_channel == "sms"
    assert sender.sent_messages[0]["to_phone"] == "+15551234567"


def test_signed_whatsapp_webhook_uses_forwarded_public_url_for_validation():
    client, repository, sender = make_client(verify_twilio_signature=True, twilio_auth_token="token")
    url = "https://maya-relay-production.up.railway.app/webhooks/twilio/whatsapp"
    data = {
        "MessageSid": "WMinbound",
        "From": "whatsapp:+15550000001",
        "To": "whatsapp:+13852208404",
        "Body": "Need a quote on WhatsApp",
        "NumMedia": "0",
    }
    signature = RequestValidator("token").compute_signature(url, data)

    response = client.post(
        "/webhooks/twilio/whatsapp",
        data=data,
        headers={
            "X-Twilio-Signature": signature,
            "x-forwarded-proto": "https",
            "x-forwarded-host": "maya-relay-production.up.railway.app",
        },
    )

    assert response.status_code == 200
    assert len(repository.messages) == 2
    assert repository.conversations[0].customer_channel == "whatsapp"
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
