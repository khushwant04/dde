"""Bounded PDF loader using PyMuPDF."""

import math
from pathlib import Path
from typing import Any

import pymupdf

from dde.config import Settings
from dde.errors import CorruptInputError, EncryptedPDFError, InputError, InputLimitError
from dde.loaders.base import LoadedDocument, digest, safe_filename
from dde.models import LoaderNotice, LoaderNoticeCode, Severity


def load_pdf(path: Path, data: bytes, settings: Settings) -> LoadedDocument:
    try:
        document: Any = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise CorruptInputError("PDF cannot be opened") from exc
    try:
        if document.needs_pass:
            raise EncryptedPDFError("Encrypted PDFs are not supported")
        page_count = document.page_count
        if page_count == 0:
            raise InputError("PDF contains no pages")
        if page_count > settings.max_pages:
            raise InputLimitError(f"PDF has {page_count} pages; limit is {settings.max_pages}")
        scale = settings.render_dpi / 72
        matrix = pymupdf.Matrix(scale, scale)  # type: ignore[no-untyped-call]
        texts: list[str] = []
        images: list[bytes] = []
        for page in document:
            texts.append(page.get_text("text"))
            projected_width = max(1, math.ceil(abs(page.rect.width) * scale))
            projected_height = max(1, math.ceil(abs(page.rect.height) * scale))
            if projected_width * projected_height > settings.max_image_pixels:
                raise InputLimitError(
                    "Projected PDF page exceeds DDE_MAX_IMAGE_PIXELS; lower DDE_RENDER_DPI"
                )
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            if pixmap.width * pixmap.height > settings.max_image_pixels:
                raise InputLimitError(
                    "Rendered PDF page exceeds DDE_MAX_IMAGE_PIXELS; lower DDE_RENDER_DPI"
                )
            images.append(pixmap.tobytes("png"))
    except (EncryptedPDFError, InputError, InputLimitError):
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise CorruptInputError("PDF is corrupt or cannot be rendered") from exc
    finally:
        document.close()
    native_text = "\n\f\n".join(texts).strip() or None
    notices = (
        ()
        if native_text
        else (
            LoaderNotice(
                code=LoaderNoticeCode.NO_NATIVE_TEXT,
                severity=Severity.INFO,
                message="No native PDF text found; extraction uses rendered pages",
                field=None,
            ),
        )
    )
    return LoadedDocument(
        file_name=safe_filename(path),
        media_type="application/pdf",
        sha256=digest(data),
        byte_count=len(data),
        page_count=page_count,
        text=native_text,
        images=tuple(images),
        notices=notices,
    )
