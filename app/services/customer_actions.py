from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.customer_actions import (
    CustomerActionFileInput,
    build_public_action_url,
    customer_action_token_secret,
    generate_public_token,
    hash_public_token,
)
from app.db import RelayRepository


class CustomerActionError(Exception):
    pass


class CustomerActionNotFound(CustomerActionError):
    pass


class CustomerActionValidationError(CustomerActionError, ValueError):
    pass


class CustomerActionStateError(CustomerActionError):
    pass


class CustomerActionService:
    def __init__(self, *, settings: Settings, repository: RelayRepository):
        self.settings = settings
        self.repository = repository

    def create_proof_request(
        self,
        *,
        conversation_id: str,
        title: str | None = None,
        operator_note: str | None = None,
        proof_file: CustomerActionFileInput | None = None,
        proof_url: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        conversation = self.repository.get_conversation(conversation_id)
        if conversation is None:
            raise CustomerActionValidationError("Conversation not found.")

        file_input = self._proof_file_input(proof_file=proof_file, proof_url=proof_url)
        contact = self.repository.get_or_create_contact(conversation.customer_phone)
        token = generate_public_token()
        token_hash = hash_public_token(token, customer_action_token_secret(self.settings))
        now = _now_iso()

        request = self.repository.create_customer_action_request(
            conversation_id=conversation.id,
            contact_id=contact.id,
            request_type="proof",
            status="pending",
            title=(title or "Proof approval").strip(),
            operator_note=_clean_optional_text(operator_note),
            public_token_hash=token_hash,
            expires_at=None,
            created_by=_clean_optional_text(created_by),
        )
        self.repository.create_customer_action_file(request_id=request["id"], **file_input.__dict__)
        self.repository.create_customer_action_event(
            request_id=request["id"],
            conversation_id=conversation.id,
            event_type="created",
            comment=None,
            metadata={"created_at": now},
        )

        return {
            "request": request,
            "public_token": token,
            "public_url": build_public_action_url(self.settings.app_base_url, action_type="proof", token=token),
        }

    def approve_proof_request(self, *, public_token: str, comment: str | None = None) -> dict[str, Any]:
        request = self._get_pending_or_final_proof(public_token)
        if request["status"] == "approved":
            return request
        self._ensure_pending(request)

        updated = self.repository.update_customer_action_request_status(
            request_id=request["id"],
            status="approved",
            completed_at=_now_iso(),
            canceled_at=None,
        )
        if updated is None:
            raise CustomerActionNotFound("Proof request not found.")
        self.repository.create_customer_action_event(
            request_id=request["id"],
            conversation_id=request["conversation_id"],
            event_type="approved",
            comment=_clean_optional_text(comment),
            metadata={},
        )
        return updated

    def request_proof_changes(self, *, public_token: str, comment: str) -> dict[str, Any]:
        clean_comment = _clean_optional_text(comment)
        if not clean_comment:
            raise CustomerActionValidationError("Change request comment is required.")

        request = self._get_pending_or_final_proof(public_token)
        if request["status"] == "changes_requested":
            return request
        self._ensure_pending(request)

        updated = self.repository.update_customer_action_request_status(
            request_id=request["id"],
            status="changes_requested",
            completed_at=_now_iso(),
            canceled_at=None,
        )
        if updated is None:
            raise CustomerActionNotFound("Proof request not found.")
        self.repository.create_customer_action_event(
            request_id=request["id"],
            conversation_id=request["conversation_id"],
            event_type="changes_requested",
            comment=clean_comment,
            metadata={},
        )
        return updated

    def _get_pending_or_final_proof(self, public_token: str) -> dict[str, Any]:
        token_hash = hash_public_token(public_token, customer_action_token_secret(self.settings))
        request = self.repository.get_customer_action_by_token_hash(token_hash)
        if request is None or request.get("request_type") != "proof":
            raise CustomerActionNotFound("Proof request not found.")
        return request

    @staticmethod
    def _ensure_pending(request: dict[str, Any]) -> None:
        if request["status"] != "pending":
            raise CustomerActionStateError(f"Proof request is already {request['status']}.")

    @staticmethod
    def _proof_file_input(
        *,
        proof_file: CustomerActionFileInput | None,
        proof_url: str | None,
    ) -> CustomerActionFileInput:
        clean_url = (proof_url or "").strip()
        if proof_file is not None and clean_url:
            raise CustomerActionValidationError("Provide either proof_file or proof_url, not both.")
        if proof_file is None and not clean_url:
            raise CustomerActionValidationError("Proof file or proof URL is required.")
        if proof_file is not None:
            if proof_file.role != "proof":
                raise CustomerActionValidationError("Proof file role must be 'proof'.")
            if not (proof_file.public_url or proof_file.external_url or proof_file.object_path):
                raise CustomerActionValidationError("Proof file must include a URL or storage object path.")
            return proof_file
        return CustomerActionFileInput(role="proof", external_url=clean_url)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_optional_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None
