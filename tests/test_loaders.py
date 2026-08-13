from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from dde.config import Settings
from dde.errors import (
    CorruptInputError,
    EncryptedPDFError,
    InputError,
    InputLimitError,
    UnsupportedInputError,
)
from dde.loaders import load_document


def settings(**updates: object) -> Settings:
    value = Settings(_env_file=None)
    for name, item in updates.items():
        setattr(value, name, item)
    return value


def image_bytes(format_name: str = "PNG", size: tuple[int, int] = (20, 10)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format=format_name)
    return output.getvalue()


def pdf_bytes(text: str = "Invoice") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_text_loader_and_hash(tmp_path: Path) -> None:
    path = tmp_path / "doc.txt"
    path.write_text("hello £", encoding="utf-8")
    loaded = load_document(path, settings())
    assert loaded.media_type == "text/plain; charset=utf-8"
    assert loaded.text == "hello £"
    assert len(loaded.sha256) == 64
    assert loaded.page_count == 1


@pytest.mark.parametrize("data", [b"\xff", b"hello\x00world", b"  \n"])
def test_invalid_text_rejected(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "bad.txt"
    path.write_bytes(data)
    with pytest.raises((CorruptInputError, InputError)):
        load_document(path, settings())


def test_missing_empty_oversized_and_unsupported(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        load_document(tmp_path / "missing.txt", settings())
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    with pytest.raises(InputError):
        load_document(empty, settings())
    large = tmp_path / "large.txt"
    large.write_bytes(b"1234")
    with pytest.raises(InputLimitError):
        load_document(large, settings(max_file_bytes=3))
    unknown = tmp_path / "data.bin"
    unknown.write_bytes(b"not supported")
    with pytest.raises(UnsupportedInputError):
        load_document(unknown, settings())


def test_content_extension_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "pretend.txt"
    path.write_bytes(image_bytes())
    with pytest.raises(UnsupportedInputError):
        load_document(path, settings())


@pytest.mark.parametrize(
    ("suffix", "format_name", "media"), [("png", "PNG", "image/png"), ("jpg", "JPEG", "image/jpeg")]
)
def test_images_decode_and_normalize(
    tmp_path: Path, suffix: str, format_name: str, media: str
) -> None:
    path = tmp_path / f"image.{suffix}"
    path.write_bytes(image_bytes(format_name))
    loaded = load_document(path, settings())
    assert loaded.media_type == media
    assert loaded.images[0].startswith(b"\x89PNG")
    assert loaded.image_data_urls()[0].startswith("data:image/png;base64,")


def test_corrupt_image_and_pixel_limit(tmp_path: Path) -> None:
    corrupt = tmp_path / "bad.png"
    corrupt.write_bytes(b"\x89PNG\r\n\x1a\nnot-an-image")
    with pytest.raises(CorruptInputError):
        load_document(corrupt, settings())
    large = tmp_path / "large.png"
    large.write_bytes(image_bytes(size=(20, 20)))
    with pytest.raises(InputLimitError):
        load_document(large, settings(max_image_pixels=399))


def test_pdf_extracts_text_and_renders_ordered_png(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    path.write_bytes(pdf_bytes("Visible invoice"))
    loaded = load_document(path, settings(render_dpi=72))
    assert loaded.text is not None and "Visible invoice" in loaded.text
    assert loaded.page_count == 1
    assert loaded.images[0].startswith(b"\x89PNG")


def test_visual_only_pdf_warning(tmp_path: Path) -> None:
    image = image_bytes(size=(50, 50))
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(page.rect, stream=image)
    path = tmp_path / "scan.pdf"
    document.save(path)
    document.close()
    loaded = load_document(path, settings(render_dpi=72))
    assert loaded.text is None
    assert loaded.warnings


def test_pdf_page_and_render_pixel_limits(tmp_path: Path) -> None:
    document = pymupdf.open()
    document.new_page()
    document.new_page()
    path = tmp_path / "two.pdf"
    document.save(path)
    document.close()
    with pytest.raises(InputLimitError):
        load_document(path, settings(max_pages=1))
    with pytest.raises(InputLimitError):
        load_document(path, settings(max_image_pixels=100, render_dpi=72))


def test_pdf_projection_limit_prevents_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = pymupdf.open()
    document.new_page(width=2000, height=2000)
    path = tmp_path / "huge-page.pdf"
    document.save(path)
    document.close()
    render_called = False

    def fail_if_rendered(*args: object, **kwargs: object) -> object:
        nonlocal render_called
        render_called = True
        raise AssertionError("get_pixmap must not run after projected pixel rejection")

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", fail_if_rendered)
    with pytest.raises(InputLimitError):
        load_document(path, settings(max_image_pixels=100, render_dpi=72))
    assert render_called is False


def test_encrypted_and_corrupt_pdf(tmp_path: Path) -> None:
    document = pymupdf.open()
    document.new_page()
    encrypted = tmp_path / "encrypted.pdf"
    document.save(
        encrypted,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret",
        owner_pw="owner",
    )
    document.close()
    with pytest.raises(EncryptedPDFError):
        load_document(encrypted, settings())
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"%PDF-not-valid")
    with pytest.raises(CorruptInputError):
        load_document(corrupt, settings())
