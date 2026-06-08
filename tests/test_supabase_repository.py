from app.db import SupabaseRelayRepository
from tests.in_memory_supabase import InMemorySupabaseClient


def build_repository() -> tuple[SupabaseRelayRepository, InMemorySupabaseClient]:
    client = InMemorySupabaseClient()
    return SupabaseRelayRepository(client), client


def test_get_contact_returns_existing_row_by_phone_number():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [
            {"phone_number": "+15550000001", "display_name": "Maria Lopez"},
            {"phone_number": "+15550000002", "display_name": "Other Contact"},
        ],
    )

    contact = repository.get_contact("+15550000001")

    assert contact is not None
    assert contact.phone_number == "+15550000001"
    assert contact.display_name == "Maria Lopez"
    assert contact.lookup_name is None


def test_get_or_create_contact_creates_once_then_reuses_row():
    repository, client = build_repository()

    first = repository.get_or_create_contact("+15550000001")
    second = repository.get_or_create_contact("+15550000001")

    assert first == second
    assert len(client.rows("contacts")) == 1
    assert client.rows("contacts")[0]["phone_number"] == "+15550000001"


def test_update_contact_lookup_name_upserts_and_preserves_display_name():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [{"phone_number": "+15550000001", "display_name": "Uploaded Name", "lookup_name": None}],
    )

    contact = repository.update_contact_lookup_name("+15550000001", "Lookup Name")

    stored = client.rows("contacts")[0]
    assert contact.lookup_name == "Lookup Name"
    assert contact.display_name == "Uploaded Name"
    assert stored["display_name"] == "Uploaded Name"
    assert stored["lookup_name"] == "Lookup Name"
    assert stored["lookup_checked_at"] is not None


def test_update_contact_lookup_name_creates_contact_when_missing():
    repository, client = build_repository()

    contact = repository.update_contact_lookup_name("+15550000001", "Lookup Name")

    assert contact.phone_number == "+15550000001"
    assert contact.lookup_name == "Lookup Name"
    assert len(client.rows("contacts")) == 1


def test_upsert_contact_display_name_preserves_lookup_name():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [{"phone_number": "+15550000001", "display_name": None, "lookup_name": "Lookup Name"}],
    )

    contact = repository.upsert_contact_display_name("+15550000001", "Manual Name")

    stored = client.rows("contacts")[0]
    assert contact.display_name == "Manual Name"
    assert contact.lookup_name == "Lookup Name"
    assert stored["display_name"] == "Manual Name"
    assert stored["lookup_name"] == "Lookup Name"


def test_get_or_create_customer_conversation_creates_contact_and_open_conversation_once():
    repository, client = build_repository()

    first = repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )
    second = repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )

    assert first == second
    assert first.status == "open"
    assert len(first.conversation_code) == 8
    assert first.conversation_code.isalnum()
    assert first.conversation_code == first.conversation_code.upper()
    assert len(client.rows("contacts")) == 1
    assert len(client.rows("conversations")) == 1


def test_get_or_create_customer_conversation_separates_channels():
    repository, client = build_repository()

    sms = repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="sms",
    )
    whatsapp = repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
        customer_channel="whatsapp",
    )

    assert sms.id != whatsapp.id
    assert sms.customer_channel == "sms"
    assert whatsapp.customer_channel == "whatsapp"
    assert len(client.rows("contacts")) == 1
    assert len(client.rows("conversations")) == 2


def test_get_latest_employee_conversation_uses_open_status_and_latest_updated_at():
    repository, client = build_repository()
    client.seed(
        "conversations",
        [
            {
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "status": "open",
                "updated_at": "2026-06-04T00:00:01+00:00",
            },
            {
                "customer_phone": "+15550000002",
                "assigned_employee": "+15551234567",
                "status": "closed",
                "updated_at": "2026-06-04T00:00:03+00:00",
            },
            {
                "customer_phone": "+15550000003",
                "assigned_employee": "+15551234567",
                "status": "open",
                "updated_at": "2026-06-04T00:00:02+00:00",
            },
        ],
    )

    conversation = repository.get_latest_employee_conversation("+15551234567")

    assert conversation is not None
    assert conversation.customer_phone == "+15550000003"


def test_get_open_conversation_by_code_routes_employee_reply():
    repository, client = build_repository()
    client.seed(
        "conversations",
        [
            {
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "conversation_code": "C0001",
                "status": "open",
            },
            {
                "customer_phone": "+15550000002",
                "assigned_employee": "+15551234567",
                "conversation_code": "C0002",
                "status": "open",
            },
        ],
    )

    conversation = repository.get_open_conversation_by_code("c0002")

    assert conversation is not None
    assert conversation.customer_phone == "+15550000002"
    assert conversation.conversation_code == "C0002"


def test_update_conversation_status_updates_row():
    repository, client = build_repository()
    client.seed(
        "conversations",
        [
            {
                "id": "conversation-1",
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "conversation_code": "C0001",
                "status": "open",
            }
        ],
    )

    conversation = repository.update_conversation_status("conversation-1", "closed")

    assert conversation.status == "closed"
    assert client.rows("conversations")[0]["status"] == "closed"


def test_create_message_stores_real_row_shape():
    repository, client = build_repository()

    message = repository.create_message(
        conversation_id="conversation-1",
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+13852208404",
        body="Hello",
        twilio_message_sid="SM123",
        num_media=1,
        media_urls=("https://example.com/image.jpg",),
        media_content_types=("image/jpeg",),
    )

    assert message["id"] == "message-1"
    assert message["media_urls"] == ["https://example.com/image.jpg"]
    assert message["media_content_types"] == ["image/jpeg"]
    assert client.rows("messages")[0]["twilio_message_sid"] == "SM123"


def test_create_message_updates_parent_conversation_timestamp():
    repository, client = build_repository()
    client.seed(
        "conversations",
        [
            {
                "id": "conversation-1",
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "updated_at": "2026-06-01T00:00:00+00:00",
            }
        ],
    )

    repository.create_message(
        conversation_id="conversation-1",
        direction="customer_to_employee",
        from_phone="+15550000001",
        to_phone="+13852208404",
        body="Fresh message",
    )

    assert client.rows("conversations")[0]["updated_at"] != "2026-06-01T00:00:00+00:00"


def test_get_message_by_client_request_id_returns_existing_message():
    repository, _ = build_repository()
    created = repository.create_message(
        conversation_id="conversation-1",
        direction="employee_to_customer",
        from_phone="+13852208404",
        to_phone="+15550000001",
        body="Already sent.",
        client_request_id="browser-request-1",
    )

    found = repository.get_message_by_client_request_id(
        conversation_id="conversation-1",
        client_request_id="browser-request-1",
    )

    assert found["id"] == created["id"]
    assert found["client_request_id"] == "browser-request-1"


def test_update_message_status_updates_matching_message_only():
    repository, client = build_repository()
    client.seed(
        "messages",
        [
            {"conversation_id": "conversation-1", "twilio_message_sid": "SMtarget", "body": "target"},
            {"conversation_id": "conversation-1", "twilio_message_sid": "SMother", "body": "other"},
        ],
    )

    repository.update_message_status(
        twilio_message_sid="SMtarget",
        status="delivered",
        error_code=None,
        error_message=None,
    )

    rows = client.rows("messages")
    target = next(row for row in rows if row["twilio_message_sid"] == "SMtarget")
    other = next(row for row in rows if row["twilio_message_sid"] == "SMother")
    assert target["delivery_status"] == "delivered"
    assert other["delivery_status"] is None


def test_create_call_stores_outbound_call_log():
    repository, client = build_repository()

    call = repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="conversation_call",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CA123",
        status="initiated",
    )

    stored = client.rows("calls")[0]
    assert call["id"] == "call-1"
    assert stored["conversation_id"] == "conversation-1"
    assert stored["direction"] == "outbound"
    assert stored["call_type"] == "conversation_call"
    assert stored["customer_phone"] == "+15550000001"
    assert stored["employee_phone"] == "+15551234567"
    assert stored["twilio_call_sid"] == "CA123"
    assert stored["status"] == "initiated"


def test_update_call_status_by_sid_sets_status_timestamps():
    repository, client = build_repository()
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="manual_outbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CA123",
        status="initiated",
    )

    answered = repository.update_call_status_by_sid(twilio_call_sid="CA123", status="answered")
    completed = repository.update_call_status_by_sid(twilio_call_sid="CA123", status="completed")
    missing = repository.update_call_status_by_sid(twilio_call_sid="CAmissing", status="completed")

    stored = client.rows("calls")[0]
    assert answered is not None
    assert completed is not None
    assert missing is None
    assert stored["status"] == "completed"
    assert stored["answered_at"] is not None
    assert stored["completed_at"] is not None


def test_update_call_details_stores_outcome_notes_and_follow_up_fields():
    repository, client = build_repository()
    repository.create_call(
        conversation_id="conversation-1",
        direction="outbound",
        call_type="manual_outbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CA123",
        status="completed",
    )

    call = repository.update_call_details(
        call_id="call-1",
        outcome="voicemail",
        follow_up_status="scheduled",
        notes="Left a message.",
        recap="Customer did not answer.",
        transcription="Voicemail greeting.",
    )

    stored = client.rows("calls")[0]
    assert call is not None
    assert stored["outcome"] == "voicemail"
    assert stored["follow_up_status"] == "scheduled"
    assert stored["notes"] == "Left a message."
    assert stored["recap"] == "Customer did not answer."
    assert stored["transcription"] == "Voicemail greeting."


def test_create_call_event_stores_payload_even_without_matched_call():
    repository, client = build_repository()

    event = repository.create_call_event(
        call_id=None,
        twilio_call_sid="CAunmatched",
        event_type="ringing",
        call_status="ringing",
        payload={"CallSid": "CAunmatched", "CallStatus": "ringing"},
    )

    stored = client.rows("call_events")[0]
    assert event["id"] == "call_event-1"
    assert stored["call_id"] is None
    assert stored["twilio_call_sid"] == "CAunmatched"
    assert stored["event_type"] == "ringing"
    assert stored["call_status"] == "ringing"
    assert stored["payload"] == {"CallSid": "CAunmatched", "CallStatus": "ringing"}


def test_list_calls_for_conversation_returns_newest_first():
    repository, client = build_repository()
    client.seed(
        "calls",
        [
            {
                "id": "call-old",
                "conversation_id": "conversation-1",
                "direction": "outbound",
                "call_type": "conversation_call",
                "customer_phone": "+15550000001",
                "employee_phone": "+15551234567",
                "twilio_call_sid": "CAold",
                "status": "completed",
                "created_at": "2026-06-08T20:00:00+00:00",
            },
            {
                "id": "call-new",
                "conversation_id": "conversation-1",
                "direction": "outbound",
                "call_type": "manual_outbound",
                "customer_phone": "+15550000001",
                "employee_phone": "+15551234567",
                "twilio_call_sid": "CAnew",
                "status": "ringing",
                "created_at": "2026-06-08T20:05:00+00:00",
            },
            {
                "id": "call-other",
                "conversation_id": "conversation-2",
                "direction": "outbound",
                "call_type": "conversation_call",
                "customer_phone": "+15550000002",
                "employee_phone": "+15551234567",
                "twilio_call_sid": "CAother",
                "status": "completed",
                "created_at": "2026-06-08T20:10:00+00:00",
            },
        ],
    )

    calls = repository.list_calls_for_conversation("conversation-1")

    assert [call["id"] for call in calls] == ["call-new", "call-old"]


def test_list_conversations_batches_contacts_and_messages():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [
            {"phone_number": "+15550000001", "display_name": "Maria Lopez"},
            {"phone_number": "+15550000002", "lookup_name": "Lookup Client"},
        ],
    )
    client.seed(
        "conversations",
        [
            {
                "id": "conversation-1",
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "conversation_code": "C0001",
                "updated_at": "2026-06-04T00:00:02+00:00",
            },
            {
                "id": "conversation-2",
                "customer_phone": "+15550000002",
                "assigned_employee": "+15551234567",
                "conversation_code": "C0002",
                "updated_at": "2026-06-04T00:00:01+00:00",
            },
        ],
    )
    client.seed(
        "messages",
        [
            {
                "conversation_id": "conversation-1",
                "body": "Older message",
                "direction": "customer_to_employee",
                "created_at": "2026-06-04T00:00:01+00:00",
            },
            {
                "conversation_id": "conversation-1",
                "body": "Latest message",
                "direction": "employee_to_customer",
                "delivery_status": "delivered",
                "created_at": "2026-06-04T00:00:03+00:00",
            },
            {
                "conversation_id": "conversation-1",
                "body": "#C0001 Internal AI suggestion",
                "direction": "system",
                "delivery_status": "delivered",
                "created_at": "2026-06-04T00:00:04+00:00",
            },
            {
                "conversation_id": "conversation-2",
                "body": "Second conversation",
                "direction": "customer_to_employee",
                "created_at": "2026-06-04T00:00:02+00:00",
            },
        ],
    )
    client.query_count = 0

    conversations = repository.list_conversations()

    assert client.query_count == 3
    assert [conversation["id"] for conversation in conversations] == ["conversation-1", "conversation-2"]
    assert conversations[0]["customer_display_name"] == "Maria Lopez"
    assert conversations[0]["customer_name"] == "Maria Lopez"
    assert conversations[0]["last_message"]["body"] == "Latest message"
    assert "Internal AI suggestion" in conversations[0]["message_search_text"]
    assert "Older message" in conversations[0]["message_search_text"]
    assert conversations[1]["customer_lookup_name"] == "Lookup Client"
    assert conversations[1]["last_message"]["body"] == "Second conversation"


def test_list_conversations_applies_offset_and_limit():
    repository, client = build_repository()
    client.seed(
        "conversations",
        [
            {
                "id": "conversation-1",
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "updated_at": "2026-06-04T00:00:03+00:00",
            },
            {
                "id": "conversation-2",
                "customer_phone": "+15550000002",
                "assigned_employee": "+15551234567",
                "updated_at": "2026-06-04T00:00:02+00:00",
            },
            {
                "id": "conversation-3",
                "customer_phone": "+15550000003",
                "assigned_employee": "+15551234567",
                "updated_at": "2026-06-04T00:00:01+00:00",
            },
        ],
    )

    conversations = repository.list_conversations(limit=1, offset=1)

    assert [conversation["id"] for conversation in conversations] == ["conversation-2"]


def test_list_conversations_applies_status_before_offset_and_limit():
    repository, client = build_repository()
    client.seed(
        "conversations",
        [
            {
                "id": "conversation-1",
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "status": "open",
                "updated_at": "2026-06-04T00:00:03+00:00",
            },
            {
                "id": "conversation-2",
                "customer_phone": "+15550000002",
                "assigned_employee": "+15551234567",
                "status": "open",
                "updated_at": "2026-06-04T00:00:02+00:00",
            },
            {
                "id": "conversation-3",
                "customer_phone": "+15550000003",
                "assigned_employee": "+15551234567",
                "status": "closed",
                "updated_at": "2026-06-04T00:00:01+00:00",
            },
        ],
    )

    conversations = repository.list_conversations(limit=1, offset=0, status="closed")

    assert [conversation["id"] for conversation in conversations] == ["conversation-3"]


def test_list_conversations_uses_latest_message_activity_for_display_order():
    repository, client = build_repository()
    client.seed(
        "conversations",
        [
            {
                "id": "conversation-1",
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "updated_at": "2026-06-01T00:00:00+00:00",
            },
            {
                "id": "conversation-2",
                "customer_phone": "+15550000002",
                "assigned_employee": "+15551234567",
                "updated_at": "2026-06-04T00:00:00+00:00",
            },
        ],
    )
    client.seed(
        "messages",
        [
            {
                "conversation_id": "conversation-1",
                "body": "New customer activity",
                "direction": "customer_to_employee",
                "created_at": "2026-06-05T00:00:00+00:00",
            },
            {
                "conversation_id": "conversation-2",
                "body": "Older active conversation",
                "direction": "customer_to_employee",
                "created_at": "2026-06-04T00:00:00+00:00",
            },
        ],
    )

    conversations = repository.list_conversations()

    assert [conversation["id"] for conversation in conversations] == ["conversation-1", "conversation-2"]
    assert conversations[0]["updated_at"] == "2026-06-05T00:00:00+00:00"
