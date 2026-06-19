import pytest

from app.config import Settings
from app.customer_actions import (
    CustomerActionFileInput,
    customer_action_token_secret,
    hash_public_token,
)
from app.models import Conversation
from app.services.customer_actions import (
    CustomerActionNotFound,
    CustomerActionService,
    CustomerActionStateError,
    CustomerActionValidationError,
)
from tests.fakes import FakeRepository


def build_service() -> tuple[CustomerActionService, FakeRepository]:
    repository = FakeRepository()
    repository.conversations.append(
        Conversation(
            id="conversation-1",
            customer_phone="+15550000001",
            assigned_employee="+15551234567",
            status="open",
            conversation_code="ABC12345",
            customer_channel="sms",
        )
    )
    settings = Settings(
        APP_BASE_URL="https://relay.example",
        CUSTOMER_ACTION_TOKEN_SECRET="test-action-secret",
    )
    return CustomerActionService(settings=settings, repository=repository), repository


def test_create_proof_request_stores_hash_file_and_created_event():
    service, repository = build_service()

    result = service.create_proof_request(
        conversation_id="conversation-1",
        title="Business card proof",
        operator_note="Please review the logo.",
        proof_url="https://files.example/proof.pdf",
        created_by="operator@example.com",
    )

    request = result["request"]
    token = result["public_token"]
    assert result["public_url"] == f"https://relay.example/proof/{token}"
    assert request["request_type"] == "proof"
    assert request["status"] == "pending"
    assert request["conversation_id"] == "conversation-1"
    assert request["contact_id"] == "contact-1"
    assert request["public_token_hash"] == hash_public_token(token, "test-action-secret")
    assert token not in request["public_token_hash"]
    assert repository.customer_action_files == [
        {
            "id": "customer-action-file-1",
            "request_id": request["id"],
            "role": "proof",
            "bucket": None,
            "object_path": None,
            "public_url": None,
            "external_url": "https://files.example/proof.pdf",
            "original_filename": None,
            "content_type": None,
            "size_bytes": None,
            "created_at": repository.customer_action_files[0]["created_at"],
        }
    ]
    assert repository.customer_action_events[0]["event_type"] == "created"


def test_create_proof_request_accepts_stored_file_reference():
    service, repository = build_service()

    result = service.create_proof_request(
        conversation_id="conversation-1",
        proof_file=CustomerActionFileInput(
            role="proof",
            bucket="proofs",
            object_path="conversation-1/proof.pdf",
            public_url="https://files.example/proof.pdf",
            original_filename="proof.pdf",
            content_type="application/pdf",
            size_bytes=1234,
        ),
    )

    file_row = repository.customer_action_files[0]
    assert result["request"]["status"] == "pending"
    assert file_row["bucket"] == "proofs"
    assert file_row["object_path"] == "conversation-1/proof.pdf"
    assert file_row["public_url"] == "https://files.example/proof.pdf"


def test_create_proof_request_requires_one_proof_source():
    service, _ = build_service()

    with pytest.raises(CustomerActionValidationError):
        service.create_proof_request(conversation_id="conversation-1")

    with pytest.raises(CustomerActionValidationError):
        service.create_proof_request(
            conversation_id="conversation-1",
            proof_url="https://files.example/proof.pdf",
            proof_file=CustomerActionFileInput(role="proof", public_url="https://files.example/proof.pdf"),
        )


def test_approve_proof_request_updates_status_and_records_event():
    service, repository = build_service()
    created = service.create_proof_request(
        conversation_id="conversation-1",
        proof_url="https://files.example/proof.pdf",
    )

    approved = service.approve_proof_request(public_token=created["public_token"], comment="Looks good.")

    assert approved["status"] == "approved"
    assert approved["completed_at"] is not None
    assert repository.customer_action_events[-1]["event_type"] == "approved"
    assert repository.customer_action_events[-1]["comment"] == "Looks good."


def test_approve_proof_request_is_idempotent_after_approval():
    service, repository = build_service()
    created = service.create_proof_request(
        conversation_id="conversation-1",
        proof_url="https://files.example/proof.pdf",
    )

    first = service.approve_proof_request(public_token=created["public_token"])
    second = service.approve_proof_request(public_token=created["public_token"])

    assert second == first
    assert [event["event_type"] for event in repository.customer_action_events] == ["created", "approved"]


def test_request_proof_changes_requires_comment_and_blocks_after_approval():
    service, _ = build_service()
    created = service.create_proof_request(
        conversation_id="conversation-1",
        proof_url="https://files.example/proof.pdf",
    )

    with pytest.raises(CustomerActionValidationError):
        service.request_proof_changes(public_token=created["public_token"], comment=" ")

    service.approve_proof_request(public_token=created["public_token"])
    with pytest.raises(CustomerActionStateError):
        service.request_proof_changes(public_token=created["public_token"], comment="Make the logo bigger.")


def test_request_proof_changes_updates_status_and_records_comment():
    service, repository = build_service()
    created = service.create_proof_request(
        conversation_id="conversation-1",
        proof_url="https://files.example/proof.pdf",
    )

    changed = service.request_proof_changes(
        public_token=created["public_token"],
        comment="Please use the other logo.",
    )

    assert changed["status"] == "changes_requested"
    assert repository.customer_action_events[-1]["event_type"] == "changes_requested"
    assert repository.customer_action_events[-1]["comment"] == "Please use the other logo."


def test_cancel_request_updates_pending_request_and_records_event():
    service, repository = build_service()
    created = service.create_assets_request(
        conversation_id="conversation-1",
        title="Upload logo files",
    )

    canceled = service.cancel_request(request_id=created["request"]["id"], comment="Duplicate request.")

    assert canceled["status"] == "canceled"
    assert canceled["canceled_at"] is not None
    assert canceled["completed_at"] is None
    assert repository.customer_action_events[-1]["event_type"] == "canceled"
    assert repository.customer_action_events[-1]["comment"] == "Duplicate request."


def test_cancel_request_blocks_final_request():
    service, _ = build_service()
    created = service.create_proof_request(
        conversation_id="conversation-1",
        proof_url="https://files.example/proof.pdf",
    )
    service.approve_proof_request(public_token=created["public_token"])

    with pytest.raises(CustomerActionStateError):
        service.cancel_request(request_id=created["request"]["id"])


def test_unknown_token_is_not_found():
    service, _ = build_service()

    with pytest.raises(CustomerActionNotFound):
        service.approve_proof_request(public_token="missing-token")


def test_customer_action_token_secret_requires_explicit_secret_in_production():
    settings = Settings(APP_ENV="production", CUSTOMER_ACTION_TOKEN_SECRET="")

    with pytest.raises(RuntimeError):
        customer_action_token_secret(settings)
