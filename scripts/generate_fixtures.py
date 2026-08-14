"""Generate the small synthetic fixture set; no network or credentials required."""

from __future__ import annotations

import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pymupdf
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont

from dde.config import Settings
from dde.evaluator import evaluate_samples
from dde.models import ExtractedDocument
from dde.pipeline import ExtractionPipeline
from dde.providers.fake import FakeProvider

ROOT = Path(__file__).resolve().parents[1] / "samples"
DOCS = ROOT / "documents"
GROUND = ROOT / "ground_truth"
FAKE = ROOT / "fake_responses"
OUTPUTS = ROOT / "outputs"

FIXTURES: dict[str, dict[str, object]] = {
    "invoice_a": {
        "format": "pdf",
        "layout": "traditional-table",
        "text": """ACME Technologies Pvt Ltd\nAddress: Bengaluru, India\nGSTIN: GSTIN29ABCDE1234F1Z5\nINVOICE INV-20491\nBill To: Rooman Labs\nDate: 12 Aug 2026  Due: 26 Aug 2026\nGPU Server | 2 | INR 150000.00 | INR 300000.00\nSupport Plan | 1 | INR 20000.00 | INR 20000.00\nSubtotal INR 320000.00\nTax INR 57600.00\nTOTAL INR 377600.00""",
        "document": {
            "document_type": "invoice",
            "document_id": "INV-20491",
            "vendor": {
                "name": "ACME Technologies Pvt Ltd",
                "tax_id": "GSTIN29ABCDE1234F1Z5",
                "address": "Bengaluru, India",
            },
            "customer_name": "Rooman Labs",
            "issue_date": "2026-08-12",
            "due_date": "2026-08-26",
            "currency": "INR",
            "line_items": [
                {
                    "description": "GPU Server",
                    "quantity": "2",
                    "unit_price": "150000.00",
                    "amount": "300000.00",
                },
                {
                    "description": "Support Plan",
                    "quantity": "1",
                    "unit_price": "20000.00",
                    "amount": "20000.00",
                },
            ],
            "subtotal": "320000.00",
            "discount": None,
            "tax": "57600.00",
            "shipping": None,
            "total": "377600.00",
        },
        "expected_issue_codes": [],
    },
    "invoice_b": {
        "format": "image",
        "layout": "modern-two-column",
        "text": """NORTHSTAR DESIGN\nInvoice #NS-882\nAUG 11, 2026\nCurrency: USD\nBrand identity package 1 x $900.00 = $900.00\nPrint proofs 3 x $25.00 = $75.00\nSUBTOTAL $975.00 | DISCOUNT $75.00 | TOTAL $900.00""",
        "document": {
            "document_type": "invoice",
            "document_id": "NS-882",
            "vendor": {"name": "Northstar Design", "tax_id": None, "address": None},
            "customer_name": None,
            "issue_date": "2026-08-11",
            "due_date": None,
            "currency": "USD",
            "line_items": [
                {
                    "description": "Brand identity package",
                    "quantity": "1",
                    "unit_price": "900.00",
                    "amount": "900.00",
                },
                {
                    "description": "Print proofs",
                    "quantity": "3",
                    "unit_price": "25.00",
                    "amount": "75.00",
                },
            ],
            "subtotal": "975.00",
            "discount": "75.00",
            "tax": None,
            "shipping": None,
            "total": "900.00",
        },
        "expected_issue_codes": [],
    },
    "invoice_c": {
        "format": "text",
        "layout": "compact-text",
        "text": """INVOICE\nVendor: Delta Office Supply\nAddress: Austin, TX\nDate 2026/08/10\nPaper cartons, qty 4 @ USD 12.50 = USD 50.00\nSubtotal: 50.00\nTotal: USD 50.00\nIdentifier not provided.""",
        "document": {
            "document_type": "invoice",
            "document_id": None,
            "vendor": {"name": "Delta Office Supply", "tax_id": None, "address": "Austin, TX"},
            "customer_name": None,
            "issue_date": "2026-08-10",
            "due_date": None,
            "currency": "USD",
            "line_items": [
                {
                    "description": "Paper cartons",
                    "quantity": "4",
                    "unit_price": "12.50",
                    "amount": "50.00",
                }
            ],
            "subtotal": "50.00",
            "discount": None,
            "tax": None,
            "shipping": None,
            "total": "50.00",
        },
        "expected_issue_codes": ["MISSING_IDENTIFIER"],
    },
    "invoice_d": {
        "format": "pdf",
        "layout": "scanned-table",
        "text": """EUROPA PARTS\nAddress: Berlin, Germany\nVAT ID: DE123456789\nBill To: Example Robotics\nINVOICE EP-140\nIssued 09.08.2026 | Due 08.08.2026\nPrecision bearing 5 x EUR 18.00   EUR 90.00\nSubtotal EUR 90.00\nShipping EUR 10.00\nTOTAL EUR 100.00""",
        "document": {
            "document_type": "invoice",
            "document_id": "EP-140",
            "vendor": {
                "name": "Europa Parts",
                "tax_id": "DE123456789",
                "address": "Berlin, Germany",
            },
            "customer_name": "Example Robotics",
            "issue_date": "2026-08-09",
            "due_date": "2026-08-08",
            "currency": "EUR",
            "line_items": [
                {
                    "description": "Precision bearing",
                    "quantity": "5",
                    "unit_price": "18.00",
                    "amount": "90.00",
                }
            ],
            "subtotal": "90.00",
            "discount": None,
            "tax": None,
            "shipping": "10.00",
            "total": "100.00",
        },
        "expected_issue_codes": ["DUE_BEFORE_ISSUE", "NO_NATIVE_TEXT"],
    },
    "receipt_a": {
        "format": "image",
        "layout": "narrow-thermal",
        "text": """CORNER CAFE\nSeattle, WA\nRECEIPT R-3019\n13/08/2026\nCurrency: USD\nCoffee 2 @ $3.50  $7.00\nBagel 1 @ $4.00  $4.00\nSubtotal $11.00\nTax $0.88\nTOTAL $11.88""",
        "document": {
            "document_type": "receipt",
            "document_id": "R-3019",
            "vendor": {"name": "Corner Cafe", "tax_id": None, "address": "Seattle, WA"},
            "customer_name": None,
            "issue_date": "2026-08-13",
            "due_date": None,
            "currency": "USD",
            "line_items": [
                {"description": "Coffee", "quantity": "2", "unit_price": "3.50", "amount": "7.00"},
                {"description": "Bagel", "quantity": "1", "unit_price": "4.00", "amount": "4.00"},
            ],
            "subtotal": "11.00",
            "discount": None,
            "tax": "0.88",
            "shipping": None,
            "total": "11.88",
        },
        "expected_issue_codes": [],
    },
    "receipt_b": {
        "format": "pdf",
        "layout": "wide-retail",
        "text": """GREEN MART                         RECEIPT GM-7781\nPune, India                         GSTIN27EXAMPLE1Z2\n2026-08-12\nOrganic rice  2 x INR 210.00  INR 420.00\nCooking oil   1 x INR 180.00  INR 180.00\nSUBTOTAL 600.00   DISCOUNT 20.00   TAX 29.00   TOTAL INR 609.00""",
        "document": {
            "document_type": "receipt",
            "document_id": "GM-7781",
            "vendor": {
                "name": "Green Mart",
                "tax_id": "GSTIN27EXAMPLE1Z2",
                "address": "Pune, India",
            },
            "customer_name": None,
            "issue_date": "2026-08-12",
            "due_date": None,
            "currency": "INR",
            "line_items": [
                {
                    "description": "Organic rice",
                    "quantity": "2",
                    "unit_price": "210.00",
                    "amount": "420.00",
                },
                {
                    "description": "Cooking oil",
                    "quantity": "1",
                    "unit_price": "180.00",
                    "amount": "180.00",
                },
            ],
            "subtotal": "600.00",
            "discount": "20.00",
            "tax": "29.00",
            "shipping": None,
            "total": "609.00",
        },
        "expected_issue_codes": [],
    },
    "invoice_mismatch": {
        "format": "pdf",
        "layout": "table-mismatch",
        "text": """ORBITAL COMPONENTS\nBill To: Demo Manufacturing\nINVOICE OC-404\nDate: August 13, 2026\nSensor array 2 x USD 125.00 = USD 250.00\nSubtotal USD 250.00\nTax USD 25.00\nPRINTED TOTAL USD 270.00""",
        "document": {
            "document_type": "invoice",
            "document_id": "OC-404",
            "vendor": {"name": "Orbital Components", "tax_id": None, "address": None},
            "customer_name": "Demo Manufacturing",
            "issue_date": "2026-08-13",
            "due_date": None,
            "currency": "USD",
            "line_items": [
                {
                    "description": "Sensor array",
                    "quantity": "2",
                    "unit_price": "125.00",
                    "amount": "250.00",
                }
            ],
            "subtotal": "250.00",
            "discount": None,
            "tax": "25.00",
            "shipping": None,
            "total": "270.00",
        },
        "expected_issue_codes": ["TOTAL_MISMATCH"],
    },
    "purchase_order_a": {
        "format": "text",
        "layout": "purchase-order-table",
        "text": """PURCHASE ORDER PO-6021\nSupplier: Atlas Industrial Supply\nAddress: Denver, CO\nShip To: Rooman Manufacturing\nIssue Date: 14 Aug 2026\nDelivery Date: 28 Aug 2026\nCurrency: USD\nControl Module | 3 | USD 40.00 | USD 120.00\nSubtotal USD 120.00\nShipping USD 15.00\nTOTAL USD 135.00""",
        "document": {
            "document_type": "purchase_order",
            "document_id": "PO-6021",
            "reference_document_id": None,
            "vendor": {
                "name": "Atlas Industrial Supply",
                "tax_id": None,
                "address": "Denver, CO",
            },
            "customer_name": "Rooman Manufacturing",
            "issue_date": "2026-08-14",
            "due_date": None,
            "delivery_date": "2026-08-28",
            "currency": "USD",
            "line_items": [
                {
                    "description": "Control Module",
                    "quantity": "3",
                    "unit_price": "40.00",
                    "amount": "120.00",
                }
            ],
            "subtotal": "120.00",
            "discount": None,
            "tax": None,
            "shipping": "15.00",
            "total": "135.00",
        },
        "expected_issue_codes": [],
    },
    "credit_note_a": {
        "format": "text",
        "layout": "credit-note-compact",
        "text": """CREDIT NOTE CN-104\nReferences invoice INV-900\nVendor: Beacon Services\nCredit To: Rooman Labs\nDate: 15 Aug 2026\nCurrency: USD\nService adjustment | 1 | USD 100.00 | USD 100.00\nSubtotal USD 100.00\nTax USD 8.00\nCREDIT TOTAL USD 108.00""",
        "document": {
            "document_type": "credit_note",
            "document_id": "CN-104",
            "reference_document_id": "INV-900",
            "vendor": {"name": "Beacon Services", "tax_id": None, "address": None},
            "customer_name": "Rooman Labs",
            "issue_date": "2026-08-15",
            "due_date": None,
            "delivery_date": None,
            "currency": "USD",
            "line_items": [
                {
                    "description": "Service adjustment",
                    "quantity": "1",
                    "unit_price": "100.00",
                    "amount": "100.00",
                }
            ],
            "subtotal": "100.00",
            "discount": None,
            "tax": "8.00",
            "shipping": None,
            "total": "108.00",
        },
        "expected_issue_codes": [],
    },
    "credit_note_b": {
        "format": "csv",
        "layout": "credit-note-records",
        "text": """section,field,value,description,quantity,unit_price,amount
meta,document_type,credit note,,,,
meta,document_id,CN-205,,,,
meta,reference_document_id,INV-901,,,,
meta,vendor,Beacon Services,,,,
meta,customer,Rooman Labs,,,,
meta,issue_date,16 Aug 2026,,,,
meta,currency,USD,,,,
line,,,Service adjustment,1,-100.00,-100.00
total,subtotal,-100.00,,,,
total,tax,-8.00,,,,
total,total,-108.00,,,,""",
        "document": {
            "document_type": "credit_note",
            "document_id": "CN-205",
            "reference_document_id": "INV-901",
            "vendor": {"name": "Beacon Services", "tax_id": None, "address": None},
            "customer_name": "Rooman Labs",
            "issue_date": "2026-08-16",
            "due_date": None,
            "delivery_date": None,
            "currency": "USD",
            "line_items": [
                {
                    "description": "Service adjustment",
                    "quantity": "1",
                    "unit_price": "-100.00",
                    "amount": "-100.00",
                }
            ],
            "subtotal": "-100.00",
            "discount": None,
            "tax": "-8.00",
            "shipping": None,
            "total": "-108.00",
        },
        "expected_issue_codes": [],
    },
    "purchase_order_b": {
        "format": "xlsx",
        "layout": "multi-sheet-purchase-order",
        "text": """PURCHASE ORDER PO-7102
Supplier: Meridian Components
Address: Toronto, Canada
Ship To: Rooman Manufacturing
Issue Date: 17 Aug 2026
Delivery Date: 31 Aug 2026
Currency: CAD
Optical Sensor | 4 | 75.00 | 300.00
Subtotal 300.00
Tax 39.00
Total 339.00
Payment Terms: Net 30""",
        "sheets": [
            {
                "title": "Purchase Order",
                "rows": [
                    ["PURCHASE ORDER", "PO-7102"],
                    ["Supplier", "Meridian Components"],
                    ["Address", "Toronto, Canada"],
                    ["Ship To", "Rooman Manufacturing"],
                    ["Issue Date", "17 Aug 2026"],
                    ["Delivery Date", "31 Aug 2026"],
                    ["Currency", "CAD"],
                    [],
                    ["Item", "Quantity", "Unit Price", "Amount"],
                    ["Optical Sensor", "4", "75.00", "300.00"],
                    ["Subtotal", "300.00"],
                    ["Tax", "39.00"],
                    ["Total", "339.00"],
                ],
            },
            {"title": "Terms", "rows": [["Payment Terms", "Net 30"]]},
        ],
        "document": {
            "document_type": "purchase_order",
            "document_id": "PO-7102",
            "reference_document_id": None,
            "vendor": {
                "name": "Meridian Components",
                "tax_id": None,
                "address": "Toronto, Canada",
            },
            "customer_name": "Rooman Manufacturing",
            "issue_date": "2026-08-17",
            "due_date": None,
            "delivery_date": "2026-08-31",
            "currency": "CAD",
            "line_items": [
                {
                    "description": "Optical Sensor",
                    "quantity": "4",
                    "unit_price": "75.00",
                    "amount": "300.00",
                }
            ],
            "subtotal": "300.00",
            "discount": None,
            "tax": "39.00",
            "shipping": None,
            "total": "339.00",
        },
        "expected_issue_codes": [],
    },
}

for fixture in FIXTURES.values():
    document = fixture["document"]
    if not isinstance(document, dict):
        raise TypeError("fixture document must be an object")
    document.setdefault("reference_document_id", None)
    document.setdefault("delivery_date", None)


def draw_image(text: str, width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text(
        (24, 20), text, fill="black", font=ImageFont.load_default(size=18), spacing=10
    )
    return image


def draw_two_column_invoice() -> Image.Image:
    """Render invoice_b with independently populated left and right columns."""
    image = Image.new("RGB", (1000, 700), "white")
    draw = ImageDraw.Draw(image)
    body = ImageFont.load_default(size=20)
    title = ImageFont.load_default(size=32)
    draw.text((40, 35), "NORTHSTAR DESIGN", fill="black", font=title)
    draw.line((500, 30, 500, 660), fill="gray", width=2)
    draw.multiline_text(
        (40, 125),
        "ITEMS\n\nBrand identity package\n1 x $900.00 = $900.00\n\n"
        "Print proofs\n3 x $25.00 = $75.00",
        fill="black",
        font=body,
        spacing=12,
    )
    draw.multiline_text(
        (550, 35),
        "INVOICE\n#NS-882\nAUG 11, 2026\nCurrency: USD\n\nSUMMARY\n\nSUBTOTAL  $975.00\n"
        "DISCOUNT   $75.00\nTOTAL     $900.00",
        fill="black",
        font=body,
        spacing=14,
    )
    return image


def save_pdf(path: Path, text: str, image_only: bool = False) -> None:
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    if image_only:
        image = draw_image(text, 900, 1100)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        page.insert_image(page.rect, stream=buffer.getvalue())
    else:
        page.insert_textbox(pymupdf.Rect(45, 50, 550, 790), text, fontsize=12, lineheight=1.5)
    document.save(path, no_new_id=True)
    document.close()


def save_xlsx(path: Path, sheet_definitions: object) -> None:
    if not isinstance(sheet_definitions, list) or not sheet_definitions:
        raise TypeError("XLSX fixture sheets must be a non-empty list")
    workbook = Workbook()
    workbook.remove(workbook.active)
    fixed_time = datetime(2020, 1, 1)
    workbook.properties.created = fixed_time
    workbook.properties.modified = fixed_time
    for definition in sheet_definitions:
        if not isinstance(definition, dict):
            raise TypeError("XLSX sheet definition must be an object")
        title = definition.get("title")
        rows = definition.get("rows")
        if not isinstance(title, str) or not isinstance(rows, list):
            raise TypeError("XLSX sheet title/rows are invalid")
        sheet = workbook.create_sheet(title)
        for row in rows:
            if not isinstance(row, list):
                raise TypeError("XLSX fixture row must be a list")
            sheet.append(row)

    raw = BytesIO()
    workbook.save(raw)
    workbook.close()
    with (
        ZipFile(BytesIO(raw.getvalue())) as source,
        ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as target,
    ):
        for name in sorted(source.namelist()):
            content = source.read(name)
            if name == "docProps/core.xml":
                content = re.sub(
                    rb"(<dcterms:modified\b[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>2020-01-01T00:00:00Z\g<2>",
                    content,
                )
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            target.writestr(info, content)


def main() -> None:
    for directory in (DOCS, GROUND, FAKE, OUTPUTS):
        directory.mkdir(parents=True, exist_ok=True)
    for fixture_id, fixture in FIXTURES.items():
        text = str(fixture["text"])
        if fixture_id in {"invoice_b", "receipt_a"}:
            image = (
                draw_two_column_invoice()
                if fixture_id == "invoice_b"
                else draw_image(text, 440, 720)
            )
            extension = "png" if fixture_id == "invoice_b" else "jpg"
            image.save(DOCS / f"{fixture_id}.{extension}", quality=90)
        elif fixture["format"] in {"text", "csv"}:
            extension = "txt" if fixture["format"] == "text" else "csv"
            (DOCS / f"{fixture_id}.{extension}").write_text(text + "\n", encoding="utf-8")
        elif fixture["format"] == "xlsx":
            save_xlsx(DOCS / f"{fixture_id}.xlsx", fixture.get("sheets"))
        else:
            save_pdf(DOCS / f"{fixture_id}.pdf", text, image_only=fixture_id == "invoice_d")
        serialized = json.dumps(fixture["document"], indent=2) + "\n"
        (GROUND / f"{fixture_id}.json").write_text(serialized, encoding="utf-8")
        (FAKE / f"{fixture_id}.json").write_text(serialized, encoding="utf-8")

    (DOCS / "bad_input.pdf").write_bytes(b"%PDF-not-a-valid-document\n")
    manifest = {
        "fixture_set_version": "5.0",
        "fixtures": {
            key: {
                "format": value["format"],
                "layout": value["layout"],
                "document_type": value["document"]["document_type"],
                "expected_issue_codes": value["expected_issue_codes"],
            }
            for key, value in FIXTURES.items()
        }
        | {"bad_input": {"format": "bad", "layout": "corrupt", "expected_exit_code": 3}},
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    settings = Settings()
    provider = FakeProvider(fixture_dir=FAKE)
    pipeline = ExtractionPipeline(settings, provider)
    for path in sorted(DOCS.iterdir()):
        if path.stem in FIXTURES:
            result = pipeline.run(path)
            (OUTPUTS / f"{path.stem}.json").write_text(
                result.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
    # Validate generation through the exact provider contract.
    for path in GROUND.glob("*.json"):
        ExtractedDocument.model_validate_json(path.read_text())
    summary = evaluate_samples(ROOT)
    (ROOT / "evaluation-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
