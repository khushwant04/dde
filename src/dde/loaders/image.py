"""Content-verified image loader."""

from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from dde.config import Settings
from dde.errors import CorruptInputError, InputLimitError
from dde.loaders.base import LoadedDocument, digest, safe_filename


def load_image(path: Path, data: bytes, settings: Settings) -> LoadedDocument:
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise CorruptInputError("Image cannot be decoded") from exc
    pixels = width * height
    if width <= 0 or height <= 0 or pixels > settings.max_image_pixels:
        raise InputLimitError(f"Image has {pixels} pixels; limit is {settings.max_image_pixels}")
    expected = "PNG" if data.startswith(b"\x89PNG") else "JPEG"
    if image_format != expected:
        raise CorruptInputError(f"Image signature says {expected}, decoder says {image_format}")
    media_type = "image/png" if expected == "PNG" else "image/jpeg"
    # Preserve source bytes for JPEG; normalize all provider images to PNG data URLs.
    if expected == "PNG":
        provider_image = data
    else:
        with Image.open(BytesIO(data)) as image:
            output = BytesIO()
            image.convert("RGB").save(output, format="PNG", optimize=True)
            provider_image = output.getvalue()
    return LoadedDocument(
        file_name=safe_filename(path),
        media_type=media_type,
        sha256=digest(data),
        byte_count=len(data),
        page_count=1,
        text=None,
        images=(provider_image,),
    )
