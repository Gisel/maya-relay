import mimetypes
import uuid
from dataclasses import dataclass
from typing import Protocol

import requests
from supabase import create_client

from app.config import Settings
from app.db import RelayRepository


@dataclass(frozen=True)
class StoredAttachment:
    source_url: str
    public_url: str
    content_type: str
    bucket: str
    object_path: str


class AttachmentStore(Protocol):
    def store_message_attachments(
        self,
        *,
        message_id: str,
        source_urls: tuple[str, ...],
        content_types: tuple[str, ...],
    ) -> tuple[StoredAttachment, ...]:
        ...


class NoopAttachmentStore:
    def store_message_attachments(
        self,
        *,
        message_id: str,
        source_urls: tuple[str, ...],
        content_types: tuple[str, ...],
    ) -> tuple[StoredAttachment, ...]:
        return tuple(
            StoredAttachment(
                source_url=url,
                public_url=url,
                content_type=content_types[index] if index < len(content_types) else "application/octet-stream",
                bucket="",
                object_path="",
            )
            for index, url in enumerate(source_urls)
        )


class SupabaseAttachmentStore:
    def __init__(self, *, settings: Settings, repository: RelayRepository):
        self.settings = settings
        self.repository = repository
        self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        self.bucket = settings.supabase_attachments_bucket

    def store_message_attachments(
        self,
        *,
        message_id: str,
        source_urls: tuple[str, ...],
        content_types: tuple[str, ...],
    ) -> tuple[StoredAttachment, ...]:
        stored: list[StoredAttachment] = []
        for index, source_url in enumerate(source_urls):
            content_type = content_types[index] if index < len(content_types) else "application/octet-stream"
            stored.append(self._store_one(message_id, source_url, content_type))
        return tuple(stored)

    def _store_one(self, message_id: str, source_url: str, content_type: str) -> StoredAttachment:
        response = requests.get(
            source_url,
            auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token),
            timeout=30,
        )
        response.raise_for_status()

        final_content_type = response.headers.get("content-type") or content_type
        object_path = f"messages/{message_id}/{uuid.uuid4()}{_extension_for_content_type(final_content_type)}"
        self.client.storage.from_(self.bucket).upload(
            object_path,
            response.content,
            {"content-type": final_content_type, "upsert": "false"},
        )
        public_url = self.client.storage.from_(self.bucket).get_public_url(object_path)

        self.repository.create_message_attachment(
            message_id=message_id,
            bucket=self.bucket,
            object_path=object_path,
            public_url=public_url,
            source_url=source_url,
            content_type=final_content_type,
            size_bytes=len(response.content),
        )
        return StoredAttachment(
            source_url=source_url,
            public_url=public_url,
            content_type=final_content_type,
            bucket=self.bucket,
            object_path=object_path,
        )


def _extension_for_content_type(content_type: str) -> str:
    clean_type = content_type.split(";")[0].strip().lower()
    if clean_type == "image/jpeg":
        return ".jpg"
    return mimetypes.guess_extension(clean_type) or ""
