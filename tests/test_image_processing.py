import io
import os

import pillow_heif
from PIL import Image

from app.image_processing import compress_for_mms, is_heic, normalize_image


def _jpeg_bytes(width: int, height: int, *, quality: int = 95, noisy: bool = False) -> bytes:
    if noisy:
        # Random noise defeats JPEG's compression, giving a realistic "big photo" size.
        image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    else:
        image = Image.new("RGB", (width, height), color=(120, 40, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _heic_bytes(width: int = 64, height: int = 64) -> bytes:
    image = Image.new("RGB", (width, height), color=(255, 0, 0))
    heif_file = pillow_heif.from_pillow(image)
    buffer = io.BytesIO()
    heif_file.save(buffer, quality=80)
    return buffer.getvalue()


def test_is_heic_detects_by_content_type():
    assert is_heic("image/heic", "photo.jpg") is True
    assert is_heic("image/heif", "photo") is True
    assert is_heic("image/jpeg", "photo.jpg") is False


def test_is_heic_detects_by_extension_when_content_type_generic():
    assert is_heic("application/octet-stream", "IMG_3531.HEIC") is True
    assert is_heic("application/octet-stream", "IMG_3531.jpg") is False


def test_normalize_image_converts_heic_to_jpeg():
    content, content_type, filename = normalize_image(_heic_bytes(), "image/heic", "IMG_3531.HEIC")

    assert content_type == "image/jpeg"
    assert filename == "IMG_3531.jpg"
    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "JPEG"
        assert image.size == (64, 64)


def test_normalize_image_passes_through_non_heic_unchanged():
    original = _jpeg_bytes(32, 32)

    content, content_type, filename = normalize_image(original, "image/jpeg", "photo.jpg")

    assert content is original
    assert content_type == "image/jpeg"
    assert filename == "photo.jpg"


def test_compress_for_mms_returns_none_when_already_small():
    small = _jpeg_bytes(32, 32)

    result = compress_for_mms(small, "image/jpeg", target_bytes=500_000, max_dimension=1600)

    assert result is None


def test_compress_for_mms_shrinks_oversized_image_under_target():
    large = _jpeg_bytes(1200, 900, quality=95, noisy=True)
    assert len(large) > 500_000

    result = compress_for_mms(large, "image/jpeg", target_bytes=500_000, max_dimension=1600)

    assert result is not None
    content, content_type = result
    assert content_type == "image/jpeg"
    assert len(content) <= 500_000
    with Image.open(io.BytesIO(content)) as image:
        assert max(image.size) <= 1600


def test_compress_for_mms_preserves_aspect_ratio():
    large = _jpeg_bytes(2000, 1000, quality=95, noisy=True)

    result = compress_for_mms(large, "image/jpeg", target_bytes=500_000, max_dimension=1600)

    assert result is not None
    content, _ = result
    with Image.open(io.BytesIO(content)) as image:
        width, height = image.size
        assert width == 1600
        assert abs((width / height) - 2.0) < 0.02


def test_compress_for_mms_ignores_non_image_content_types():
    result = compress_for_mms(b"not an image" * 100_000, "application/pdf", target_bytes=500_000, max_dimension=1600)

    assert result is None
