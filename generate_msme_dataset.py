"""Generate a synthetic Indian MSME monthly purchase register for AuRIS.

Writes two CSVs under data/ :

- `transactions_msme.csv`: ~2000 line-items with vendor, GSTIN, invoice
  number, invoice date, PO date, amount, HSN code. This is the test
  bed for the new India-native checks (GSTIN format, enhanced
  duplicate detection, PO-date-vs-invoice-date, blocked vendor).
- `vendor_master.csv`: ~35 vendors with their canonical GSTIN, state
  code, HSN default, and a `blocked` flag. Side-table for mismatch
  and blocked-vendor checks later.

The data is deliberately dirty. Known failure patterns are seeded so
the new checks have something concrete to catch:

- ~5% rows with vendor_gstin missing
- ~3% rows with malformed vendor_gstin (wrong length or bad chars)
- ~2% rows where vendor_gstin does not match the vendor master
- ~2% exact duplicates (vendor + invoice# + amount + date)
- ~1% near-duplicates (trailing space or case flip in invoice#)
- ~1% rows with invoice_date before po_date
- ~1% high-value amount outliers
- 1 blocked vendor with ~20 transactions

The old `generate_dataset.py` is untouched. This file lives beside it
so the live demo (`data/transactions.csv`) keeps working while the
pivot work builds its own test bed.

Run from the repo root:

    python3 generate_msme_dataset.py
"""
import csv
import random
import string
from datetime import datetime, timedelta
from pathlib import Path

# GSTIN format: 2 state digits + 10-char PAN (5 letters, 4 digits, 1 letter)
# + 1 entity code (1-9 or A-Z) + "Z" + 1 check digit (0-9 or A-Z).
_CODE_POINTS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_STATE_CODES = [
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
    "11", "19", "20", "21", "22", "23", "24", "27", "29", "30",
    "32", "33", "34", "36", "37",
]

VENDORS = [
    "Shree Krishna Textiles Pvt Ltd",
    "Rajasthan Steel Traders",
    "Mumbai IT Solutions LLP",
    "Patel Hardware Supplies",
    "Chennai Logistics Pvt Ltd",
    "Bharat Office Furniture",
    "Deccan Chemicals India",
    "Himalaya Packaging Co",
    "Vikram Printing Press",
    "Ganesh Electrical Works",
    "Surya Transport Services",
    "Lotus Garments Exports",
    "Agarwal Stationers",
    "Shivam Cleaning Services",
    "Kerala Spices Trading",
    "Punjab Agro Products",
    "Bangalore Software Partners",
    "Delhi Marketing Agency",
    "Nashik Fabrication Pvt",
    "Udyog Industrial Tools",
    "Siddhi Vinayak Enterprises",
    "Jay Shree Packaging",
    "Pune Auto Components",
    "Hyderabad Media Works",
    "Western Freight Carriers",
    "Eastern Office Supplies",
    "North Star Consulting",
    "Southern Catering Services",
    "Metro Security Solutions",
    "Rapid Courier Partners",
    "Prime Furniture Mart",
    "Shakti Industrial Fasteners",
    "Oceanic Shipping Lines",
    "Sunrise Printing Hub",
    "Trident Office Interiors",
]

HSN_CODES = [
    "4820",  # Office stationery
    "5208",  # Woven fabrics of cotton
    "7308",  # Structures of iron or steel
    "8471",  # Computers
    "8481",  # Taps/valves
    "8544",  # Insulated wire
    "9018",  # Medical instruments
    "9403",  # Furniture
    "4901",  # Printed books
    "3923",  # Plastic articles
    "7210",  # Flat-rolled iron
    "8415",  # Air conditioning
    "9983",  # Professional services (SAC)
    "9985",  # Support services (SAC)
    "9987",  # Maintenance services (SAC)
]

START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 9, 30)
NUM_ROWS = 2000
BLOCKED_VENDOR_INDEX = 7  # "Himalaya Packaging Co" is seeded as blocked.

DATA_DIR = Path(__file__).resolve().parent / "data"
VENDOR_MASTER_FILE = DATA_DIR / "vendor_master.csv"
TRANSACTIONS_FILE = DATA_DIR / "transactions_msme.csv"


def _compute_gstin_checksum(base14: str) -> str:
    """Compute the 15th-character GSTIN check digit per GSTN's base-36 formula.

    Duplicated intentionally in this generator so it stays self-contained;
    the production implementation lives in `src/auris/gstin.py` once the
    GSTIN-check PR ships.
    """
    factor = 2
    total = 0
    for ch in reversed(base14):
        value = _CODE_POINTS.index(ch)
        addend = factor * value
        factor = 1 if factor == 2 else 2
        addend = (addend // 36) + (addend % 36)
        total += addend
    remainder = total % 36
    check_index = (36 - remainder) % 36
    return _CODE_POINTS[check_index]


def _random_gstin(state_code: str | None = None) -> str:
    """Produce a syntactically valid GSTIN with a correct check digit."""
    if state_code is None:
        state_code = random.choice(_STATE_CODES)
    pan_letters_1 = "".join(random.choices(string.ascii_uppercase, k=5))
    pan_digits = "".join(random.choices(string.digits, k=4))
    pan_letter_2 = random.choice(string.ascii_uppercase)
    entity_code = random.choice(string.digits[1:] + string.ascii_uppercase)
    base14 = f"{state_code}{pan_letters_1}{pan_digits}{pan_letter_2}{entity_code}Z"
    return base14 + _compute_gstin_checksum(base14)


def _corrupt_gstin(valid_gstin: str) -> str:
    """Return a GSTIN that will fail the regex-plus-checksum check.

    Picks one of four corruption modes so the test set covers each
    failure path: wrong length, bad character in the PAN block, missing
    the fixed 'Z', or flipped check digit.
    """
    mode = random.choice(["too_short", "bad_pan_char", "missing_z", "bad_checksum"])
    if mode == "too_short":
        return valid_gstin[:-2]
    if mode == "bad_pan_char":
        return valid_gstin[:2] + "1" + valid_gstin[3:]  # digit where a PAN letter must be
    if mode == "missing_z":
        return valid_gstin[:13] + "A" + valid_gstin[14]  # replace mandatory Z
    # bad_checksum: keep format, change the final character
    last = valid_gstin[-1]
    swap = next(c for c in _CODE_POINTS if c != last)
    return valid_gstin[:-1] + swap


def _random_date(start: datetime, end: datetime) -> datetime:
    delta_days = (end - start).days
    return start + timedelta(days=random.randint(0, delta_days))


def _generate_vendor_master() -> list[dict]:
    """Build the vendor master side-table with one GSTIN per vendor."""
    master = []
    for i, name in enumerate(VENDORS):
        state_code = _STATE_CODES[i % len(_STATE_CODES)]
        master.append({
            "vendor_name": name,
            "canonical_gstin": _random_gstin(state_code=state_code),
            "state_code": state_code,
            "default_hsn": random.choice(HSN_CODES),
            "blocked": "true" if i == BLOCKED_VENDOR_INDEX else "false",
        })
    return master


def _invoice_number(seq: int) -> str:
    """Generate an invoice number that varies by vendor-style formatting.

    Half the vendors use short numeric codes, half use alphanumeric
    prefixes with a slash. This matches the heterogeneity CAs actually
    see in Tally bills across different MSMEs.
    """
    style = random.choice(["numeric", "prefixed", "slashed"])
    if style == "numeric":
        return f"{seq:06d}"
    if style == "prefixed":
        prefix = random.choice(["INV", "BILL", "TAX", "PI"])
        return f"{prefix}-{seq:05d}"
    return f"{random.randint(2024, 2026)}/{seq:05d}"


def _generate_transactions(master: list[dict]) -> list[dict]:
    """Generate the main transaction register and seed the dirt patterns."""
    rows: list[dict] = []
    master_by_name = {v["vendor_name"]: v for v in master}

    # Weighted vendor selection: a few vendors dominate the register,
    # which matches real MSME books where 20% of vendors account for
    # 80% of purchases.
    vendor_weights = [random.randint(1, 10) for _ in VENDORS]

    for i in range(1, NUM_ROWS + 1):
        vendor_name = random.choices(VENDORS, weights=vendor_weights, k=1)[0]
        vendor = master_by_name[vendor_name]
        po_date = _random_date(START_DATE, END_DATE - timedelta(days=15))
        invoice_date = po_date + timedelta(days=random.randint(1, 14))
        base_amount = (hash(vendor_name) % 50000) + 5000
        amount = round(random.gauss(base_amount, base_amount * 0.3), 2)
        if amount < 100:
            amount = round(abs(amount) + 500, 2)
        row = {
            "line_id": i,
            "vendor_name": vendor_name,
            "vendor_gstin": vendor["canonical_gstin"],
            "invoice_number": _invoice_number(i),
            "invoice_date": invoice_date.strftime("%Y-%m-%d"),
            "po_date": po_date.strftime("%Y-%m-%d"),
            "amount": amount,
            "hsn_code": vendor["default_hsn"] if random.random() < 0.85 else random.choice(HSN_CODES),
        }
        rows.append(row)

    _seed_missing_gstin(rows)
    _seed_malformed_gstin(rows)
    _seed_mismatched_gstin(rows, master_by_name)
    _seed_exact_duplicates(rows)
    _seed_near_duplicate_invoice_numbers(rows)
    _seed_invoice_before_po(rows)
    _seed_high_value_outliers(rows, master_by_name)
    _seed_blocked_vendor_hits(rows, master, master_by_name)

    random.shuffle(rows)
    for new_seq, row in enumerate(rows, start=1):
        row["line_id"] = new_seq
    return rows


def _seed_missing_gstin(rows: list[dict], rate: float = 0.05) -> None:
    for row in random.sample(rows, int(len(rows) * rate)):
        row["vendor_gstin"] = ""


def _seed_malformed_gstin(rows: list[dict], rate: float = 0.03) -> None:
    candidates = [r for r in rows if r["vendor_gstin"]]
    for row in random.sample(candidates, int(len(rows) * rate)):
        row["vendor_gstin"] = _corrupt_gstin(row["vendor_gstin"])


def _seed_mismatched_gstin(
    rows: list[dict], master_by_name: dict[str, dict], rate: float = 0.02
) -> None:
    """Keep the GSTIN syntactically valid but swap it to another vendor's."""
    candidates = [r for r in rows if r["vendor_gstin"] and len(r["vendor_gstin"]) == 15]
    for row in random.sample(candidates, int(len(rows) * rate)):
        other_name = random.choice([n for n in master_by_name if n != row["vendor_name"]])
        row["vendor_gstin"] = master_by_name[other_name]["canonical_gstin"]


def _seed_exact_duplicates(rows: list[dict], rate: float = 0.02) -> None:
    for src in random.sample(rows, int(len(rows) * rate)):
        rows.append({**src, "line_id": len(rows) + 1})


def _seed_near_duplicate_invoice_numbers(rows: list[dict], rate: float = 0.01) -> None:
    """Produce rows whose invoice# differs only by whitespace or case."""
    for src in random.sample(rows, int(len(rows) * rate)):
        twin = {**src, "line_id": len(rows) + 1}
        mode = random.choice(["trailing_space", "upper", "lower"])
        if mode == "trailing_space":
            twin["invoice_number"] = src["invoice_number"] + " "
        elif mode == "upper":
            twin["invoice_number"] = src["invoice_number"].upper()
        else:
            twin["invoice_number"] = src["invoice_number"].lower()
        rows.append(twin)


def _seed_invoice_before_po(rows: list[dict], rate: float = 0.01) -> None:
    for row in random.sample(rows, int(len(rows) * rate)):
        invoice = datetime.strptime(row["invoice_date"], "%Y-%m-%d")
        row["po_date"] = (invoice + timedelta(days=random.randint(5, 30))).strftime("%Y-%m-%d")


def _seed_high_value_outliers(
    rows: list[dict], master_by_name: dict[str, dict], rate: float = 0.01
) -> None:
    for _ in range(int(len(rows) * rate)):
        vendor_name = random.choice(VENDORS)
        vendor = master_by_name[vendor_name]
        po_date = _random_date(START_DATE, END_DATE - timedelta(days=15))
        rows.append({
            "line_id": len(rows) + 1,
            "vendor_name": vendor_name,
            "vendor_gstin": vendor["canonical_gstin"],
            "invoice_number": _invoice_number(len(rows) + 1),
            "invoice_date": (po_date + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d"),
            "po_date": po_date.strftime("%Y-%m-%d"),
            "amount": round(random.uniform(500000, 2000000), 2),
            "hsn_code": vendor["default_hsn"],
        })


def _seed_blocked_vendor_hits(
    rows: list[dict], master: list[dict], master_by_name: dict[str, dict], count: int = 20
) -> None:
    """Add transactions against the blocked vendor so the later blocked-vendor check lights up."""
    blocked = master[BLOCKED_VENDOR_INDEX]
    for _ in range(count):
        po_date = _random_date(START_DATE, END_DATE - timedelta(days=15))
        rows.append({
            "line_id": len(rows) + 1,
            "vendor_name": blocked["vendor_name"],
            "vendor_gstin": blocked["canonical_gstin"],
            "invoice_number": _invoice_number(len(rows) + 1),
            "invoice_date": (po_date + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d"),
            "po_date": po_date.strftime("%Y-%m-%d"),
            "amount": round(random.uniform(3000, 80000), 2),
            "hsn_code": blocked["default_hsn"],
        })


def main() -> None:
    random.seed(2026)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    master = _generate_vendor_master()
    with VENDOR_MASTER_FILE.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["vendor_name", "canonical_gstin", "state_code", "default_hsn", "blocked"],
        )
        writer.writeheader()
        writer.writerows(master)

    transactions = _generate_transactions(master)
    with TRANSACTIONS_FILE.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "line_id", "vendor_name", "vendor_gstin", "invoice_number",
                "invoice_date", "po_date", "amount", "hsn_code",
            ],
        )
        writer.writeheader()
        writer.writerows(transactions)

    print(f"wrote {len(master)} vendors -> {VENDOR_MASTER_FILE}")
    print(f"wrote {len(transactions)} transactions -> {TRANSACTIONS_FILE}")


if __name__ == "__main__":
    main()
