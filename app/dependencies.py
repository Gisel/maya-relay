from functools import lru_cache

from fastapi import Depends

from app.attachments import AttachmentStore, SupabaseAttachmentStore
from app.ai_triage import MessageTriage, NoopMessageTriage, OpenAIMessageTriage
from app.config import Settings, get_settings
from app.db import RelayRepository, SupabaseRelayRepository
from app.lookup import ContactNameLookup, NoopContactNameLookup, TwilioContactNameLookup
from app.operator_auth import MayaOperatorAuthService, OperatorAuthService
from app.services.customer_actions import CustomerActionService
from app.services.relay import RelayService
from app.twilio_client import MessageSender, TwilioMessageSender, TwilioVoiceCaller, VoiceCaller


@lru_cache
def get_repository() -> RelayRepository:
    return SupabaseRelayRepository.from_settings(get_settings())


@lru_cache
def get_sender() -> MessageSender:
    return TwilioMessageSender(get_settings())


@lru_cache
def get_voice_caller() -> VoiceCaller:
    return TwilioVoiceCaller(get_settings())


@lru_cache
def get_operator_auth_service() -> OperatorAuthService:
    return MayaOperatorAuthService(get_settings())


@lru_cache
def get_attachment_store() -> AttachmentStore:
    return SupabaseAttachmentStore(settings=get_settings(), repository=get_repository())


@lru_cache
def get_contact_name_lookup() -> ContactNameLookup:
    settings = get_settings()
    if not settings.enable_twilio_lookup:
        return NoopContactNameLookup()
    return TwilioContactNameLookup(settings)


@lru_cache
def get_message_triage() -> MessageTriage:
    settings = get_settings()
    if not settings.enable_ai_triage:
        return NoopMessageTriage()
    return OpenAIMessageTriage(settings)


def get_relay_service() -> RelayService:
    settings: Settings = get_settings()
    return RelayService(
        settings=settings,
        repository=get_repository(),
        sender=get_sender(),
        attachment_store=get_attachment_store(),
        contact_name_lookup=get_contact_name_lookup(),
        message_triage=get_message_triage(),
    )


def get_customer_action_service(
    settings: Settings = Depends(get_settings),
    repository: RelayRepository = Depends(get_repository),
) -> CustomerActionService:
    return CustomerActionService(settings=settings, repository=repository)
