from __future__ import annotations

from pathlib import Path

import pytest

from dde.config import Settings
from dde.errors import CorruptInputError, InputLimitError
from dde.loaders import load_document
from dde.models import LoaderNoticeCode, Severity


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def write_csv(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "document.csv"
    path.write_bytes(data)
    return path


def test_csv_preserves_quoted_multiline_and_ragged_logical_rows(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        b'name,description,amount\r\nA,"line one\nline two",10.00\r\nB,short\r\n',
    )
    loaded = load_document(path, settings())
    assert loaded.media_type == "text/csv; charset=utf-8"
    assert loaded.page_count is None
    assert loaded.sheet_count == 1
    assert loaded.notices == ()
    assert loaded.text is not None
    assert 'row 2: ["A", "line one\\nline two", "10.00"]' in loaded.text
    assert 'row 3: ["B", "short"]' in loaded.text


def test_csv_detects_allowed_semicolon_dialect(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "name;amount\nCafé;12.50\n".encode())
    loaded = load_document(path, settings())
    assert loaded.notices == ()
    assert loaded.text is not None and '["Café", "12.50"]' in loaded.text


def test_csv_dialect_fallback_is_typed_and_requires_review_evidence(tmp_path: Path) -> None:
    path = write_csv(tmp_path, b"single column\nsecond row\n")
    loaded = load_document(path, settings())
    assert len(loaded.notices) == 1
    assert loaded.notices[0].code == LoaderNoticeCode.CSV_DIALECT_FALLBACK
    assert loaded.notices[0].severity == Severity.WARNING


@pytest.mark.parametrize("data", [b"name\n\xff\n", b"name\x00amount\n", b'a,"unterminated\n'])
def test_csv_rejects_invalid_utf8_nul_and_malformed_quotes(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(CorruptInputError):
        load_document(write_csv(tmp_path, data), settings())


@pytest.mark.parametrize(
    ("data", "overrides", "message"),
    [
        (b"a\nb\n", {"DDE_MAX_TABULAR_ROWS": 1}, "logical rows"),
        (b"a,b\n", {"DDE_MAX_TABULAR_COLUMNS": 1}, "columns"),
        (b"abcd\n", {"DDE_MAX_CELL_CHARS": 3}, "characters"),
        (b"a,b\n1,2\n", {"DDE_MAX_TABULAR_CHARS": 20}, "Canonical CSV text"),
    ],
)
def test_csv_enforces_all_tabular_limits(
    tmp_path: Path, data: bytes, overrides: dict[str, int], message: str
) -> None:
    with pytest.raises(InputLimitError, match=message):
        load_document(write_csv(tmp_path, data), settings(**overrides))
