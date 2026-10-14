from fastapi import UploadFile

from app.attachments import AttachmentStore, StoredAttachment, UploadedAttachment
from app.db import RelayRepository
from app.image_processing import compress_for_mms, is_heic, normalize_image
from app.short_links import generate_short_token


def read_uploads(files: list[UploadFile]) -> tuple[UploadedAttachment, ...]:
    uploads: list[UploadedAttachment] = []
    for file in files:
        if not file.filename:
            continue
        content = file.file.read()
        if not content:
            continue
        uploads.append(
            UploadedAttachment(
                filename=file.filename,
                content=content,
                content_type=file.content_type or "application/octet-stream",
            )
        )
    return tuple(uploads)


def reply_body_with_attachments(
    body: str,
    attachments: tuple[StoredAttachment, ...],
    *,
    full_quality_links: tuple[str, ...] = (),
) -> str:
    lines = [body] if body else []
    attachment_number = 1
    for attachment in attachments:
        if is_image_content_type(attachment.content_type):
            continue
        lines.append(f"Attachment {attachment_number} ({attachment.content_type}): {attachment.public_url}")
        attachment_number += 1
    for url in full_quality_links:
        lines.append(f"See original photo: {url}")
    return "\n".join(lines)


def normalize_image_uploads(uploads: tuple[UploadedAttachment, ...]) -> tuple[UploadedAttachment, ...]:
    """Convert HEIC/HEIF uploads to JPEG so Twilio and browsers can render them. Other files pass through unchanged."""
    normalized: list[UploadedAttachment] = []
    for upload in uploads:
        if not is_heic(upload.content_type, upload.filename):
            normalized.append(upload)
            continue
        try:
            content, content_type, filename = normalize_image(upload.content, upload.content_type, upload.filename)
        except Exception:
            normalized.append(upload)
            continue
        normalized.append(UploadedAttachment(filename=filename, content=content, content_type=content_type))
    return tuple(normalized)


def prepare_mms_media(
    *,
    attachment_store: AttachmentStore,
    repository: RelayRepository,
    app_base_url: str,
    object_prefix: str,
    uploads: tuple[UploadedAttachment, ...],
    stored_attachments: tuple[StoredAttachment, ...],
    target_bytes: int,
    max_dimension: int,
) -> tuple[tuple[str, ...], tuple[StoredAttachment, ...], tuple[str, ...]]:
    """
    Build carrier-safe MMS media URLs for outbound sending.

    `uploads` and `stored_attachments` must correspond 1:1 (same order, same
    length) as returned by store_uploaded_attachments(). For any image over
    `target_bytes`, a second, compressed copy is uploaded and its URL is used
    for Twilio instead of the original. Returns:
      - media_urls: URLs to pass to MessageSender.send_message(media_urls=...)
      - compressed_attachments: extra StoredAttachments to persist for audit
      - full_quality_links: short mayagraphics.co/i/<token> URLs that redirect
        to the original full-res attachment, for appending a "See original
        photo" link to the outbound message body
    """
    media_urls: list[str] = []
    compressed_attachments: list[StoredAttachment] = []
    full_quality_links: list[str] = []
    for upload, attachment in zip(uploads, stored_attachments):
        if not is_image_content_type(attachment.content_type):
            continue
        try:
            result = compress_for_mms(
                upload.content,
                attachment.content_type,
                target_bytes=target_bytes,
                max_dimension=max_dimension,
            )
        except Exception:
            result = None
        if result is None:
            media_urls.append(attachment.public_url)
            continue

        compressed_content, compressed_content_type = result
        compressed_upload = UploadedAttachment(
            filename=f"mms-{upload.filename}",
            content=compressed_content,
            content_type=compressed_content_type,
        )
        compressed = attachment_store.store_uploaded_attachments(
            object_prefix=f"{object_prefix}/mms",
            files=(compressed_upload,),
        )[0]
        media_urls.append(compressed.public_url)
        compressed_attachments.append(compressed)
        try:
            link = _short_link_for(repository, app_base_url, attachment.public_url)
        except Exception:
            link = attachment.public_url
        full_quality_links.append(link)
    return tuple(media_urls), tuple(compressed_attachments), tuple(full_quality_links)


def _short_link_for(repository: RelayRepository, app_base_url: str, target_url: str) -> str:
    token = generate_short_token()
    repository.create_short_link(token=token, target_url=target_url)
    return f"{app_base_url.rstrip('/')}/i/{token}"


def image_attachment_urls(attachments: tuple[StoredAttachment, ...]) -> tuple[str, ...]:
    return tuple(
        attachment.public_url
        for attachment in attachments
        if is_image_content_type(attachment.content_type)
    )


def is_image_content_type(content_type: str) -> bool:
    return content_type.lower().startswith("image/")
