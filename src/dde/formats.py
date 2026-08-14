"""Authoritative registry for implemented input formats."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final


class FormatKind(StrEnum):
    PDF = "pdf"
    PNG = "png"
    JPEG = "jpeg"
    TEXT = "text"
    CSV = "csv"
    XLSX = "xlsx"


@dataclass(frozen=True, slots=True)
class FormatSpec:
    kind: FormatKind
    label: str
    extensions: tuple[str, ...]
    media_type: str
    signatures: tuple[bytes, ...] = ()

    def matches_signature(self, data: bytes) -> bool:
        return any(data.startswith(signature) for signature in self.signatures)


FORMAT_SPECS: Final[tuple[FormatSpec, ...]] = (
    FormatSpec(
        kind=FormatKind.PDF,
        label="PDF",
        extensions=(".pdf",),
        media_type="application/pdf",
        signatures=(b"%PDF-",),
    ),
    FormatSpec(
        kind=FormatKind.PNG,
        label="PNG",
        extensions=(".png",),
        media_type="image/png",
        signatures=(b"\x89PNG\r\n\x1a\n",),
    ),
    FormatSpec(
        kind=FormatKind.JPEG,
        label="JPEG",
        extensions=(".jpg", ".jpeg"),
        media_type="image/jpeg",
        signatures=(b"\xff\xd8\xff",),
    ),
    FormatSpec(
        kind=FormatKind.TEXT,
        label="UTF-8 TXT",
        extensions=(".txt",),
        media_type="text/plain; charset=utf-8",
    ),
    FormatSpec(
        kind=FormatKind.CSV,
        label="UTF-8 CSV",
        extensions=(".csv",),
        media_type="text/csv; charset=utf-8",
    ),
    FormatSpec(
        kind=FormatKind.XLSX,
        label="XLSX",
        extensions=(".xlsx",),
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        signatures=(b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ),
)

_FORMAT_BY_EXTENSION = {extension: spec for spec in FORMAT_SPECS for extension in spec.extensions}
FORMAT_BY_EXTENSION: Final[Mapping[str, FormatSpec]] = MappingProxyType(_FORMAT_BY_EXTENSION)
SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset(FORMAT_BY_EXTENSION)


def format_for_extension(extension: str) -> FormatSpec | None:
    return FORMAT_BY_EXTENSION.get(extension.casefold())


def sniff_binary_format(data: bytes) -> FormatSpec | None:
    return next(
        (spec for spec in FORMAT_SPECS if spec.signatures and spec.matches_signature(data)),
        None,
    )


def is_supported_path(path: Path) -> bool:
    return path.suffix.casefold() in SUPPORTED_EXTENSIONS


def supported_format_labels() -> str:
    return ", ".join(spec.label for spec in FORMAT_SPECS)
