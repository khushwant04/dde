"""Canonical loader boundary and content-aware dispatch."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from dde.config import Settings
from dde.errors import InputError, InputLimitError, UnsupportedInputError
from dde.formats import (
    FormatKind,
    format_for_extension,
    sniff_binary_format,
    supported_format_labels,
)
from dde.models import LoaderNotice


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    file_name: str
    media_type: str
    sha256: str
    byte_count: int
    page_count: int | None
    text: str | None
    images: tuple[bytes, ...]
    sheet_count: int | None = None
    notices: tuple[LoaderNotice, ...] = ()

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
    suffix = path.suffix.casefold()
    declared_format = format_for_extension(suffix)
    detected_format = sniff_binary_format(data)
    if detected_format is not None and suffix not in detected_format.extensions:
        expected = " or ".join(detected_format.extensions)
        raise UnsupportedInputError(
            f"{detected_format.label} content requires a {expected} extension"
        )
    if detected_format is not None:
        if detected_format.kind == FormatKind.PDF:
            from dde.loaders.pdf import load_pdf

            return load_pdf(path, data, settings)
        if detected_format.kind in {FormatKind.PNG, FormatKind.JPEG}:
            from dde.loaders.image import load_image

            return load_image(path, data, settings)
        if detected_format.kind == FormatKind.XLSX:
            from dde.loaders.xlsx import load_xlsx

            return load_xlsx(path, data, settings)
    if declared_format is not None and declared_format.signatures:
        raise UnsupportedInputError(
            f"{declared_format.label} extension does not match the file content"
        )
    if declared_format is not None and declared_format.kind == FormatKind.TEXT:
        from dde.loaders.text import load_text

        return load_text(path, data)
    if declared_format is not None and declared_format.kind == FormatKind.CSV:
        from dde.loaders.csv import load_csv

        return load_csv(path, data, settings)
    raise UnsupportedInputError(f"Unsupported content; expected {supported_format_labels()}")
