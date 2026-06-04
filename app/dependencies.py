from functools import lru_cache

from app.attachments import AttachmentStore, SupabaseAttachmentStore
from app.config import Settings, get_settings
from app.db import RelayRepository, SupabaseRelayRepository
from app.services.relay import RelayService
from app.twilio_client import MessageSender, TwilioMessageSender


@lru_cache
def get_repository() -> RelayRepository:
    return SupabaseRelayRepository.from_settings(get_settings())


@lru_cache
def get_sender() -> MessageSender:
    return TwilioMessageSender(get_settings())


@lru_cache
def get_attachment_store() -> AttachmentStore:
    return SupabaseAttachmentStore(settings=get_settings(), repository=get_repository())


def get_relay_service() -> RelayService:
    settings: Settings = get_settings()
    return RelayService(
        settings=settings,
        repository=get_repository(),
        sender=get_sender(),
        attachment_store=get_attachment_store(),
    )
