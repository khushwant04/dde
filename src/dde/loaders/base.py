"""Canonical loader boundary and content-aware dispatch."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from dde.config import Settings
from dde.errors import InputError, InputLimitError, UnsupportedInputError


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    file_name: str
    media_type: str
    sha256: str
    byte_count: int
    page_count: int
    text: str | None
    images: tuple[bytes, ...]
    warnings: tuple[str, ...] = ()

    def image_data_urls(self) -> tuple[str, ...]:
        encoded: list[str] = []
        for image in self.images:
            value = base64.b64encode(image).decode("ascii")
            encoded.append(f"data:image/png;base64,{value}")
        return tuple(encoded)


def safe_filename(path: Path) -> str:
    name = path.name.replace("\x00", "").strip()
    return name or "document"


def read_bounded(path: Path, settings: Settings) -> bytes:
    if not path.is_file():
        raise InputError(f"Input file does not exist: {path}")
    size = path.stat().st_size
    if size == 0:
        raise InputError("Input file is empty")
    if size > settings.max_file_bytes:
        raise InputLimitError(f"Input is {size} bytes; limit is {settings.max_file_bytes} bytes")
    data = path.read_bytes()
    if not data:
        raise InputError("Input file is empty")
    return data


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_document(path: Path, settings: Settings) -> LoadedDocument:
    data = read_bounded(path, settings)
    suffix = path.suffix.lower()
    if data.startswith(b"%PDF-"):
        if suffix != ".pdf":
            raise UnsupportedInputError("PDF content requires a .pdf extension")
        from dde.loaders.pdf import load_pdf

        return load_pdf(path, data, settings)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if suffix != ".png":
            raise UnsupportedInputError("PNG content requires a .png extension")
        from dde.loaders.image import load_image

        return load_image(path, data, settings)
    if data.startswith(b"\xff\xd8\xff"):
        if suffix not in {".jpg", ".jpeg"}:
            raise UnsupportedInputError("JPEG content requires a .jpg or .jpeg extension")
        from dde.loaders.image import load_image

        return load_image(path, data, settings)
    if suffix == ".txt":
        from dde.loaders.text import load_text

        return load_text(path, data)
    raise UnsupportedInputError("Unsupported content; expected PDF, PNG, JPEG, or UTF-8 TXT")
