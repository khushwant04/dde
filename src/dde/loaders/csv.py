"""Guarded UTF-8 CSV loader with deterministic canonical text."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from dde.config import Settings
from dde.errors import CorruptInputError, InputError, InputLimitError
from dde.loaders.base import LoadedDocument, digest, safe_filename
from dde.models import LoaderNotice, LoaderNoticeCode, Severity

_DIALECT_SAMPLE_CHARS = 65_536
_ALLOWED_DELIMITERS = ",;\t|"
_CANONICAL_PREFIX = "CSV rows as JSON arrays (logical row order preserved):\n"


def _decode_csv(data: bytes) -> str:
    if b"\x00" in data:
        raise CorruptInputError("CSV input contains NUL bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorruptInputError("CSV input is not valid UTF-8") from exc
    if not text.strip():
        raise InputError("CSV input contains no visible content")
    return text


def _dialect(text: str) -> tuple[type[csv.Dialect], tuple[LoaderNotice, ...]]:
    try:
        detected = csv.Sniffer().sniff(text[:_DIALECT_SAMPLE_CHARS], delimiters=_ALLOWED_DELIMITERS)
        return detected, ()
    except csv.Error:
        notice = LoaderNotice(
            code=LoaderNoticeCode.CSV_DIALECT_FALLBACK,
            severity=Severity.WARNING,
            message="CSV dialect could not be detected; comma delimiter was used",
            field=None,
        )
        return csv.excel, (notice,)


def load_csv(path: Path, data: bytes, settings: Settings) -> LoadedDocument:
    text = _decode_csv(data)
    dialect, notices = _dialect(text)
    canonical_parts = [_CANONICAL_PREFIX]
    canonical_chars = len(_CANONICAL_PREFIX)
    row_count = 0
    try:
        reader = csv.reader(StringIO(text, newline=""), dialect=dialect, strict=True)
        for row_count, row in enumerate(reader, start=1):
            if row_count > settings.max_tabular_rows:
                raise InputLimitError(f"CSV has more than {settings.max_tabular_rows} logical rows")
            if len(row) > settings.max_tabular_columns:
                raise InputLimitError(
                    f"CSV row {row_count} has {len(row)} columns; "
                    f"limit is {settings.max_tabular_columns}"
                )
            for column, cell in enumerate(row, start=1):
                if len(cell) > settings.max_cell_chars:
                    raise InputLimitError(
                        f"CSV cell {row_count},{column} has {len(cell)} characters; "
                        f"limit is {settings.max_cell_chars}"
                    )
            line = f"row {row_count}: {json.dumps(row, ensure_ascii=False)}\n"
            canonical_chars += len(line)
            if canonical_chars > settings.max_tabular_chars:
                raise InputLimitError(
                    f"Canonical CSV text exceeds {settings.max_tabular_chars} characters"
                )
            canonical_parts.append(line)
    except csv.Error as exc:
        raise CorruptInputError(f"CSV parsing failed: {exc}") from exc
    if row_count == 0:
        raise InputError("CSV input contains no logical rows")

    return LoadedDocument(
        file_name=safe_filename(path),
        media_type="text/csv; charset=utf-8",
        sha256=digest(data),
        byte_count=len(data),
        page_count=None,
        sheet_count=1,
        text="".join(canonical_parts),
        images=(),
        notices=notices,
    )
