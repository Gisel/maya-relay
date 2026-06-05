from fastapi import UploadFile

from app.attachments import StoredAttachment, UploadedAttachment


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


def reply_body_with_attachments(body: str, attachments: tuple[StoredAttachment, ...]) -> str:
    lines = [body] if body else []
    attachment_number = 1
    for attachment in attachments:
        if is_image_content_type(attachment.content_type):
            continue
        lines.append(f"Attachment {attachment_number} ({attachment.content_type}): {attachment.public_url}")
        attachment_number += 1
    return "\n".join(lines)


def image_attachment_urls(attachments: tuple[StoredAttachment, ...]) -> tuple[str, ...]:
    return tuple(
        attachment.public_url
        for attachment in attachments
        if is_image_content_type(attachment.content_type)
    )


def is_image_content_type(content_type: str) -> bool:
    return content_type.lower().startswith("image/")
