from app.config import Settings
from app.models import IncomingMessage
from app.services.relay import RelayService
from tests.fakes import FakeRepository, FakeSender


def build_service() -> tuple[RelayService, FakeRepository, FakeSender]:
    settings = Settings(
        FRANCISCO_PHONE="+15551234567",
        MAYA_BUSINESS_NUMBER="+13852208404",
        VERIFY_TWILIO_SIGNATURE=False,
    )
    repository = FakeRepository()
    sender = FakeSender()
    return RelayService(settings=settings, repository=repository, sender=sender), repository, sender


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
            "body": "From customer +15550000001:\nI need a sign quote.",
        }
    ]
    assert repository.messages[0]["direction"] == "customer_to_employee"
    assert repository.messages[1]["direction"] == "system"


def test_employee_reply_routes_to_latest_open_customer_conversation():
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
            body="Thanks, send us the dimensions.",
        )
    )

    assert result == {"status": "forwarded_to_customer", "conversation_id": "conversation-1"}
    assert sender.sent_messages[-1] == {
        "sid": "SMfake2",
        "to_phone": "+15550000001",
        "body": "Thanks, send us the dimensions.",
    }


def test_employee_reply_without_open_conversation_fails_safely():
    service, repository, sender = build_service()

    result = service.handle_inbound_sms(
        IncomingMessage(
            message_sid="SMemployee",
            from_phone="+15551234567",
            to_phone="+13852208404",
            body="Hello?",
        )
    )

    assert result == {"status": "no_open_conversation", "conversation_id": None}
    assert repository.messages == []
    assert sender.sent_messages == []

