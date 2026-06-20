from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from fastapi import HTTPException
from twilio.request_validator import RequestValidator

from app.config import Settings, get_settings
from app.dependencies import (
    get_attachment_store,
    get_message_triage,
    get_operator_auth_service,
    get_relay_service,
    get_repository,
    get_sender,
    get_voice_caller,
)
from app.main import create_app
from app.operator_auth import MayaOperatorAuthService
from app.services.relay import RelayService
from tests.fakes import FakeAttachmentStore, FakeOperatorAuthService, FakeRepository, FakeSender, FakeTriage, FakeVoiceCaller


PROOF_PDF_BYTES = b"%PDF-1.4\nfake proof"


def make_client(
    *,
    verify_twilio_signature: bool = False,
    twilio_account_sid: str = "",
    twilio_auth_token: str = "",
    admin_password: str = "",
    app_base_url: str = "https://maya-relay.example",
    assemblyai_api_key: str = "",
    openai_api_key: str = "",
    whatsapp_template_proof_ready_content_sid: str = "",
    whatsapp_template_assets_needed_content_sid: str = "",
    whatsapp_template_new_customer_intro_content_sid: str = "",
    whatsapp_template_quote_follow_up_content_sid: str = "",
    whatsapp_template_pickup_reminder_content_sid: str = "",
    whatsapp_template_payment_reminder_content_sid: str = "",
    whatsapp_template_owner_message_content_sid: str = "",
    message_triage: FakeTriage | None = None,
    operator_auth: FakeOperatorAuthService | None = None,
) -> tuple[TestClient, FakeRepository, FakeSender]:
    settings = Settings(
        FRANCISCO_PHONE="+15551234567",
        MAYA_BUSINESS_NUMBER="+13852208404",
        VERIFY_TWILIO_SIGNATURE=verify_twilio_signature,
        ENABLE_AI_TRIAGE=False,
        OPENAI_API_KEY=openai_api_key,
        OPENAI_MODEL="gpt-5-mini",
        ASSEMBLYAI_API_KEY=assemblyai_api_key,
        ADMIN_PASSWORD=admin_password,
        AUTH_SESSION_SECRET="test-session-secret",
        TWILIO_ACCOUNT_SID=twilio_account_sid,
        TWILIO_AUTH_TOKEN=twilio_auth_token,
        TWILIO_MESSAGING_SERVICE_SID="",
        SUPABASE_URL="",
        SUPABASE_SERVICE_ROLE_KEY="",
        APP_BASE_URL=app_base_url,
        CUSTOMER_ACTION_TOKEN_SECRET="test-action-secret",
        WHATSAPP_TEMPLATE_PROOF_READY_CONTENT_SID=whatsapp_template_proof_ready_content_sid,
        WHATSAPP_TEMPLATE_ASSETS_NEEDED_CONTENT_SID=whatsapp_template_assets_needed_content_sid,
        WHATSAPP_TEMPLATE_NEW_CUSTOMER_INTRO_CONTENT_SID=whatsapp_template_new_customer_intro_content_sid,
        WHATSAPP_TEMPLATE_QUOTE_FOLLOW_UP_CONTENT_SID=whatsapp_template_quote_follow_up_content_sid,
        WHATSAPP_TEMPLATE_PICKUP_REMINDER_CONTENT_SID=whatsapp_template_pickup_reminder_content_sid,
        WHATSAPP_TEMPLATE_PAYMENT_REMINDER_CONTENT_SID=whatsapp_template_payment_reminder_content_sid,
        WHATSAPP_TEMPLATE_OWNER_MESSAGE_CONTENT_SID=whatsapp_template_owner_message_content_sid,
    )
    repository = FakeRepository()
    sender = FakeSender()
    voice_caller = FakeVoiceCaller()
    attachment_store = FakeAttachmentStore()
    app = create_app()

    def relay_override() -> RelayService:
        return RelayService(settings=settings, repository=repository, sender=sender)

    app.dependency_overrides[get_relay_service] = relay_override
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_sender] = lambda: sender
    app.dependency_overrides[get_voice_caller] = lambda: voice_caller
    app.dependency_overrides[get_attachment_store] = lambda: attachment_store
    if operator_auth is not None:
        app.dependency_overrides[get_operator_auth_service] = lambda: operator_auth
    if message_triage is not None:
        app.dependency_overrides[get_message_triage] = lambda: message_triage
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.fake_voice_caller = voice_caller
    return TestClient(app), repository, sender


def test_health():
    client, _, _ = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_app():
    client, _, _ = make_client()

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app"


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
    assert "Reply with #C0001 your message" not in dashboard.text

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
    image_detail = client.get("/admin/conversations/conversation-1", headers={"cookie": cookie})
    assert "class='media media-preview'" in image_detail.text
    assert "<img src='https://files.example/admin-replies/conversation-1/proof.jpg'" in image_detail.text

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


def test_api_requires_admin_session():
    client, _, _ = make_client(admin_password="secret")

    response = client.get("/api/conversations")

    assert response.status_code == 401


def test_api_json_login_and_logout():
    client, _, _ = make_client(admin_password="secret")

    bad_login = client.post("/api/auth/login", json={"password": "wrong"})
    assert bad_login.status_code == 401

    login = client.post("/api/auth/login", json={"password": "secret"})
    assert login.status_code == 200
    assert login.json() == {"authenticated": True}
    cookie = login.headers["set-cookie"]

    me = client.get("/api/me", headers={"cookie": cookie})
    assert me.status_code == 200
    assert me.json()["session"]["cookieName"] == "maya_admin"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"authenticated": False}
    assert "maya_admin" in logout.headers["set-cookie"]


def test_api_operator_login_returns_profile_and_me():
    operator_auth = FakeOperatorAuthService()
    operator_auth.add_operator(
        email="signs@mayagraphics.test",
        password="safe-password",
        display_name="Signs Desk",
        routing_line="signs",
        click_to_call_phone="+15557654321",
    )
    client, _, _ = make_client(admin_password="legacy-secret", operator_auth=operator_auth)

    bad_login = client.post(
        "/api/auth/login",
        json={"email": "signs@mayagraphics.test", "password": "wrong"},
    )
    assert bad_login.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": "signs@mayagraphics.test", "password": "safe-password"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["authenticated"] is True
    assert payload["user"]["email"] == "signs@mayagraphics.test"
    assert payload["user"]["displayName"] == "Signs Desk"
    assert payload["user"]["routingLine"] == "signs"
    assert payload["user"]["clickToCallPhone"] == "+15557654321"

    me = client.get("/api/me", headers={"cookie": login.headers["set-cookie"]})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "signs@mayagraphics.test"


def test_api_operator_login_rejects_inactive_user():
    operator_auth = FakeOperatorAuthService()
    operator_auth.add_operator(email="orders@mayagraphics.test", password="secret", active=False)
    client, _, _ = make_client(admin_password="legacy-secret", operator_auth=operator_auth)

    response = client.post(
        "/api/auth/login",
        json={"email": "orders@mayagraphics.test", "password": "secret"},
    )

    assert response.status_code == 403


def test_api_operator_login_requires_supabase_anon_key_when_using_supabase_auth():
    settings = Settings(
        ADMIN_PASSWORD="legacy-secret",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="service-role",
        SUPABASE_ANON_KEY="",
    )
    service = MayaOperatorAuthService(settings)

    try:
        service.authenticate(email="giselcrystal@gmail.com", password="M4y42026!@")
    except HTTPException as error:
        assert error.status_code == 503
        assert error.detail == "SUPABASE_ANON_KEY is required for operator login."
    else:
        raise AssertionError("expected missing anon key to fail")


def test_api_quick_responses_include_template_mapped_actions():
    client, _, _ = make_client(admin_password="secret")

    unauthenticated = client.get("/api/quick-responses")
    assert unauthenticated.status_code == 401

    login = client.post("/api/auth/login", json={"password": "secret"})
    response = client.get("/api/quick-responses", headers={"cookie": login.headers["set-cookie"]})

    assert response.status_code == 200
    quick_responses = response.json()["quickResponses"]
    response_by_id = {item["id"]: item for item in quick_responses}

    assert "proof_approval" not in response_by_id
    assert "whatsapp_proof_ready" not in response_by_id
    assert response_by_id["missing_job_specs"]["channels"] == ["sms", "whatsapp"]
    assert response_by_id["shop_hours"]["label"] == "Shop hours"
    assert "M-F: 9:00am - 5:30pm | SAT: By Appointment" in response_by_id["shop_hours"]["body"]
    assert response_by_id["maya_owner_message"]["templateKey"] == "owner_message"
    assert response_by_id["maya_owner_message"]["channels"] == ["whatsapp"]
    assert response_by_id["maya_owner_message"]["variables"][0]["contentIndex"] == "1"
    assert response_by_id["maya_new_customer_intro"]["templateKey"] == "new_customer_intro"
    assert response_by_id["maya_quote_follow_up"]["group"] == "template_response"
    assert response_by_id["maya_quote_follow_up"]["channels"] == ["sms", "whatsapp"]
    assert response_by_id["maya_quote_follow_up"]["variables"][0]["defaultSource"] == "customer_name"
    assert response_by_id["maya_pickup_reminder"]["templateKey"] == "pickup_reminder"
    assert response_by_id["maya_payment_reminder"]["templateKey"] == "payment_reminder"


def test_api_send_quick_response_uses_free_form_for_sms():
    client, repository, sender = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/quick-responses/maya_quote_follow_up/send",
        json={"variables": {"customer_name": "Gisel"}, "client_request_id": "quick-1"},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    assert response.json()["sendMode"] == "free_form"
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "body": "Hi Gisel, following up on your quote request. Reply here with any questions or updates.",
    }
    assert repository.messages[-1]["client_request_id"] == "quick-1"


def test_api_send_quick_response_uses_free_form_for_active_whatsapp_window():
    client, repository, sender = make_client(
        admin_password="secret",
        whatsapp_template_quote_follow_up_content_sid="HXquote",
    )
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )
    repository.create_message(
        conversation_id="conversation-1",
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+15551234567",
        body="Hi",
    )
    repository.messages[-1]["created_at"] = datetime.now(UTC).isoformat()
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/quick-responses/maya_quote_follow_up/send",
        json={"variables": {"customer_name": "Gisel"}, "client_request_id": "quick-1"},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    assert response.json()["sendMode"] == "free_form"
    assert sender.sent_messages[-1]["channel"] == "whatsapp"
    assert "content_sid" not in sender.sent_messages[-1]


def test_api_send_quick_response_uses_template_for_stale_whatsapp_window():
    client, repository, sender = make_client(
        admin_password="secret",
        whatsapp_template_quote_follow_up_content_sid="HXquote",
    )
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )
    repository.create_message(
        conversation_id="conversation-1",
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+15551234567",
        body="Hi",
    )
    repository.messages[-1]["created_at"] = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/quick-responses/maya_quote_follow_up/send",
        json={"variables": {"customer_name": "Gisel"}, "client_request_id": "quick-1"},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    assert response.json()["sendMode"] == "template"
    assert response.json()["templateKey"] == "quote_follow_up"
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "channel": "whatsapp",
        "content_sid": "HXquote",
        "content_variables": {"1": "Gisel"},
    }
    assert repository.messages[-1]["body"] == (
        "Hi Gisel, following up on your quote request. Reply here with any questions or updates."
    )


def test_api_send_quick_response_requires_template_config_outside_whatsapp_window():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/quick-responses/maya_quote_follow_up/send",
        json={"variables": {"customer_name": "Gisel"}, "client_request_id": "quick-1"},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "WHATSAPP_TEMPLATE_QUOTE_FOLLOW_UP_CONTENT_SID must be configured before sending this WhatsApp quick response."
    )


def test_api_starts_sms_conversation_and_sends_first_message():
    client, repository, sender = make_client(admin_password="secret")
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/start",
        json={
            "phone_number": "5550000003",
            "display_name": "New Client",
            "channel": "sms",
            "body": "Hi, this is Maya Graphics following up on your order.",
            "client_request_id": "start-sms-1",
        },
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "sent"
    assert payload["sendMode"] == "free_form"
    assert payload["conversation"]["id"] == "conversation-1"
    assert payload["conversation"]["channel"] == "sms"
    assert payload["conversation"]["customer"]["displayName"] == "New Client"
    assert payload["message"]["body"] == "Hi, this is Maya Graphics following up on your order."
    assert repository.conversations[0].customer_phone == "+15550000003"
    assert repository.conversations[0].customer_channel == "sms"
    assert repository.messages[0]["client_request_id"] == "start-sms-1"
    assert sender.sent_messages == [
        {
            "sid": "SMfake1",
            "to_phone": "+15550000003",
            "body": "Hi, this is Maya Graphics following up on your order.",
        }
    ]


def test_api_start_conversation_is_idempotent_by_client_request_id():
    client, repository, sender = make_client(admin_password="secret")
    login = client.post("/api/auth/login", json={"password": "secret"})
    request_payload = {
        "phone_number": "+15550000003",
        "channel": "sms",
        "body": "Hi from Maya.",
        "client_request_id": "start-sms-1",
    }

    first = client.post(
        "/api/conversations/start",
        json=request_payload,
        headers={"cookie": login.headers["set-cookie"]},
    )
    second = client.post(
        "/api/conversations/start",
        json=request_payload,
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert len(sender.sent_messages) == 1
    assert len(repository.messages) == 1


def test_api_start_whatsapp_conversation_requires_template():
    client, _, _ = make_client(admin_password="secret")
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/start",
        json={
            "phone_number": "+15550000003",
            "channel": "whatsapp",
            "body": "Hi from Maya.",
            "client_request_id": "start-wa-1",
        },
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Starting a WhatsApp conversation requires an approved template."


def test_api_starts_whatsapp_conversation_with_template():
    client, repository, sender = make_client(
        admin_password="secret",
        whatsapp_template_quote_follow_up_content_sid="HXquote",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/start",
        json={
            "phone_number": "+15550000003",
            "display_name": "Gisel",
            "channel": "whatsapp",
            "template_key": "quote_follow_up",
            "variables": {"customer_name": "Gisel"},
            "client_request_id": "start-wa-1",
        },
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "sent"
    assert payload["sendMode"] == "template"
    assert payload["templateKey"] == "quote_follow_up"
    assert payload["contentSid"] == "HXquote"
    assert payload["conversation"]["channel"] == "whatsapp"
    assert repository.conversations[0].customer_channel == "whatsapp"
    assert repository.messages[0]["body"] == (
        "Hi Gisel, following up on your quote request. Reply here with any questions or updates."
    )
    assert sender.sent_messages == [
        {
            "sid": "SMfake1",
            "to_phone": "+15550000003",
            "channel": "whatsapp",
            "content_sid": "HXquote",
            "content_variables": {"1": "Gisel"},
        }
    ]


def test_api_starts_whatsapp_conversation_with_owner_message_template():
    client, repository, sender = make_client(
        admin_password="secret",
        whatsapp_template_owner_message_content_sid="HXowner",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/start",
        json={
            "phone_number": "+15550000003",
            "channel": "whatsapp",
            "template_key": "owner_message",
            "variables": {"message": "Can you send the size, quantity, deadline, and artwork?"},
            "client_request_id": "start-wa-owner-1",
        },
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "sent"
    assert payload["sendMode"] == "template"
    assert payload["templateKey"] == "owner_message"
    assert payload["contentSid"] == "HXowner"
    assert repository.messages[0]["body"] == (
        "Maya Graphics:\nCan you send the size, quantity, deadline, and artwork?"
    )
    assert sender.sent_messages == [
        {
            "sid": "SMfake1",
            "to_phone": "+15550000003",
            "channel": "whatsapp",
            "content_sid": "HXowner",
            "content_variables": {"1": "Can you send the size, quantity, deadline, and artwork?"},
        }
    ]


def test_api_operations_status_reports_recent_message_and_call_issues():
    client, repository, _ = make_client(admin_password="secret")
    repository.update_contact_lookup_name("+15550000001", "Test Customer")
    conversation = repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    repository.create_message(
        conversation_id=conversation.id,
        direction="employee_to_customer",
        from_phone="+13852208404",
        to_phone="+15550000001",
        body="Your proof is ready.",
        twilio_message_sid="SMfailed",
    )
    repository.update_message_status(
        twilio_message_sid="SMfailed",
        status="undelivered",
        error_code="30007",
        error_message="Carrier violation",
    )
    call = repository.create_call(
        conversation_id=conversation.id,
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAmissingRecording",
        status="initiated",
    )
    repository.update_call_status_by_sid(twilio_call_sid=str(call["twilio_call_sid"]), status="completed")

    unauthenticated = client.get("/api/operations/status")
    assert unauthenticated.status_code == 401

    login = client.post("/api/auth/login", json={"password": "secret"})
    response = client.get("/api/operations/status", headers={"cookie": login.headers["set-cookie"]})

    assert response.status_code == 200
    assert response.json()["summary"] == {
        "messageFailures": 1,
        "callAttention": 1,
        "total": 2,
    }
    assert response.json()["messageFailures"][0] == {
        "id": "message-1",
        "conversationId": "conversation-1",
        "conversationCode": "C0001",
        "customerName": "Test Customer",
        "customerPhone": "+15550000001",
        "channel": "sms",
        "direction": "employee_to_customer",
        "bodyPreview": "Your proof is ready.",
        "twilioMessageSid": "SMfailed",
        "deliveryStatus": "undelivered",
        "deliveryErrorCode": "30007",
        "deliveryErrorMessage": "Carrier violation",
        "createdAt": None,
        "hint": "Carrier filtering. Check message wording, sender registration, and recent repeated sends.",
    }
    assert response.json()["callAttention"][0]["kind"] == "recording_missing"
    assert response.json()["callAttention"][0]["conversationCode"] == "C0001"
    assert response.json()["callAttention"][0]["customerName"] == "Test Customer"
    assert response.json()["callAttention"][0]["hint"].startswith("The call completed but no recording is attached yet.")


def test_api_conversation_contract_and_idempotent_reply():
    client, repository, sender = make_client(admin_password="secret")
    repository.update_contact_lookup_name("+15550000001", "GOMEZ, GISEL")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )
    repository.create_message(
        conversation_id="conversation-1",
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+13852208404",
        body="Need a quote for presentation cards",
        num_media=1,
        media_urls=("https://files.example/card.jpg",),
        media_content_types=("image/jpeg",),
    )
    repository.create_message(
        conversation_id="conversation-1",
        direction="system",
        from_phone="+13852208404",
        to_phone="+15551234567",
        body="#C0001 Please send size and quantity.",
    )

    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    me = client.get("/api/me", headers={"cookie": cookie})
    assert me.status_code == 200
    assert me.json()["app"]["name"] == "Maya Relay"

    conversations = client.get("/api/conversations?q=cards", headers={"cookie": cookie})
    assert conversations.status_code == 200
    assert conversations.json()["metrics"]["open"] == 1
    assert conversations.json()["conversations"][0] == {
        "id": "conversation-1",
        "code": "C0001",
        "status": "open",
        "channel": "whatsapp",
        "customer": {
            "phone": "+15550000001",
            "displayName": None,
            "lookupName": "GOMEZ, GISEL",
            "name": "GOMEZ, GISEL",
        },
        "lastMessage": {
            "body": "Need a quote for presentation cards",
            "direction": "customer_to_employee",
            "deliveryStatus": "pending",
            "deliveryErrorCode": None,
            "createdAt": None,
            "hasAttachments": True,
        },
        "updatedAt": "",
    }

    detail = client.get("/api/conversations/conversation-1", headers={"cookie": cookie})
    assert detail.status_code == 200
    assert detail.json()["conversation"]["channel"] == "whatsapp"
    assert detail.json()["suggestedReply"] == "Please send size and quantity."
    assert detail.json()["messages"][0]["attachments"] == [
        {
            "url": "https://files.example/card.jpg",
            "contentType": "image/jpeg",
            "kind": "image",
        }
    ]

    send = client.post(
        "/api/conversations/conversation-1/reply",
        data={"body": "Thanks, please send the size.", "client_request_id": "request-1"},
        headers={"cookie": cookie},
    )
    assert send.status_code == 200
    assert send.json()["status"] == "sent"
    assert send.json()["message"]["clientRequestId"] == "request-1"
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "body": "Thanks, please send the size.",
        "channel": "whatsapp",
    }

    duplicate = client.post(
        "/api/conversations/conversation-1/reply",
        data={"body": "Thanks, please send the size.", "client_request_id": "request-1"},
        headers={"cookie": cookie},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert len(sender.sent_messages) == 1


def test_api_generates_fresh_suggested_reply_for_latest_customer_message():
    triage = FakeTriage(
        "Intent: proof timing question\n"
        "Missing: exact production timing\n"
        "#C0001 Let me confirm the production time for that proof and I will update you here."
    )
    client, repository, _ = make_client(admin_password="secret", message_triage=triage)
    conversation = repository.get_or_create_customer_conversation(
        "+15550000001",
        "+15551234567",
        customer_channel="whatsapp",
    )
    repository.create_message(
        conversation_id=conversation.id,
        direction="employee_to_customer",
        from_phone="+13852208404",
        to_phone="+15550000001",
        body="Your proof is ready. Review here: https://maya-relay.example/proof/token",
    )
    repository.create_message(
        conversation_id=conversation.id,
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+13852208404",
        body="If I approve the proof, how long will it take?",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post(
        f"/api/conversations/{conversation.id}/suggested-reply",
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    assert response.json() == {
        "suggestedReply": "Let me confirm the production time for that proof and I will update you here."
    }
    assert triage.calls == [
        {
            "body": (
                "Maya: Your proof is ready. Review here: https://maya-relay.example/proof/token\n"
                "Customer: If I approve the proof, how long will it take?"
            ),
            "has_attachments": False,
            "conversation_code": "C0001",
        }
    ]


def test_api_suggested_reply_returns_empty_when_operator_replied_last():
    triage = FakeTriage("#C0001 This should not be used.")
    client, repository, _ = make_client(admin_password="secret", message_triage=triage)
    conversation = repository.get_or_create_customer_conversation(
        "+15550000001",
        "+15551234567",
        customer_channel="sms",
    )
    repository.create_message(
        conversation_id=conversation.id,
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+13852208404",
        body="Can you quote business cards?",
    )
    repository.create_message(
        conversation_id=conversation.id,
        direction="employee_to_customer",
        from_phone="+13852208404",
        to_phone="+15550000001",
        body="Sure, please send the quantity and finish.",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post(
        f"/api/conversations/{conversation.id}/suggested-reply",
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    assert response.json() == {"suggestedReply": ""}
    assert triage.calls == []


def test_api_suggested_reply_requires_admin_session():
    client, repository, _ = make_client(admin_password="secret", message_triage=FakeTriage("#C0001 Hello."))
    conversation = repository.get_or_create_customer_conversation("+15550000001", "+15551234567")

    response = client.post(f"/api/conversations/{conversation.id}/suggested-reply")

    assert response.status_code == 401


def test_api_search_checks_beyond_first_conversation_page():
    client, repository, _ = make_client(admin_password="secret")
    for index in range(55):
        phone = f"+1555000{index:04d}"
        repository.get_or_create_customer_conversation(
            customer_phone=phone,
            assigned_employee="+15551234567",
        )
        repository.create_message(
            conversation_id=f"conversation-{index + 1}",
            direction="customer_to_employee",
            from_phone=phone,
            to_phone="+13852208404",
            body="General quote request",
        )
    repository.upsert_contact_display_name("+15550000054", "Legacy Client")

    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.get("/api/conversations?q=legacy", headers={"cookie": cookie})

    assert response.status_code == 200
    assert [conversation["id"] for conversation in response.json()["conversations"]] == ["conversation-55"]


def test_api_status_filter_checks_before_conversation_pagination():
    client, repository, _ = make_client(admin_password="secret")
    closed = repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    repository.update_conversation_status(closed.id, "closed")
    for index in range(55):
        repository.get_or_create_customer_conversation(
            customer_phone=f"+1555001{index:04d}",
            assigned_employee="+15551234567",
        )

    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.get("/api/conversations?status=closed", headers={"cookie": cookie})

    assert response.status_code == 200
    assert [conversation["id"] for conversation in response.json()["conversations"]] == [closed.id]


def test_api_reply_uploads_image_as_media():
    client, repository, sender = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post(
        "/api/conversations/conversation-1/reply",
        data={"body": "Please review.", "client_request_id": "image-request-1"},
        files=[("reply_files", ("proof.jpg", b"fake jpg", "image/jpeg"))],
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "body": "Please review.",
        "media_urls": ("https://files.example/api-replies/conversation-1/proof.jpg",),
    }
    assert response.json()["message"]["attachments"] == [
        {
            "url": "https://files.example/api-replies/conversation-1/proof.jpg",
            "contentType": "image/jpeg",
            "kind": "image",
        }
    ]


def test_api_updates_conversation_status():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.patch(
        "/api/conversations/conversation-1",
        json={"status": "closed"},
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    assert response.json()["conversation"]["status"] == "closed"
    assert repository.conversations[0].status == "closed"


def test_api_conversation_detail_includes_call_history():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="conversation_call",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAfake1",
        status="completed",
    )
    repository.calls[0]["started_at"] = "2026-06-08T20:08:45Z"
    repository.calls[0]["answered_at"] = "2026-06-08T20:08:49Z"
    repository.calls[0]["completed_at"] = "2026-06-08T20:09:28Z"
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.get("/api/conversations/conversation-1", headers={"cookie": cookie})

    assert response.status_code == 200
    calls = response.json()["calls"]
    assert len(calls) == 1
    call = calls[0]
    assert call["id"] == "call-1"
    assert call["conversationId"] == "conversation-1"
    assert call["direction"] == "outbound"
    assert call["callType"] == "conversation_call"
    assert call["customerPhone"] == "+15550000001"
    assert call["employeePhone"] == "+15551234567"
    assert call["twilioCallSid"] == "CAfake1"
    assert call["status"] == "completed"
    assert call["outcome"] is None
    assert call["followUpStatus"] == "none"
    assert call["recordingSid"] is None
    assert call["recordingUrl"] is None
    assert call["recordingStatus"] is None
    assert call["recordingDurationSeconds"] is None
    assert call["recordingChannels"] is None
    assert call["startedAt"] == "2026-06-08T20:08:45Z"
    assert call["answeredAt"] == "2026-06-08T20:08:49Z"
    assert call["completedAt"] == "2026-06-08T20:09:28Z"


def test_api_calls_groups_by_conversation_and_filters_direction_search_and_pagination():
    client, repository, _ = make_client(admin_password="secret")
    repository.upsert_contact_display_name("+15550000001", "Maya Client")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="conversation_call",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAold",
        status="completed",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="manual_outbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAnew",
        status="completed",
    )
    repository.create_call(
        conversation_id=None,
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000002",
        employee_phone="+15551234567",
        twilio_call_sid="CAin",
        status="completed",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    outgoing = client.get("/api/calls?direction=outgoing&q=maya&limit=1", headers={"cookie": cookie})

    assert outgoing.status_code == 200
    payload = outgoing.json()
    assert payload["pagination"]["hasMore"] is False
    assert len(payload["calls"]) == 1
    row = payload["calls"][0]
    assert row["id"] == "conversation-1"
    assert row["customer"]["name"] == "Maya Client"
    assert row["conversation"]["code"] == "C0001"
    assert row["latestCall"]["id"] == "call-2"
    assert row["callCount"] == 2

    incoming = client.get("/api/calls?direction=incoming", headers={"cookie": cookie})

    assert incoming.status_code == 200
    assert [row["latestCall"]["direction"] for row in incoming.json()["calls"]] == ["inbound"]

    paged = client.get("/api/calls?direction=all&limit=1", headers={"cookie": cookie})

    assert paged.status_code == 200
    assert paged.json()["pagination"]["hasMore"] is True
    assert paged.json()["pagination"]["nextOffset"] == 1


def test_api_contacts_requires_auth():
    client, _, _ = make_client(admin_password="secret")

    response = client.get("/api/contacts")

    assert response.status_code == 401


def test_api_contacts_searches_and_returns_profile_hints():
    client, repository, _ = make_client(admin_password="secret")
    repository.upsert_contact_display_name("+15550000001", "Maria Lopez")
    repository.update_contact_profile(
        contact_id="contact-1",
        display_name="Maria Lopez",
        notes="Prefers pickup reminders.",
    )
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="conversation_call",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAcontact",
        status="completed",
    )
    repository.upsert_contact_display_name("+15550000002", "Other Client")
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.get("/api/contacts?q=pickup&limit=10", headers={"cookie": cookie})

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"] == {
        "limit": 10,
        "offset": 0,
        "nextOffset": None,
        "hasMore": False,
    }
    assert payload["items"] == [
        {
            "id": "contact-1",
            "phone": "+15550000001",
            "displayName": "Maria Lopez",
            "lookupName": None,
            "name": "Maria Lopez",
            "notes": "Prefers pickup reminders.",
            "lastActivityAt": repository.calls[0]["created_at"],
            "openConversationId": "conversation-1",
            "lastConversationId": "conversation-1",
            "latestCallId": "call-1",
        }
    ]


def test_api_updates_contact_profile():
    client, repository, _ = make_client(admin_password="secret")
    repository.update_contact_lookup_name("+15550000001", "Lookup Name")
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.patch(
        "/api/contacts/contact-1",
        json={"displayName": "Manual Name", "notes": "Likes proofs by text."},
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    assert response.json()["contact"] == {
        "id": "contact-1",
        "phone": "+15550000001",
        "displayName": "Manual Name",
        "lookupName": "Lookup Name",
        "name": "Manual Name",
        "notes": "Likes proofs by text.",
    }
    assert repository.contacts[0].display_name == "Manual Name"
    assert repository.contacts[0].lookup_name == "Lookup Name"
    assert repository.contacts[0].notes == "Likes proofs by text."


def test_api_contact_patch_preserves_omitted_fields():
    client, repository, _ = make_client(admin_password="secret")
    repository.upsert_contact_display_name("+15550000001", "Manual Name")
    repository.update_contact_profile(
        contact_id="contact-1",
        display_name="Manual Name",
        notes="Original notes.",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.patch(
        "/api/contacts/contact-1",
        json={"notes": "Updated notes."},
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    assert response.json()["contact"]["displayName"] == "Manual Name"
    assert response.json()["contact"]["notes"] == "Updated notes."


def test_api_import_contacts_requires_auth():
    client, _, _ = make_client(admin_password="secret")

    response = client.post(
        "/api/contacts/import",
        files={"file": ("contacts.csv", b"phone_number,display_name\n+15550000001,Maria\n", "text/csv")},
    )

    assert response.status_code == 401


def test_api_import_contacts_creates_updates_skips_and_reports_invalid_rows():
    client, repository, _ = make_client(admin_password="secret")
    repository.update_contact_lookup_name("+15550000001", "Lookup One")
    repository.upsert_contact_display_name("+15550000002", "Existing Manual")
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post(
        "/api/contacts/import",
        files={
            "file": (
                "contacts.csv",
                (
                    "phone_number,display_name\n"
                    "+15550000001,Imported One\n"
                    "+15550000002,Should Not Replace\n"
                    "(555) 000-0003,Imported Three\n"
                    "+15550000004,\n"
                ).encode("utf-8"),
                "text/csv",
            )
        },
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    assert response.json() == {
        "created": 1,
        "updated": 1,
        "skipped": 1,
        "invalidRows": [
            {
                "row": 5,
                "code": "missing_display_name",
                "message": "Display name is required.",
            }
        ],
    }
    assert repository.get_contact("+15550000001").display_name == "Imported One"
    assert repository.get_contact("+15550000001").lookup_name == "Lookup One"
    assert repository.get_contact("+15550000002").display_name == "Existing Manual"
    assert repository.get_contact("+15550000003").display_name == "Imported Three"


def test_api_import_contacts_overwrites_when_explicit():
    client, repository, _ = make_client(admin_password="secret")
    repository.upsert_contact_display_name("+15550000001", "Existing Manual")
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post(
        "/api/contacts/import",
        data={"overwrite": "true"},
        files={"file": ("contacts.csv", b"phone_number,display_name\n+15550000001,Imported Name\n", "text/csv")},
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    assert response.json()["updated"] == 1
    assert repository.get_contact("+15550000001").display_name == "Imported Name"


def test_api_import_contacts_rejects_missing_columns():
    client, _, _ = make_client(admin_password="secret")
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post(
        "/api/contacts/import",
        files={"file": ("contacts.csv", b"phone,name\n+15550000001,Maria\n", "text/csv")},
        headers={"cookie": cookie},
    )

    assert response.status_code == 400
    assert response.json()["detail"][0]["code"] == "missing_columns"


def test_imported_contact_name_is_used_before_lookup_name_in_conversations():
    client, repository, _ = make_client(admin_password="secret")
    repository.update_contact_lookup_name("+15550000001", "Lookup Name")
    repository.import_contact_display_name(phone_number="+15550000001", display_name="Imported Name")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    repository.create_message(
        conversation_id="conversation-1",
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+13852208404",
        body="Hello",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.get("/api/conversations", headers={"cookie": cookie})

    assert response.status_code == 200
    customer = response.json()["conversations"][0]["customer"]
    assert customer["displayName"] == "Imported Name"
    assert customer["lookupName"] == "Lookup Name"
    assert customer["name"] == "Imported Name"


def test_api_update_contact_returns_404_for_missing_contact():
    client, _, _ = make_client(admin_password="secret")
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.patch(
        "/api/contacts/missing",
        json={"displayName": "Missing", "notes": "No row."},
        headers={"cookie": cookie},
    )

    assert response.status_code == 404


def test_api_updates_call_details():
    client, repository, _ = make_client(admin_password="secret")
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="conversation_call",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAfake1",
        status="completed",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.patch(
        "/api/calls/call-1",
        json={
            "outcome": "connected",
            "follow_up_status": "needed",
            "notes": "Customer wants a quote.",
            "recap": "Discussed print timing.",
            "transcription": "Transcript placeholder.",
        },
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    payload = response.json()["call"]
    assert payload["outcome"] == "connected"
    assert payload["followUpStatus"] == "needed"
    assert payload["notes"] == "Customer wants a quote."
    assert payload["recap"] == "Discussed print timing."
    assert payload["transcription"] == "Transcript placeholder."
    assert repository.calls[0]["outcome"] == "connected"


def test_api_streams_call_recording_through_twilio_proxy(monkeypatch):
    client, repository, _ = make_client(
        admin_password="secret",
        twilio_account_sid="ACfake",
        twilio_auth_token="token",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAfake1",
        status="completed",
    )
    repository.calls[0]["recording_url"] = "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/REfake1"
    repository.calls[0]["recording_status"] = "completed"
    calls: list[dict[str, object]] = []

    class FakeResponse:
        content = b"fake audio"
        headers = {"content-type": "audio/mpeg"}

        def raise_for_status(self):
            return None

    def fake_get(url, auth=None, timeout=None, headers=None):
        calls.append({"url": url, "auth": auth, "timeout": timeout, "headers": headers})
        return FakeResponse()

    monkeypatch.setattr("app.routes.api.requests.get", fake_get)
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.get("/api/calls/call-1/recording", headers={"cookie": cookie})

    assert response.status_code == 200
    assert response.content == b"fake audio"
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert calls == [
        {
            "url": "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/REfake1.mp3",
            "auth": ("ACfake", "token"),
            "timeout": 30,
            "headers": None,
        }
    ]


def test_api_transcribes_call_recording_and_saves_text(monkeypatch):
    client, repository, _ = make_client(
        admin_password="secret",
        twilio_account_sid="ACfake",
        twilio_auth_token="token",
        assemblyai_api_key="assembly-key",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAfake1",
        status="completed",
    )
    repository.calls[0]["recording_url"] = "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/REfake1"

    class FakeAudioResponse:
        content = b"fake audio"
        headers = {"content-type": "audio/mpeg"}

        def raise_for_status(self):
            return None

    class FakeJsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, auth=None, timeout=None, headers=None):
        if auth:
            return FakeAudioResponse()
        assert url == "https://api.assemblyai.com/v2/transcript/transcript-1"
        assert headers == {"Authorization": "assembly-key"}
        return FakeJsonResponse({"status": "completed", "text": "Please call me back about the order."})

    def fake_post(url, headers=None, data=None, json=None, timeout=None):
        if url == "https://api.assemblyai.com/v2/upload":
            assert headers == {"Authorization": "assembly-key"}
            assert data == b"fake audio"
            return FakeJsonResponse({"upload_url": "https://assembly.example/upload/audio"})
        assert url == "https://api.assemblyai.com/v2/transcript"
        assert headers == {"Authorization": "assembly-key", "Content-Type": "application/json"}
        assert json == {
            "audio_url": "https://assembly.example/upload/audio",
            "speech_models": ["universal-3-pro", "universal-2"],
        }
        return FakeJsonResponse({"id": "transcript-1"})

    monkeypatch.setattr("app.routes.api.requests.get", fake_get)
    monkeypatch.setattr("app.routes.api.requests.post", fake_post)
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post("/api/calls/call-1/transcribe", headers={"cookie": cookie})

    assert response.status_code == 200
    assert response.json()["call"]["transcription"] == "Please call me back about the order."
    assert repository.calls[0]["transcription"] == "Please call me back about the order."


def test_api_generates_call_recap_from_transcription(monkeypatch):
    client, repository, _ = make_client(admin_password="secret", openai_api_key="openai-key")
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAfake1",
        status="completed",
    )
    repository.calls[0]["transcription"] = "I need flyers ready for pickup this Friday."

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.openai.com/v1/responses"
        assert headers == {
            "Authorization": "Bearer openai-key",
            "Content-Type": "application/json",
        }
        assert json["model"] == "gpt-5-mini"
        assert "I need flyers ready for pickup this Friday." in json["input"]
        assert timeout == 20

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"output_text": "- Customer needs flyers ready for Friday pickup.\n- Confirm quantity and file details."}

        return FakeResponse()

    monkeypatch.setattr("app.routes.api.requests.post", fake_post)
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post("/api/calls/call-1/recap", headers={"cookie": cookie})

    assert response.status_code == 200
    assert response.json()["call"]["recap"] == "- Customer needs flyers ready for Friday pickup.\n- Confirm quantity and file details."
    assert repository.calls[0]["recap"] == "- Customer needs flyers ready for Friday pickup.\n- Confirm quantity and file details."


def test_api_requires_transcription_before_call_recap():
    client, repository, _ = make_client(admin_password="secret", openai_api_key="openai-key")
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAfake1",
        status="completed",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post("/api/calls/call-1/recap", headers={"cookie": cookie})

    assert response.status_code == 400
    assert response.json()["detail"] == "Transcription is required before generating a recap."


def test_api_starts_click_to_call_bridge():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="whatsapp:+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post("/api/conversations/conversation-1/call", headers={"cookie": cookie})

    assert response.status_code == 200
    assert response.json() == {
        "status": "calling",
        "callSid": "CAfake1",
        "to": "+15550000001",
        "employeePhone": "+15551234567",
    }
    assert client.app.state.fake_voice_caller.calls == [
        {
            "employee_phone": "+15551234567",
            "bridge_url": "https://maya-relay.example/webhooks/twilio/voice/bridge/conversation-1",
            "status_callback_url": "https://maya-relay.example/webhooks/twilio/voice/status",
        }
    ]
    assert len(repository.calls) == 1
    call = repository.calls[0]
    assert call["id"] == "call-1"
    assert call["conversation_id"] == "conversation-1"
    assert call["direction"] == "outbound"
    assert call["call_type"] == "conversation_call"
    assert call["customer_phone"] == "+15550000001"
    assert call["employee_phone"] == "+15551234567"
    assert call["twilio_call_sid"] == "CAfake1"
    assert call["status"] == "initiated"


def test_api_rejects_duplicate_active_click_to_call():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="conversation_call",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAactive",
        status="ringing",
    )
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post("/api/conversations/conversation-1/call", headers={"cookie": cookie})

    assert response.status_code == 409
    assert response.json()["detail"] == "A call is already in progress for this conversation."
    assert client.app.state.fake_voice_caller.calls == []
    assert len(repository.calls) == 1


def test_api_starts_new_call_and_creates_contact_conversation():
    client, repository, _ = make_client(admin_password="secret")
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post(
        "/api/calls",
        json={"phone_number": "+15550000003", "display_name": "New Client"},
        headers={"cookie": cookie},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "calling"
    assert payload["callSid"] == "CAfake1"
    assert payload["to"] == "+15550000003"
    assert payload["employeePhone"] == "+15551234567"
    assert payload["conversation"]["id"] == "conversation-1"
    assert payload["conversation"]["channel"] == "sms"
    assert payload["conversation"]["customer"]["displayName"] == "New Client"
    assert repository.conversations[0].customer_phone == "+15550000003"
    assert repository.conversations[0].assigned_employee == "+15551234567"
    assert repository.conversations[0].customer_channel == "sms"
    assert client.app.state.fake_voice_caller.calls == [
        {
            "employee_phone": "+15551234567",
            "bridge_url": "https://maya-relay.example/webhooks/twilio/voice/bridge/conversation-1",
            "status_callback_url": "https://maya-relay.example/webhooks/twilio/voice/status",
        }
    ]
    assert repository.calls[0]["call_type"] == "manual_outbound"
    assert repository.calls[0]["customer_phone"] == "+15550000003"
    assert repository.calls[0]["employee_phone"] == "+15551234567"
    assert repository.calls[0]["twilio_call_sid"] == "CAfake1"


def test_api_new_call_rejects_maya_business_number():
    client, _, _ = make_client(admin_password="secret")
    login = client.post("/admin/login", data={"password": "secret"}, follow_redirects=False)
    cookie = login.headers["set-cookie"]

    response = client.post(
        "/api/calls",
        json={"phone_number": "+13852208404"},
        headers={"cookie": cookie},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Customer phone number cannot be the Maya business number."


def test_twilio_voice_bridge_dials_customer():
    client, repository, _ = make_client()
    repository.get_or_create_customer_conversation(
        customer_phone="whatsapp:+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )

    response = client.post("/webhooks/twilio/voice/bridge/conversation-1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/xml")
    assert "Connecting you to the customer." in response.text
    assert "<Dial" in response.text
    assert "+15550000001" in response.text
    assert "+13852208404" in response.text


def test_twilio_studio_incoming_voice_call_logs_inbound():
    client, repository, _ = make_client()

    response = client.post(
        "/webhooks/twilio/voice/studio/incoming",
        data={
            "CallSid": "CAinbound",
            "CallStatus": "ringing",
            "From": "+15550000009",
            "To": "+13852208404",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "logged",
        "callId": "call-1",
        "conversationId": "conversation-1",
    }
    assert len(repository.conversations) == 1
    assert len(repository.calls) == 1
    call = repository.calls[0]
    assert call["conversation_id"] == "conversation-1"
    assert call["direction"] == "inbound"
    assert call["call_type"] == "inbound"
    assert call["customer_phone"] == "+15550000009"
    assert call["employee_phone"] == "+15551234567"
    assert call["twilio_call_sid"] == "CAinbound"
    assert call["status"] == "ringing"
    assert repository.call_events[0]["call_id"] == "call-1"
    assert repository.call_events[0]["event_type"] == "ringing"


def test_twilio_studio_incoming_voice_complete_updates_inbound_call():
    client, repository, _ = make_client()
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000009",
        employee_phone="+15551234567",
        twilio_call_sid="CAinbound",
        status="ringing",
    )

    response = client.post(
        "/webhooks/twilio/voice/studio/complete",
        data={
            "CallSid": "CAinbound",
            "DialCallSid": "CAofficeleg",
            "DialCallStatus": "completed",
        },
    )

    assert response.status_code == 204
    assert repository.calls[0]["status"] == "completed"
    assert repository.calls[0]["completed_at"] is not None
    assert repository.call_events == [
        {
            "id": "call-event-1",
            "call_id": "call-1",
            "twilio_call_sid": "CAinbound",
            "event_type": "studio-complete",
            "call_status": "completed",
            "payload": {
                "CallSid": "CAinbound",
                "DialCallSid": "CAofficeleg",
                "DialCallStatus": "completed",
            },
        }
    ]


def test_twilio_studio_complete_fetches_live_call_recording_and_auto_processes(monkeypatch):
    client, repository, _ = make_client(
        twilio_account_sid="ACfake",
        twilio_auth_token="token",
        assemblyai_api_key="assembly-key",
        openai_api_key="openai-key",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000009",
        employee_phone="+15551234567",
        twilio_call_sid="CAinbound",
        status="ringing",
    )

    class FakeAudioResponse:
        content = b"fake live call audio"
        headers = {"content-type": "audio/mpeg"}

        def raise_for_status(self):
            return None

    class FakeJsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, auth=None, timeout=None, headers=None):
        if url.endswith("/Calls/CAinbound/Recordings.json"):
            assert auth == ("ACfake", "token")
            return FakeJsonResponse(
                {
                    "recordings": [
                        {
                            "sid": "REshort",
                            "uri": "/2010-04-01/Accounts/ACfake/Recordings/REshort.json",
                            "status": "completed",
                            "duration": "31",
                            "channels": "2",
                        },
                        {
                            "sid": "RElive",
                            "uri": "/2010-04-01/Accounts/ACfake/Recordings/RElive.json",
                            "status": "completed",
                            "duration": "84",
                            "channels": "2",
                        }
                    ]
                }
            )
        if url == "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/RElive.mp3":
            assert auth == ("ACfake", "token")
            return FakeAudioResponse()
        assert url == "https://api.assemblyai.com/v2/transcript/transcript-live"
        assert headers == {"Authorization": "assembly-key"}
        return FakeJsonResponse({"status": "completed", "text": "I need a quote for a lobby sign."})

    def fake_post(url, headers=None, data=None, json=None, timeout=None):
        if url == "https://api.assemblyai.com/v2/upload":
            assert headers == {"Authorization": "assembly-key"}
            assert data == b"fake live call audio"
            return FakeJsonResponse({"upload_url": "https://assembly.example/upload/live-audio"})
        if url == "https://api.assemblyai.com/v2/transcript":
            assert headers == {"Authorization": "assembly-key", "Content-Type": "application/json"}
            assert json == {
                "audio_url": "https://assembly.example/upload/live-audio",
                "speech_models": ["universal-3-pro", "universal-2"],
            }
            return FakeJsonResponse({"id": "transcript-live"})
        assert url == "https://api.openai.com/v1/responses"
        assert headers == {
            "Authorization": "Bearer openai-key",
            "Content-Type": "application/json",
        }
        assert "I need a quote for a lobby sign." in json["input"]
        return FakeJsonResponse({"output_text": "- Customer needs a quote for a lobby sign."})

    monkeypatch.setattr("app.routes.twilio_voice.requests.get", fake_get)
    monkeypatch.setattr("app.routes.api.requests.get", fake_get)
    monkeypatch.setattr("app.routes.api.requests.post", fake_post)

    response = client.post(
        "/webhooks/twilio/voice/studio/complete",
        data={
            "CallSid": "CAinbound",
            "DialCallSid": "CAofficeleg",
            "DialCallStatus": "completed",
        },
    )

    assert response.status_code == 204
    call = repository.calls[0]
    assert call["status"] == "completed"
    assert call["recording_sid"] == "RElive"
    assert call["recording_url"] == "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/RElive.json"
    assert call["recording_status"] == "completed"
    assert call["recording_duration_seconds"] == 84
    assert call["recording_channels"] == 2
    assert call["outcome"] is None
    assert call["follow_up_status"] == "none"
    assert call["transcription"] == "I need a quote for a lobby sign."
    assert call["recap"] == "- Customer needs a quote for a lobby sign."


def test_twilio_voice_status_updates_call_log_and_records_event():
    client, repository, _ = make_client()
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="conversation_call",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CAfake1",
        status="initiated",
    )

    response = client.post(
        "/webhooks/twilio/voice/status",
        data={
            "CallSid": "CAfake1",
            "CallStatus": "answered",
            "From": "+13852208404",
            "To": "+15551234567",
        },
    )

    assert response.status_code == 204
    assert repository.calls[0]["status"] == "answered"
    assert repository.calls[0]["answered_at"] is not None
    assert repository.call_events == [
        {
            "id": "call-event-1",
            "call_id": "call-1",
            "twilio_call_sid": "CAfake1",
            "event_type": "answered",
            "call_status": "answered",
            "payload": {
                "CallSid": "CAfake1",
                "CallStatus": "answered",
                "From": "+13852208404",
                "To": "+15551234567",
            },
        }
    ]


def test_twilio_voice_recording_status_updates_call_log_and_records_event():
    client, repository, _ = make_client()
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000009",
        employee_phone="+15551234567",
        twilio_call_sid="CAinbound",
        status="ringing",
    )

    response = client.post(
        "/webhooks/twilio/voice/recording",
        data={
            "CallSid": "CAinbound",
            "RecordingSid": "REfake1",
            "RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/REfake1",
            "RecordingStatus": "completed",
            "RecordingDuration": "37",
            "RecordingChannels": "1",
        },
    )

    assert response.status_code == 204
    assert repository.calls[0]["recording_sid"] == "REfake1"
    assert repository.calls[0]["recording_url"] == "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/REfake1"
    assert repository.calls[0]["recording_status"] == "completed"
    assert repository.calls[0]["recording_duration_seconds"] == 37
    assert repository.calls[0]["recording_channels"] == 1
    assert repository.calls[0]["outcome"] == "voicemail"
    assert repository.calls[0]["follow_up_status"] == "needed"
    assert repository.call_events == [
        {
            "id": "call-event-1",
            "call_id": "call-1",
            "twilio_call_sid": "CAinbound",
            "event_type": "recording-status",
            "call_status": "completed",
            "payload": {
                "CallSid": "CAinbound",
                "RecordingSid": "REfake1",
                "RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/REfake1",
                "RecordingStatus": "completed",
                "RecordingDuration": "37",
                "RecordingChannels": "1",
            },
        }
    ]


def test_twilio_voice_completed_recording_auto_transcribes_and_recaps(monkeypatch):
    client, repository, _ = make_client(
        twilio_account_sid="ACfake",
        twilio_auth_token="token",
        assemblyai_api_key="assembly-key",
        openai_api_key="openai-key",
    )
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000009",
        employee_phone="+15551234567",
        twilio_call_sid="CAinbound",
        status="ringing",
    )

    class FakeAudioResponse:
        content = b"fake audio"
        headers = {"content-type": "audio/mpeg"}

        def raise_for_status(self):
            return None

    class FakeJsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, auth=None, timeout=None, headers=None):
        if auth:
            assert url == "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/REfake1.mp3"
            assert auth == ("ACfake", "token")
            return FakeAudioResponse()
        assert url == "https://api.assemblyai.com/v2/transcript/transcript-1"
        assert headers == {"Authorization": "assembly-key"}
        return FakeJsonResponse({"status": "completed", "text": "Please call me back about a sign quote."})

    def fake_post(url, headers=None, data=None, json=None, timeout=None):
        if url == "https://api.assemblyai.com/v2/upload":
            assert headers == {"Authorization": "assembly-key"}
            assert data == b"fake audio"
            return FakeJsonResponse({"upload_url": "https://assembly.example/upload/audio"})
        if url == "https://api.assemblyai.com/v2/transcript":
            assert headers == {"Authorization": "assembly-key", "Content-Type": "application/json"}
            assert json == {
                "audio_url": "https://assembly.example/upload/audio",
                "speech_models": ["universal-3-pro", "universal-2"],
            }
            return FakeJsonResponse({"id": "transcript-1"})
        assert url == "https://api.openai.com/v1/responses"
        assert headers == {
            "Authorization": "Bearer openai-key",
            "Content-Type": "application/json",
        }
        assert "Please call me back about a sign quote." in json["input"]
        return FakeJsonResponse({"output_text": "- Customer wants a callback about a sign quote."})

    monkeypatch.setattr("app.routes.api.requests.get", fake_get)
    monkeypatch.setattr("app.routes.api.requests.post", fake_post)

    response = client.post(
        "/webhooks/twilio/voice/recording",
        data={
            "CallSid": "CAinbound",
            "RecordingSid": "REfake1",
            "RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/ACfake/Recordings/REfake1",
            "RecordingStatus": "completed",
            "RecordingDuration": "37",
            "RecordingChannels": "1",
        },
    )

    assert response.status_code == 204
    assert repository.calls[0]["transcription"] == "Please call me back about a sign quote."
    assert repository.calls[0]["recap"] == "- Customer wants a callback about a sign quote."


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


def test_api_creates_sends_public_proof_request_and_exposes_conversation_action_history():
    client, repository, sender = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    unauthenticated = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
    )
    assert unauthenticated.status_code == 401

    login = client.post("/api/auth/login", json={"password": "secret"})
    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        data={
            "title": "Business card proof",
            "operator_note": "Please review before print.",
            "customer_message": "Please review this proof before we print.",
        },
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["publicUrl"].startswith("https://maya-relay.example/proof/")
    assert payload["proofRequest"] == {
        "id": "customer-action-request-1",
        "conversationId": "conversation-1",
        "contactId": "contact-1",
        "type": "proof",
        "status": "pending",
        "title": "Business card proof",
        "operatorNote": "Please review before print.",
        "expiresAt": None,
        "completedAt": None,
        "canceledAt": None,
        "createdBy": None,
        "createdAt": repository.customer_action_requests[0]["created_at"],
        "updatedAt": None,
    }
    assert "public_token_hash" not in payload["proofRequest"]
    assert repository.customer_action_files[0]["bucket"] == "attachments"
    assert repository.customer_action_files[0]["object_path"] == "proof-requests/conversation-1/proof.pdf"
    assert repository.customer_action_files[0]["public_url"] == "https://files.example/proof-requests/conversation-1/proof.pdf"
    assert repository.customer_action_files[0]["external_url"] is None
    assert repository.customer_action_files[0]["original_filename"] == "proof.pdf"
    assert repository.customer_action_files[0]["content_type"] == "application/pdf"
    assert repository.customer_action_files[0]["size_bytes"] == len(PROOF_PDF_BYTES)
    assert payload["message"]["twilioMessageSid"] == "SMfake1"
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "body": (
            "Please review this proof before we print.\n\n"
            f"Your proof is ready. Review here: {payload['publicUrl']}"
        ),
    }
    assert repository.messages[-1]["body"] == sender.sent_messages[-1]["body"]
    assert repository.customer_action_events[-1]["event_type"] == "sent"
    assert repository.customer_action_events[-1]["metadata"] == {
        "message_id": "message-1",
        "twilio_message_sid": "SMfake1",
        "channel": "sms",
        "send_mode": "free_form",
    }

    detail = client.get("/api/conversations/conversation-1", headers={"cookie": login.headers["set-cookie"]})

    assert detail.status_code == 200
    assert detail.json()["customerActions"] == [payload["proofRequest"]]


def test_api_proof_request_rejects_unsupported_file_type_before_storage():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.txt", b"not a proof", "text/plain")},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Proof file must be a PDF or image file: PDF, JPG, PNG, GIF, WebP, or TIFF."
    assert repository.customer_action_requests == []
    assert repository.customer_action_files == []


def test_api_proof_request_rejects_oversized_file_before_storage():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})
    oversized_pdf = b"%PDF-1.4\n" + (b"x" * (32 * 1024 * 1024))

    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", oversized_pdf, "application/pdf")},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Proof file must be 32 MB or smaller."
    assert repository.customer_action_requests == []
    assert repository.customer_action_files == []


def test_api_proof_request_uses_forwarded_host_when_configured_base_url_is_localhost():
    client, repository, _ = make_client(admin_password="secret", app_base_url="http://localhost:8000")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={
            "cookie": login.headers["set-cookie"],
            "x-forwarded-proto": "https",
            "x-forwarded-host": "mayagraphics.co",
        },
    )

    assert response.status_code == 200
    assert response.json()["publicUrl"].startswith("https://mayagraphics.co/proof/")
    assert "http://localhost:8000" not in repository.messages[-1]["body"]


def test_api_proof_request_rejects_local_public_link_before_uploading():
    client, repository, _ = make_client(admin_password="secret", app_base_url="http://127.0.0.1:8000")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={
            "cookie": login.headers["set-cookie"],
            "host": "127.0.0.1:8000",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "APP_BASE_URL must be set to the public Maya Relay URL before sending proof links."
    assert repository.customer_action_requests == []
    assert repository.customer_action_files == []
    assert repository.messages == []


def test_api_public_proof_request_read_and_approve_flow():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})
    created = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={"cookie": login.headers["set-cookie"]},
    ).json()
    token = created["publicUrl"].rsplit("/", 1)[-1]

    public_read = client.get(f"/api/proof/{token}")

    assert public_read.status_code == 200
    public_payload = public_read.json()["proofRequest"]
    assert public_payload["status"] == "pending"
    assert public_payload["files"] == [
        {
            "id": "customer-action-file-1",
            "role": "proof",
            "publicUrl": "https://files.example/proof-requests/conversation-1/proof.pdf",
            "externalUrl": None,
            "originalFilename": "proof.pdf",
            "contentType": "application/pdf",
            "sizeBytes": len(PROOF_PDF_BYTES),
            "createdAt": repository.customer_action_files[0]["created_at"],
        }
    ]
    assert [event["type"] for event in public_payload["events"]] == ["created", "sent"]
    assert "public_token_hash" not in public_payload

    approved = client.post(f"/api/proof/{token}/approve", json={"comment": "Approved."})

    assert approved.status_code == 200
    assert approved.json()["proofRequest"]["status"] == "approved"
    assert repository.customer_action_events[-1]["event_type"] == "approved"
    assert repository.customer_action_events[-1]["comment"] == "Approved."
    assert repository.messages[-1]["direction"] == "system"
    assert repository.messages[-1]["body"] == "Proof approved by customer.\nComment: Approved."

    changes_after_approval = client.post(
        f"/api/proof/{token}/changes",
        json={"comment": "Actually change it."},
    )

    assert changes_after_approval.status_code == 409
    assert repository.messages[-1]["body"] == "Proof approved by customer.\nComment: Approved."


def test_api_public_proof_request_changes_flow_and_invalid_token():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})
    created = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={"cookie": login.headers["set-cookie"]},
    ).json()
    token = created["publicUrl"].rsplit("/", 1)[-1]

    missing = client.get("/api/proof/not-a-real-token")
    invalid_comment = client.post(f"/api/proof/{token}/changes", json={"comment": " "})
    changes = client.post(f"/api/proof/{token}/changes", json={"comment": "Please make the logo larger."})

    assert missing.status_code == 404
    assert invalid_comment.status_code == 400
    assert changes.status_code == 200
    assert changes.json()["proofRequest"]["status"] == "changes_requested"
    assert repository.customer_action_events[-1]["event_type"] == "changes_requested"
    assert repository.customer_action_events[-1]["comment"] == "Please make the logo larger."
    assert repository.messages[-1]["direction"] == "system"
    assert repository.messages[-1]["body"] == "Proof changes requested by customer:\nPlease make the logo larger."


def test_api_proof_request_uses_whatsapp_template_when_conversation_is_whatsapp():
    client, repository, sender = make_client(
        admin_password="secret",
        whatsapp_template_proof_ready_content_sid="HXproof",
    )
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    token = response.json()["publicUrl"].rsplit("/", 1)[-1]
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "channel": "whatsapp",
        "content_sid": "HXproof",
        "content_variables": {"1": "Proof approval", "2": token},
    }
    assert repository.messages[-1]["body"] == (
        "Your proof for Proof approval is ready. Please review it using the secure Maya Graphics link below.\n\n"
        f"Review proof: {response.json()['publicUrl']}"
    )
    assert repository.customer_action_events[-1]["metadata"] == {
        "message_id": "message-1",
        "twilio_message_sid": "SMfake1",
        "channel": "whatsapp",
        "send_mode": "template",
        "template_key": "proof_ready",
        "content_sid": "HXproof",
        "content_variables": {"1": "Proof approval", "2": token},
    }


def test_api_whatsapp_proof_request_requires_template_config():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "WHATSAPP_TEMPLATE_PROOF_READY_CONTENT_SID must be configured before sending this WhatsApp request."
    )


def test_api_proof_request_infers_whatsapp_from_legacy_prefixed_customer_phone():
    client, repository, sender = make_client(
        admin_password="secret",
        whatsapp_template_proof_ready_content_sid="HXproof",
    )
    repository.get_or_create_customer_conversation(
        customer_phone="whatsapp:+5218443261219",
        assigned_employee="+15551234567",
        customer_channel="sms",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    detail = client.get("/api/conversations/conversation-1", headers={"cookie": login.headers["set-cookie"]})
    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert detail.status_code == 200
    assert detail.json()["conversation"]["channel"] == "whatsapp"
    assert response.status_code == 200
    assert sender.sent_messages[-1]["channel"] == "whatsapp"
    assert sender.sent_messages[-1]["content_sid"] == "HXproof"
    assert repository.customer_action_events[-1]["metadata"]["channel"] == "whatsapp"
    assert repository.customer_action_events[-1]["metadata"]["send_mode"] == "template"


def test_api_proof_request_keeps_request_when_twilio_send_fails():
    client, repository, sender = make_client(admin_password="secret")
    sender.should_raise = True
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/proof-requests",
        files={"proof_file": ("proof.pdf", PROOF_PDF_BYTES, "application/pdf")},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Proof request was created, but the customer message could not be sent."
    assert len(repository.customer_action_requests) == 1
    assert [event["event_type"] for event in repository.customer_action_events] == ["created"]
    assert repository.messages == []


def test_api_cancel_customer_action_request_requires_auth_and_blocks_completed_request():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})
    created = client.post(
        "/api/conversations/conversation-1/asset-requests",
        data={"title": "Upload logo files"},
        headers={"cookie": login.headers["set-cookie"]},
    ).json()
    request_id = created["assetRequest"]["id"]

    unauthenticated = client.post(f"/api/customer-actions/{request_id}/cancel")
    canceled = client.post(
        f"/api/customer-actions/{request_id}/cancel",
        headers={"cookie": login.headers["set-cookie"]},
    )
    second_cancel = client.post(
        f"/api/customer-actions/{request_id}/cancel",
        headers={"cookie": login.headers["set-cookie"]},
    )
    detail = client.get("/api/conversations/conversation-1", headers={"cookie": login.headers["set-cookie"]})

    assert unauthenticated.status_code == 401
    assert canceled.status_code == 200
    assert canceled.json()["customerAction"]["status"] == "canceled"
    assert canceled.json()["customerAction"]["canceledAt"] is not None
    assert repository.customer_action_events[-1]["event_type"] == "canceled"
    assert second_cancel.status_code == 409
    assert detail.json()["customerActions"][0]["status"] == "canceled"


def test_api_creates_asset_request_and_customer_upload_arrives_in_conversation():
    client, repository, sender = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    unauthenticated = client.post("/api/conversations/conversation-1/asset-requests")
    assert unauthenticated.status_code == 401

    login = client.post("/api/auth/login", json={"password": "secret"})
    created = client.post(
        "/api/conversations/conversation-1/asset-requests",
        data={
            "title": "Upload logo files",
            "operator_note": "Need source files.",
            "customer_message": "Please upload the logo and any reference files.",
        },
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert created.status_code == 200
    payload = created.json()
    assert payload["publicUrl"].startswith("https://maya-relay.example/assets/")
    assert payload["assetRequest"] == {
        "id": "customer-action-request-1",
        "conversationId": "conversation-1",
        "contactId": "contact-1",
        "type": "assets",
        "status": "pending",
        "title": "Upload logo files",
        "operatorNote": "Need source files.",
        "expiresAt": None,
        "completedAt": None,
        "canceledAt": None,
        "createdBy": None,
        "createdAt": repository.customer_action_requests[0]["created_at"],
        "updatedAt": None,
    }
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "body": (
            "Please upload the logo and any reference files.\n\n"
            f"Please upload your files here: {payload['publicUrl']}"
        ),
    }
    assert repository.messages[-1]["direction"] == "employee_to_customer"
    assert repository.customer_action_events[-1]["event_type"] == "sent"

    token = payload["publicUrl"].rsplit("/", 1)[-1]
    public_read = client.get(f"/api/assets/{token}")
    assert public_read.status_code == 200
    assert public_read.json()["assetRequest"]["files"] == []

    submitted = client.post(
        f"/api/assets/{token}/submit",
        data={"note": "Here are the logo files."},
        files=[
            ("asset_files", ("logo.png", b"\x89PNG\r\n\x1a\nfake logo", "image/png")),
            ("asset_files", ("brand.ai", b"fake illustrator", "application/octet-stream")),
        ],
    )

    assert submitted.status_code == 200
    submitted_payload = submitted.json()["assetRequest"]
    assert submitted_payload["status"] == "submitted"
    assert [file["role"] for file in submitted_payload["files"]] == ["customer_asset", "customer_asset"]
    assert [file["originalFilename"] for file in submitted_payload["files"]] == ["logo.png", "brand.ai"]
    assert repository.customer_action_events[-1]["event_type"] == "assets_submitted"
    assert repository.customer_action_events[-1]["comment"] == "Here are the logo files."
    assert repository.customer_action_events[-1]["metadata"] == {"file_count": 2}
    assert repository.messages[-1]["direction"] == "system"
    assert repository.messages[-1]["body"] == "Assets uploaded by customer: 2 files.\nNote: Here are the logo files."
    assert repository.messages[-1]["num_media"] == 2
    assert repository.messages[-1]["media_urls"] == (
        "https://files.example/customer-assets/customer-action-request-1/logo.png",
        "https://files.example/customer-assets/customer-action-request-1/brand.ai",
    )
    assert len(repository.attachments) == 2
    assert repository.attachments[-1]["message_id"] == repository.messages[-1]["id"]

    detail = client.get("/api/conversations/conversation-1", headers={"cookie": login.headers["set-cookie"]})
    detail_messages = detail.json()["messages"]
    assert detail_messages[-1]["body"] == "Assets uploaded by customer: 2 files.\nNote: Here are the logo files."
    assert len(detail_messages[-1]["attachments"]) == 2


def test_api_asset_request_uses_whatsapp_template_when_conversation_is_whatsapp():
    client, repository, sender = make_client(
        admin_password="secret",
        whatsapp_template_assets_needed_content_sid="HXassets",
    )
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/asset-requests",
        data={"title": "Banner order"},
        headers={"cookie": login.headers["set-cookie"]},
    )

    assert response.status_code == 200
    token = response.json()["publicUrl"].rsplit("/", 1)[-1]
    assert sender.sent_messages[-1] == {
        "sid": "SMfake1",
        "to_phone": "+15550000001",
        "channel": "whatsapp",
        "content_sid": "HXassets",
        "content_variables": {"1": "Banner order", "2": token},
    }
    assert repository.messages[-1]["body"] == (
        "We need your files for Banner order. Please upload them using the secure Maya Graphics link below.\n\n"
        f"Upload files: {response.json()['publicUrl']}"
    )
    assert repository.customer_action_events[-1]["metadata"]["send_mode"] == "template"
    assert repository.customer_action_events[-1]["metadata"]["template_key"] == "assets_needed"


def test_api_asset_request_rejects_local_public_link_before_sending():
    client, repository, _ = make_client(admin_password="secret", app_base_url="http://127.0.0.1:8000")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})

    response = client.post(
        "/api/conversations/conversation-1/asset-requests",
        headers={
            "cookie": login.headers["set-cookie"],
            "host": "127.0.0.1:8000",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "APP_BASE_URL must be set to the public Maya Relay URL before sending asset links."
    assert repository.customer_action_requests == []
    assert repository.messages == []


def test_api_public_asset_submit_validates_file_count_type_and_size():
    client, repository, _ = make_client(admin_password="secret")
    repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    login = client.post("/api/auth/login", json={"password": "secret"})
    token = client.post(
        "/api/conversations/conversation-1/asset-requests",
        headers={"cookie": login.headers["set-cookie"]},
    ).json()["publicUrl"].rsplit("/", 1)[-1]

    missing_files = client.post(f"/api/assets/{token}/submit", data={"note": "No files"})
    too_many_files = client.post(
        f"/api/assets/{token}/submit",
        files=[("asset_files", (f"file-{index}.png", b"\x89PNG\r\n\x1a\n", "image/png")) for index in range(9)],
    )
    unsupported = client.post(
        f"/api/assets/{token}/submit",
        files=[("asset_files", ("malware.exe", b"MZ", "application/x-msdownload"))],
    )
    oversized = client.post(
        f"/api/assets/{token}/submit",
        files=[("asset_files", ("large.pdf", b"x" * (32 * 1024 * 1024 + 1), "application/pdf"))],
    )

    assert missing_files.status_code == 400
    assert missing_files.json()["detail"] == "At least one asset file is required."
    assert too_many_files.status_code == 400
    assert too_many_files.json()["detail"] == "Upload 8 files or fewer."
    assert unsupported.status_code == 400
    assert unsupported.json()["detail"] == "Asset files must be PDF, image, design, document, or ZIP files."
    assert oversized.status_code == 413
    assert oversized.json()["detail"] == "Each asset file must be 32 MB or smaller."
    assert repository.customer_action_requests[0]["status"] == "pending"
    assert repository.customer_action_files == []
