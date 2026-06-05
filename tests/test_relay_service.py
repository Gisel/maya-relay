from app.config import Settings
from app.models import Contact
from app.models import IncomingMessage
from app.services.relay import RelayService, _extract_suggested_reply, _triage_context_note
from tests.fakes import FakeLookup, FakeRepository, FakeSender, FakeTriage


def build_service(
    lookup: FakeLookup | None = None,
    *,
    employee_phone_numbers: str = "",
    triage: FakeTriage | None = None,
) -> tuple[RelayService, FakeRepository, FakeSender]:
    settings = Settings(
        FRANCISCO_PHONE="+15551234567",
        EMPLOYEE_PHONE_NUMBERS=employee_phone_numbers,
        MAYA_BUSINESS_NUMBER="+13852208404",
        VERIFY_TWILIO_SIGNATURE=False,
        ENABLE_AI_TRIAGE=False,
    )
    repository = FakeRepository()
    sender = FakeSender()
    return (
        RelayService(
            settings=settings,
            repository=repository,
            sender=sender,
            contact_name_lookup=lookup,
            message_triage=triage,
        ),
        repository,
        sender,
    )


def test_triage_suggestion_helpers_extract_copy_ready_reply():
    note = "Intent: quote\nMissing: size\n---\n#C0001 Please send the size."

    suggestion = _extract_suggested_reply(note, "C0001")

    assert suggestion == "#C0001 Please send the size."
    assert _triage_context_note(note, suggestion) == "Intent: quote\nMissing: size"


def test_customer_message_creates_conversation_and_forwards_to_employee():
    service, repository, sender = build_service()

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="I need a sign quote.",
        )
    )

    assert result == {"status": "forwarded_to_employee", "conversation_id": "conversation-1"}
    assert len(repository.conversations) == 1
    assert sender.sent_messages == [
        {
            "sid": "SMfake1",
            "to_phone": "+15551234567",
            "body": (
                "From customer +15550000001 [#C0001]:\n"
                "I need a sign quote.\n"
                "Reply with #C0001 your message"
            ),
        }
    ]
    assert repository.messages[0]["direction"] == "customer_to_employee"
    assert repository.messages[1]["direction"] == "system"


def test_customer_media_is_stored_and_forwarded_as_attachment_link():
    service, repository, sender = build_service()

    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Here is the design",
            num_media=1,
            media_urls=("https://api.twilio.com/media/image.jpg",),
            media_content_types=("image/jpeg",),
        )
    )

    assert repository.messages[0]["num_media"] == 1
    assert repository.messages[0]["media_urls"] == ("https://api.twilio.com/media/image.jpg",)
    assert sender.sent_messages[0]["body"] == (
        "From customer +15550000001 [#C0001]:\n"
        "Here is the design\n"
        "Attachment 1 (image/jpeg): https://api.twilio.com/media/image.jpg\n"
        "Reply with #C0001 your message"
    )


def test_customer_lookup_name_is_cached_and_used_in_forwarded_label():
    lookup = FakeLookup({"+15550000001": "Maria Lopez"})
    service, repository, sender = build_service(lookup)

    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Hola",
        )
    )

    assert lookup.looked_up == ["+15550000001"]
    assert repository.get_contact("+15550000001").lookup_name == "Maria Lopez"
    assert sender.sent_messages[0]["body"] == (
        "From Maria Lopez (+15550000001) [#C0001]:\n"
        "Hola\n"
        "Reply with #C0001 your message"
    )


def test_customer_message_includes_ai_triage_note_when_available():
    triage = FakeTriage(
        "Intent: quote request\n"
        "Missing: size and deadline\n"
        "---\n"
        "#C0001 Please send size and deadline."
    )
    service, _, sender = build_service(triage=triage)

    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="I need a banner quote.",
        )
    )

    assert triage.calls == [
        {"body": "I need a banner quote.", "has_attachments": False, "conversation_code": "C0001"}
    ]
    assert sender.sent_messages[0]["body"] == (
        "From customer +15550000001 [#C0001]:\n"
        "I need a banner quote.\n"
        "Reply with #C0001 your message\n"
        "---\n"
        "AI note:\n"
        "Intent: quote request\n"
        "Missing: size and deadline"
    )
    assert sender.sent_messages[1]["body"] == "#C0001 Please send size and deadline."


def test_customer_message_still_forwards_when_ai_triage_fails():
    service, _, sender = build_service(triage=FakeTriage(should_raise=True))

    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="I need a quote.",
        )
    )

    assert sender.sent_messages[0]["body"] == (
        "From customer +15550000001 [#C0001]:\n"
        "I need a quote.\n"
        "Reply with #C0001 your message"
    )


def test_existing_contact_name_is_used_without_lookup():
    lookup = FakeLookup({"+15550000001": "Lookup Name"})
    service, repository, sender = build_service(lookup)
    repository.contacts.append(
        Contact(id="contact-1", phone_number="+15550000001", display_name="Saved Name")
    )

    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Hola",
        )
    )

    assert lookup.looked_up == []
    assert sender.sent_messages[0]["body"] == (
        "From Saved Name (+15550000001) [#C0001]:\n"
        "Hola\n"
        "Reply with #C0001 your message"
    )


def test_employee_reply_does_not_use_lookup_for_default_label():
    lookup = FakeLookup({"+15550000001": "Customer Name", "+15551234567": "Paid Lookup Employee Name"})
    service, _, sender = build_service(lookup)
    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Hello",
        )
    )

    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15551234567",
            to_phone="+13852208404",
            body="#C0001 Thanks.",
        )
    )

    assert lookup.looked_up == ["+15550000001"]
    assert sender.sent_messages[-1]["body"] == "Thanks."


def test_employee_reply_routes_by_conversation_code():
    service, _, sender = build_service()
    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Hello",
        )
    )

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15551234567",
            to_phone="+13852208404",
            body="#C0001 Thanks, send us the dimensions.",
        )
    )

    assert result == {"status": "forwarded_to_customer", "conversation_id": "conversation-1"}
    assert sender.sent_messages[-1] == {
        "sid": "SMfake2",
        "to_phone": "+15550000001",
        "body": "Thanks, send us the dimensions.",
    }


def test_employee_reply_to_whatsapp_conversation_uses_whatsapp_channel():
    service, repository, sender = build_service()
    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="WMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Hello on WhatsApp",
            channel="whatsapp",
        )
    )

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15551234567",
            to_phone="+13852208404",
            body="#C0001 Thanks, WhatsApp customer.",
        )
    )

    assert result == {"status": "forwarded_to_customer", "conversation_id": "conversation-1"}
    assert repository.conversations[0].customer_channel == "whatsapp"
    assert sender.sent_messages[-1] == {
        "sid": "SMfake2",
        "to_phone": "+15550000001",
        "body": "Thanks, WhatsApp customer.",
        "channel": "whatsapp",
    }


def test_allowed_alternate_employee_phone_routes_by_conversation_code():
    service, _, sender = build_service(employee_phone_numbers="+15557654321")
    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Hello",
        )
    )

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15557654321",
            to_phone="+13852208404",
            body="#C0001 This is Francisco from another phone.",
        )
    )

    assert result == {"status": "forwarded_to_customer", "conversation_id": "conversation-1"}
    assert sender.sent_messages[-1] == {
        "sid": "SMfake2",
        "to_phone": "+15550000001",
        "body": "This is Francisco from another phone.",
    }


def test_employee_phone_matching_normalizes_configured_phone_number():
    service, _, sender = build_service(employee_phone_numbers="(555) 765-4321")
    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Hello",
        )
    )

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15557654321",
            to_phone="+13852208404",
            body="#C0001 This is Francisco from a formatted config phone.",
        )
    )

    assert result == {"status": "forwarded_to_customer", "conversation_id": "conversation-1"}
    assert sender.sent_messages[-1]["to_phone"] == "+15550000001"


def test_employee_reply_missing_conversation_code_fails_safely():
    service, repository, sender = build_service()
    service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMcustomer",
            from_phone="+15550000001",
            to_phone="+13852208404",
            body="Hello",
        )
    )

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15551234567",
            to_phone="+13852208404",
            body="Thanks, send us the dimensions.",
        )
    )

    assert result == {"status": "missing_conversation_code", "conversation_id": None}
    assert repository.messages[-1]["direction"] == "system"
    assert sender.sent_messages[-1] == {
        "sid": "SMfake2",
        "to_phone": "+15551234567",
        "body": "Please include the customer code, like #A1B2C3D4 your reply.",
    }


def test_employee_reply_invalid_conversation_code_fails_safely():
    service, _, sender = build_service()

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15551234567",
            to_phone="+13852208404",
            body="#BAD12345 Thanks.",
        )
    )

    assert result == {"status": "no_open_conversation", "conversation_id": None}
    assert sender.sent_messages == [
        {
            "sid": "SMfake1",
            "to_phone": "+15551234567",
            "body": "I could not find an open conversation for #BAD12345. Check the code and try again.",
        }
    ]


def test_employee_reply_without_open_conversation_fails_safely():
    service, repository, sender = build_service()

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15551234567",
            to_phone="+13852208404",
            body="#C9999 Hello?",
        )
    )

    assert result == {"status": "no_open_conversation", "conversation_id": None}
    assert repository.messages == []
    assert sender.sent_messages == [
        {
            "sid": "SMfake1",
            "to_phone": "+15551234567",
            "body": "I could not find an open conversation for #C9999. Check the code and try again.",
        }
    ]
