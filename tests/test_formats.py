from __future__ import annotations

from pathlib import Path

import pytest

from dde.formats import (
    FORMAT_BY_EXTENSION,
    FORMAT_SPECS,
    FormatKind,
    format_for_extension,
    is_supported_path,
    sniff_binary_format,
    supported_format_labels,
)


def test_format_registry_has_unique_complete_extension_mapping() -> None:
    declared = [extension for spec in FORMAT_SPECS for extension in spec.extensions]
    assert len(declared) == len(set(declared))
    assert set(FORMAT_BY_EXTENSION) == {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".txt",
        ".csv",
        ".xlsx",
    }
    assert {spec.kind for spec in FORMAT_SPECS} == {
        FormatKind.PDF,
        FormatKind.PNG,
        FormatKind.JPEG,
        FormatKind.TEXT,
        FormatKind.CSV,
        FormatKind.XLSX,
    }


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (b"%PDF-1.7", FormatKind.PDF),
        (b"\x89PNG\r\n\x1a\nrest", FormatKind.PNG),
        (b"\xff\xd8\xffrest", FormatKind.JPEG),
    ],
)
def test_binary_signatures_are_centralized(data: bytes, kind: FormatKind) -> None:
    detected = sniff_binary_format(data)
    assert detected is not None
    assert detected.kind == kind


def test_supported_path_and_lookup_are_case_insensitive() -> None:
    assert is_supported_path(Path("INVOICE.PDF"))
    assert format_for_extension(".JpEg") is not None
    assert not is_supported_path(Path("legacy.xls"))
    assert not is_supported_path(Path("sheet.ods"))


def test_supported_labels_come_from_registry() -> None:
    assert supported_format_labels() == "PDF, PNG, JPEG, UTF-8 TXT, UTF-8 CSV, XLSX"
