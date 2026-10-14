import io
import re

from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

_HEIC_CONTENT_TYPES = {"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"}
_HEIC_EXTENSIONS = (".heic", ".heif")
_MMS_SAFE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def is_heic(content_type: str, filename: str) -> bool:
    clean_type = (content_type or "").split(";")[0].strip().lower()
    if clean_type in _HEIC_CONTENT_TYPES:
        return True
    return (filename or "").lower().endswith(_HEIC_EXTENSIONS)


def normalize_image(content: bytes, content_type: str, filename: str) -> tuple[bytes, str, str]:
    """Convert HEIC/HEIF (common iPhone default) to JPEG. Twilio and most carriers reject HEIC outright."""
    if not is_heic(content_type, filename):
        return content, content_type, filename

    with Image.open(io.BytesIO(content)) as image:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=90)

    new_filename = re.sub(r"\.(heic|heif)$", ".jpg", filename, flags=re.IGNORECASE)
    if new_filename == filename:
        new_filename = f"{filename}.jpg"
    return buffer.getvalue(), "image/jpeg", new_filename


def compress_for_mms(
    content: bytes,
    content_type: str,
    *,
    target_bytes: int,
    max_dimension: int,
) -> tuple[bytes, str] | None:
    """
    Resize/re-encode an image to fit real-world MMS carrier limits (AT&T caps
    as low as ~600KB-1MB). Returns None if the image is already under
    target_bytes, so the caller can send the original unchanged.
    """
    clean_type = (content_type or "").split(";")[0].strip().lower()
    if clean_type not in _MMS_SAFE_CONTENT_TYPES:
        return None
    if len(content) <= target_bytes:
        return None

    with Image.open(io.BytesIO(content)) as source:
        image = source.convert("RGB")

    width, height = image.size
    longest_edge = max(width, height)
    if longest_edge > max_dimension:
        scale = max_dimension / longest_edge
        image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)

    # MMS attachments don't preserve transparency and don't need print-grade
    # fidelity, so we always re-encode to JPEG for best size-to-quality ratio.
    buffer = io.BytesIO()
    quality = 90
    while quality >= 30:
        buffer.seek(0)
        buffer.truncate()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        if buffer.tell() <= target_bytes:
            break
        quality -= 10

    return buffer.getvalue(), "image/jpeg"
