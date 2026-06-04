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

    conversation = repository.get_open_conversation_by_code("+15551234567", "c0002")

    assert conversation is not None
    assert conversation.customer_phone == "+15550000002"
    assert conversation.conversation_code == "C0002"


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
