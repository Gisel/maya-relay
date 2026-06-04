from functools import lru_cache

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


def get_relay_service() -> RelayService:
    settings: Settings = get_settings()
    return RelayService(settings=settings, repository=get_repository(), sender=get_sender())

