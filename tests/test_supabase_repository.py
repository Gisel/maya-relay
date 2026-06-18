from app.db import SupabaseRelayRepository
from tests.in_memory_supabase import InMemoryQuery, InMemorySupabaseClient


class MissingContactNotesQuery(InMemoryQuery):
    def execute(self):
        if self.table.name == "contacts" and self.selected_columns and "notes" in self.selected_columns:
            raise Exception("{'code': '42703', 'message': 'column contacts.notes does not exist'}")
        return super().execute()


class MissingContactNotesClient(InMemorySupabaseClient):
    def table(self, name: str) -> InMemoryQuery:
        if name not in self.tables:
            self.tables[name] = self.tables["contacts"].__class__(name)
        return MissingContactNotesQuery(self, self.tables[name])


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


def test_get_contact_by_id_returns_existing_row():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [{"id": "contact-1", "phone_number": "+15550000001", "display_name": "Maria Lopez", "notes": "VIP"}],
    )

    contact = repository.get_contact_by_id("contact-1")

    assert contact is not None
    assert contact.phone_number == "+15550000001"
    assert contact.display_name == "Maria Lopez"
    assert contact.notes == "VIP"


def test_get_contact_tolerates_legacy_schema_without_notes_column():
    client = MissingContactNotesClient()
    repository = SupabaseRelayRepository(client)
    client.seed(
        "contacts",
        [{"phone_number": "+15550000001", "display_name": "Maria Lopez"}],
    )

    contact = repository.get_contact("+15550000001")

    assert contact is not None
    assert contact.phone_number == "+15550000001"
    assert contact.display_name == "Maria Lopez"
    assert contact.notes is None


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


def test_update_contact_profile_stores_display_name_and_notes_without_erasing_lookup_name():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [{"id": "contact-1", "phone_number": "+15550000001", "display_name": None, "lookup_name": "Lookup Name"}],
    )

    contact = repository.update_contact_profile(
        contact_id="contact-1",
        display_name="Manual Name",
        notes="Prefers WhatsApp updates.",
    )

    stored = client.rows("contacts")[0]
    assert contact is not None
    assert contact.display_name == "Manual Name"
    assert contact.lookup_name == "Lookup Name"
    assert contact.notes == "Prefers WhatsApp updates."
    assert stored["lookup_name"] == "Lookup Name"
    assert stored["notes"] == "Prefers WhatsApp updates."


def test_update_contact_profile_returns_none_for_missing_contact():
    repository, _ = build_repository()

    contact = repository.update_contact_profile(
        contact_id="missing",
        display_name="Missing",
        notes="No row.",
    )

    assert contact is None


def test_import_contact_display_name_creates_and_updates_missing_display_name():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [{"phone_number": "+15550000001", "display_name": None, "lookup_name": "Lookup Name"}],
    )

    existing_contact, existing_action = repository.import_contact_display_name(
        phone_number="+15550000001",
        display_name="Imported Name",
    )
    new_contact, new_action = repository.import_contact_display_name(
        phone_number="+15550000002",
        display_name="New Imported Name",
    )

    rows = client.rows("contacts")
    existing = next(row for row in rows if row["phone_number"] == "+15550000001")
    new = next(row for row in rows if row["phone_number"] == "+15550000002")
    assert existing_action == "updated"
    assert existing_contact.display_name == "Imported Name"
    assert existing["lookup_name"] == "Lookup Name"
    assert new_action == "created"
    assert new_contact.display_name == "New Imported Name"
    assert new["display_name"] == "New Imported Name"


def test_import_contact_display_name_preserves_existing_manual_name_without_overwrite():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [{"phone_number": "+15550000001", "display_name": "Manual Name", "lookup_name": "Lookup Name"}],
    )

    contact, action = repository.import_contact_display_name(
        phone_number="+15550000001",
        display_name="Imported Name",
        overwrite=False,
    )

    stored = client.rows("contacts")[0]
    assert action == "skipped"
    assert contact.display_name == "Manual Name"
    assert stored["display_name"] == "Manual Name"
    assert stored["lookup_name"] == "Lookup Name"


def test_import_contact_display_name_overwrites_only_when_requested():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [{"phone_number": "+15550000001", "display_name": "Manual Name", "lookup_name": "Lookup Name"}],
    )

    contact, action = repository.import_contact_display_name(
        phone_number="+15550000001",
        display_name="Imported Name",
        overwrite=True,
    )

    stored = client.rows("contacts")[0]
    assert action == "updated"
    assert contact.display_name == "Imported Name"
    assert stored["display_name"] == "Imported Name"
    assert stored["lookup_name"] == "Lookup Name"


def test_search_contacts_matches_name_phone_notes_and_returns_conversation_hints():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [
            {
                "id": "contact-1",
                "phone_number": "+15550000001",
                "display_name": "Maria Lopez",
                "lookup_name": "Lookup Maria",
                "notes": "Prefers pickup reminders.",
                "created_at": "2026-06-04T00:00:01+00:00",
            },
            {
                "id": "contact-2",
                "phone_number": "+15550000002",
                "display_name": None,
                "lookup_name": "Signs Client",
                "notes": None,
                "created_at": "2026-06-04T00:00:02+00:00",
            },
        ],
    )
    client.seed(
        "conversations",
        [
            {
                "id": "conversation-old",
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "status": "closed",
                "updated_at": "2026-06-04T00:00:03+00:00",
            },
            {
                "id": "conversation-open",
                "customer_phone": "+15550000001",
                "assigned_employee": "+15551234567",
                "status": "open",
                "updated_at": "2026-06-04T00:00:04+00:00",
            },
        ],
    )
    client.seed(
        "calls",
        [
            {
                "id": "call-1",
                "conversation_id": "conversation-open",
                "direction": "outbound",
                "call_type": "conversation_call",
                "customer_phone": "+15550000001",
                "status": "completed",
                "created_at": "2026-06-04T00:00:05+00:00",
            }
        ],
    )

    rows, has_more = repository.search_contacts(q="pickup", limit=10, offset=0)

    assert has_more is False
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "contact-1"
    assert row["name"] == "Maria Lopez"
    assert row["open_conversation_id"] == "conversation-open"
    assert row["last_conversation_id"] == "conversation-open"
    assert row["latest_call_id"] == "call-1"
    assert row["last_activity_at"] == "2026-06-04T00:00:05+00:00"


def test_search_contacts_paginates_results():
    repository, client = build_repository()
    client.seed(
        "contacts",
        [
            {"id": "contact-1", "phone_number": "+15550000001", "display_name": "Client One"},
            {"id": "contact-2", "phone_number": "+15550000002", "display_name": "Client Two"},
            {"id": "contact-3", "phone_number": "+15550000003", "display_name": "Client Three"},
        ],
    )

    rows, has_more = repository.search_contacts(q="client", limit=2, offset=0)

    assert len(rows) == 2
    assert has_more is True


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


def test_customer_action_request_file_and_event_round_trip():
    repository, client = build_repository()

    request = repository.create_customer_action_request(
        conversation_id="conversation-1",
        contact_id="contact-1",
        request_type="proof",
        status="pending",
        title="Proof approval",
        operator_note="Please review.",
        public_token_hash="token-hash-1",
        created_by="operator@example.com",
    )
    file_row = repository.create_customer_action_file(
        request_id=request["id"],
        role="proof",
        external_url="https://files.example/proof.pdf",
        original_filename="proof.pdf",
        content_type="application/pdf",
        size_bytes=1234,
    )
    event = repository.create_customer_action_event(
        request_id=request["id"],
        conversation_id="conversation-1",
        event_type="created",
        comment="Created request.",
        metadata={"source": "test"},
    )

    by_token = repository.get_customer_action_by_token_hash("token-hash-1")
    actions = repository.list_customer_actions_for_conversation("conversation-1")
    files = repository.list_customer_action_files(request["id"])
    events = repository.list_customer_action_events(request["id"])

    assert by_token == request
    assert actions == [request]
    assert files == [file_row]
    assert events == [event]
    assert client.rows("customer_action_requests")[0]["public_token_hash"] == "token-hash-1"
    assert client.rows("customer_action_files")[0]["external_url"] == "https://files.example/proof.pdf"
    assert client.rows("customer_action_events")[0]["metadata"] == {"source": "test"}


def test_update_customer_action_request_status_returns_updated_row_and_none_for_missing():
    repository, _ = build_repository()
    request = repository.create_customer_action_request(
        conversation_id="conversation-1",
        contact_id=None,
        request_type="proof",
        status="pending",
        title=None,
        operator_note=None,
        public_token_hash="token-hash-1",
    )

    updated = repository.update_customer_action_request_status(
        request_id=request["id"],
        status="approved",
        completed_at="2026-06-18T00:00:00+00:00",
        canceled_at=None,
    )
    missing = repository.update_customer_action_request_status(
        request_id="missing",
        status="approved",
        completed_at="2026-06-18T00:00:00+00:00",
        canceled_at=None,
    )

    assert updated is not None
    assert updated["status"] == "approved"
    assert updated["completed_at"] == "2026-06-18T00:00:00+00:00"
    assert missing is None


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


def test_update_call_recording_does_not_mark_completed_live_call_as_voicemail():
    repository, client = build_repository()
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CA123",
        status="completed",
    )

    call = repository.update_call_recording_by_sid(
        twilio_call_sid="CA123",
        recording_sid="RE123",
        recording_url="https://api.twilio.com/2010-04-01/Accounts/AC123/Recordings/RE123",
        recording_status="completed",
        recording_duration_seconds=42,
        recording_channels=2,
    )

    stored = client.rows("calls")[0]
    assert call is not None
    assert stored["recording_sid"] == "RE123"
    assert stored["recording_status"] == "completed"
    assert stored["outcome"] is None
    assert stored["follow_up_status"] == "none"


def test_update_call_recording_marks_uncompleted_inbound_recording_as_voicemail():
    repository, client = build_repository()
    repository.create_call(
        conversation_id="conversation-1",
        direction="inbound",
        call_type="inbound",
        customer_phone="+15550000001",
        employee_phone="+15551234567",
        twilio_call_sid="CA123",
        status="ringing",
    )

    call = repository.update_call_recording_by_sid(
        twilio_call_sid="CA123",
        recording_sid="RE123",
        recording_url="https://api.twilio.com/2010-04-01/Accounts/AC123/Recordings/RE123",
        recording_status="completed",
        recording_duration_seconds=42,
        recording_channels=1,
    )

    stored = client.rows("calls")[0]
    assert call is not None
    assert stored["outcome"] == "voicemail"
    assert stored["follow_up_status"] == "needed"


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
