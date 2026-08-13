"""Strict UTF-8 text loader."""

from pathlib import Path

from dde.errors import CorruptInputError, InputError
from dde.loaders.base import LoadedDocument, digest, safe_filename


def load_text(path: Path, data: bytes) -> LoadedDocument:
    if b"\x00" in data:
        raise CorruptInputError("Text input contains NUL bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorruptInputError("Text input is not valid UTF-8") from exc
    if not text.strip():
        raise InputError("Text input contains no visible content")
    return LoadedDocument(
        file_name=safe_filename(path),
        media_type="text/plain; charset=utf-8",
        sha256=digest(data),
        byte_count=len(data),
        page_count=1,
        text=text,
        images=(),
    )
