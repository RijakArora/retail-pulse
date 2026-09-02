"""CSV upload parsing + validation.

MVP scope note: this supports ONE generic column format, not
POS-specific parsers for Shopify/Square/Lightspeed/Retail Pro yet (the
v1 spec's four-POS-parser list was future scope - building four parsers
before there is one real customer would be solving a problem nobody has
confirmed yet). Add a POS-specific parser here once a real customer's
actual export format is in hand.

Required columns (case-insensitive): sku, date, quantity_sold
Optional columns: name, revenue, on_hand, reorder_point

Validation deliberately mirrors the real failure modes found in Day 2's
market research (silently truncated/short exports): row-count and
required-column checks run before anything is written to the database,
and a rejected file writes an Upload audit row explaining why, rather
than silently doing nothing.
"""
import csv
import io
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import SKU, SaleRecord

MIN_ROWS = 5
REQUIRED_COLUMNS = {"sku", "date", "quantity_sold"}


class CSVValidationError(Exception):
    pass


def _parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise CSVValidationError(f"Unrecognized date format: '{value}'")


def _parse_float(value: str, default: float = 0.0) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def parse_and_validate(raw_bytes: bytes) -> list[dict]:
    """Returns a list of row dicts, or raises CSVValidationError with a
    human-readable reason. Never partially succeeds - either the whole
    file is usable or the caller gets a clear reason it wasn't."""
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise CSVValidationError(f"File is not valid UTF-8 text: {e}")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CSVValidationError("File has no header row / appears empty.")

    header = {h.strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - header
    if missing:
        raise CSVValidationError(
            f"Missing required column(s): {', '.join(sorted(missing))}. "
            f"Required: {', '.join(sorted(REQUIRED_COLUMNS))}."
        )

    rows = []
    for i, raw_row in enumerate(reader, start=2):  # start=2: header is row 1
        row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        if not row.get("sku"):
            continue  # skip blank trailing lines rather than failing the whole file
        try:
            rows.append({
                "sku": row["sku"],
                "name": row.get("name", ""),
                "date": _parse_date(row["date"]),
                "quantity": _parse_float(row.get("quantity_sold")),
                "revenue": _parse_float(row.get("revenue")),
                "on_hand": _parse_float(row.get("on_hand")),
                "reorder_point": _parse_float(row.get("reorder_point")),
            })
        except CSVValidationError as e:
            raise CSVValidationError(f"Row {i}: {e}")

    if len(rows) < MIN_ROWS:
        raise CSVValidationError(
            f"Only {len(rows)} usable row(s) found (minimum {MIN_ROWS}). "
            "This looks like a short or truncated export - re-download it "
            "and try again rather than uploading a partial file."
        )

    return rows


def apply_upload(db: Session, user_id: int, upload_id: int, rows: list[dict]) -> None:
    """Writes validated rows to the DB: one SaleRecord per row (history),
    and upserts the SKU snapshot (on_hand/reorder_point/last_sale_date)
    using each SKU's most recent row - a CSV is a point-in-time export,
    so the latest row per SKU represents current state."""
    latest_by_sku: dict[str, dict] = {}
    for row in rows:
        db.add(SaleRecord(
            user_id=user_id, upload_id=upload_id, sku_code=row["sku"],
            date=row["date"], quantity=row["quantity"], revenue=row["revenue"],
        ))
        prev = latest_by_sku.get(row["sku"])
        if prev is None or row["date"] >= prev["date"]:
            latest_by_sku[row["sku"]] = row

    existing = {s.sku_code: s for s in db.query(SKU).filter(SKU.user_id == user_id).all()}
    for sku_code, row in latest_by_sku.items():
        sku = existing.get(sku_code)
        if sku is None:
            sku = SKU(user_id=user_id, sku_code=sku_code)
            db.add(sku)
        sku.name = row["name"] or sku.name or sku_code
        sku.on_hand = row["on_hand"]
        sku.reorder_point = row["reorder_point"]
        if row["quantity"] > 0 and (sku.last_sale_date is None or row["date"] > sku.last_sale_date):
            sku.last_sale_date = row["date"]

    db.commit()
