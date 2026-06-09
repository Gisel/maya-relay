from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.config import Settings, get_settings
from app.dependencies import get_attachment_store, get_relay_service, get_repository, get_sender, get_voice_caller
from app.main import create_app
from app.services.relay import RelayService
from tests.fakes import FakeAttachmentStore, FakeRepository, FakeSender, FakeVoiceCaller


def make_client(
    *,
    verify_twilio_signature: bool = False,
    twilio_account_sid: str = "",
    twilio_auth_token: str = "",
    admin_password: str = "",
    assemblyai_api_key: str = "",
    openai_api_key: str = "",
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
        TWILIO_ACCOUNT_SID=twilio_account_sid,
        TWILIO_AUTH_TOKEN=twilio_auth_token,
        TWILIO_MESSAGING_SERVICE_SID="",
        SUPABASE_URL="",
        SUPABASE_SERVICE_ROLE_KEY="",
        APP_BASE_URL="https://maya-relay.example",
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
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.fake_voice_caller = voice_caller
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
        assert json == {"audio_url": "https://assembly.example/upload/audio"}
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
