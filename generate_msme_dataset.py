"""Generate a labelled synthetic purchase register for Indian MSMEs.

Purpose
-------
A test bed for AuRIS's India-specific checks (GSTIN validity, duplicate
invoices, PO and GRN sequencing, blocked vendors, GST computation). Every
seeded defect is recorded in a separate ground-truth file, so a check can
be scored on precision and recall instead of "it fired on something".

What it models
--------------
Purchase registers of 25 Indian MSMEs for FY 2025-26 (1 Apr 2025 to
31 Mar 2026), turnover roughly Rs 5 to 100 Cr, across manufacturing,
trading, IT services and logistics, mostly based in Maharashtra. Each
company has its own register and vendor master, shaped like a Tally or
Zoho Books purchase-register export.

Realism choices worth knowing about:

- GSTINs follow the real structure (state code, PAN, entity number, "Z",
  base-36 check digit). The PAN 4th character matches the entity type
  (C company, F firm or LLP, P proprietor) and vendor state codes match
  where the vendor is registered.
- GST is split correctly: CGST plus SGST for intra-state purchases, IGST
  for inter-state. HSN/SAC codes match the vendor's line of business.
- GST rate rationalisation effective 22 Sep 2025 is applied by invoice
  date: air conditioners, cement and motor-vehicle parts move from 28%
  to 18%. Other modelled goods and services keep the same rate.
- Unregistered vendors (petty local suppliers) legitimately have no
  GSTIN and charge no GST. Composition dealers have a valid GSTIN but
  issue a bill of supply with no GST, and only sell within their state.
  A check that flags these is producing false positives.
- Security, housekeeping and manpower vendors are companies, which keeps
  them on forward charge (reverse charge rules are out of scope).
- Rent, security, housekeeping, manpower, telecom and IT support are
  billed monthly at fixed or near-fixed amounts. Same vendor, same
  amount every month is normal, not a duplicate.
- Vendors have their own invoice series per financial year, at most 16
  characters (Rule 46), increasing with date, and shared vendors use
  one series across all clients.
- Goods carry a GRN; services do not. Larger goods purchases carry a
  PO, sometimes a blanket PO reused across invoices. Petty purchases
  have neither.
- Volume is seasonal (March year-end spike, light Sundays) and vendor
  spend is Pareto-shaped. Each client's annual goods spend is scaled to
  a plausible share of its turnover.

Seeded defects (rates are a share of base rows)
-----------------------------------------------
missing_gstin 1.5%, malformed_gstin 1.0% (realistic typos: adjacent
transposition, O/0 style confusion, dropped or doubled character),
gstin_of_other_vendor 0.4%, invoice_before_po 0.5%, goods_without_grn
0.5%, amount_decimal_slip 0.25% (x10 or x100), tax_type_mismatch 0.3%,
tax_rate_mismatch 0.3% (half are stale pre-22-Sep-2025 rates),
tax_arithmetic_error 0.2%, invoice_date_after_voucher_date 0.15%,
exact_duplicate 1.0%, near_duplicate 0.6% (invoice number formatting,
day-month swap, rupee-rounded total), plus blocked_vendor rows that slip
through after a vendor's block date.

Negative controls are labelled too: control_same_day_same_amount rows
are two genuinely different invoices from the same vendor on the same
day for the same amount. A good duplicate check must not flag them.

Defects are disjoint: each base row carries at most one. A duplicate
copy carries the label and points at its original via related_record_id.

Outputs (under data/msme/)
--------------------------
- purchase_register.csv.gz : the register (about 101,900 rows). The
  uncompressed purchase_register.csv is also written but gitignored.
- vendor_master.csv        : per-client vendor master
- clients.csv              : the 25 clients with sector and turnover
- labels.csv               : ground truth, one row per seeded label

Deterministic for a given seed (no reliance on Python's per-process
string hashing; gzip header mtime pinned to 0).

Run from the repo root:

    python3 generate_msme_dataset.py
    python3 generate_msme_dataset.py --rows 5000 --out-dir /tmp/msme
"""
from __future__ import annotations

import argparse
import csv
import gzip
import logging
import math
import re
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Optional

logger = logging.getLogger("auris.msme_dataset")

DEFAULT_SEED = 2026
DEFAULT_TARGET_ROWS = 100_000
FY_START = date(2025, 4, 1)
FY_END = date(2026, 3, 31)
GST_RATE_CHANGE_DATE = date(2025, 9, 22)
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "data" / "msme"
MAX_INVOICE_NUMBER_LENGTH = 16
MIN_ROWS_PER_CLIENT = 250
MIN_TARGET_ROWS = 10_000

# ---------------------------------------------------------------------------
# GSTIN helpers
# ---------------------------------------------------------------------------

_CODE_POINTS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_CODE_POINT_INDEX = {ch: i for i, ch in enumerate(_CODE_POINTS)}
_GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def gstin_check_char(base14: str) -> str:
    """Return the GSTN base-36 check character for the first 14 characters."""
    factor = 2
    total = 0
    for ch in reversed(base14):
        product = factor * _CODE_POINT_INDEX[ch]
        factor = 1 if factor == 2 else 2
        total += (product // 36) + (product % 36)
    return _CODE_POINTS[(36 - total % 36) % 36]


def is_valid_gstin(value: Optional[str]) -> bool:
    """Return True when value matches the GSTIN format and its check digit."""
    if not value or not _GSTIN_REGEX.match(value):
        return False
    return gstin_check_char(value[:14]) == value[14]


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

STATE_NAMES = {
    "03": "Punjab", "06": "Haryana", "07": "Delhi", "08": "Rajasthan",
    "09": "Uttar Pradesh", "19": "West Bengal", "23": "Madhya Pradesh",
    "24": "Gujarat", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "32": "Kerala", "33": "Tamil Nadu", "36": "Telangana",
}

# Where out-of-state vendors are registered, weighted toward the
# industrial states a western-India MSME typically buys from.
OUT_OF_STATE_WEIGHTS = {
    "27": 14, "24": 18, "29": 12, "07": 10, "33": 9, "06": 8, "09": 7,
    "08": 6, "23": 6, "36": 6, "30": 4, "19": 4, "32": 3, "03": 3,
}


@dataclass(frozen=True)
class Category:
    """A line of business a vendor sells in, with its tax treatment."""

    key: str
    hsn_sac: str
    kind: str  # "goods", "service" or "petty"
    rate_before: int  # GST percent for invoices dated before 22 Sep 2025
    rate_after: int  # GST percent on or after 22 Sep 2025
    median_taxable: float
    sigma: float
    nouns: tuple[str, ...]
    billing: str = "adhoc"  # "adhoc" or "monthly"
    registration: str = "Regular"  # "Regular", "Composition" or "Unregistered"
    intra_state_share: float = 0.6


_CATEGORY_LIST = [
    # Goods, regular GST
    Category("steel", "720839", "goods", 18, 18, 180000, 0.8,
             ("Steel", "Ispat", "Metals", "Steel Industries")),
    Category("structurals", "730890", "goods", 18, 18, 95000, 0.7,
             ("Structurals", "Fabricators", "Steel Structures")),
    Category("fasteners", "731815", "goods", 18, 18, 22000, 0.7,
             ("Fasteners", "Bolts and Nuts", "Fastening Systems")),
    Category("bearings", "848210", "goods", 18, 18, 38000, 0.7,
             ("Bearings", "Bearing House", "Precision Bearings")),
    Category("auto_parts", "870899", "goods", 28, 18, 55000, 0.8,
             ("Auto Parts", "Automotives", "Motor Spares")),
    Category("cement", "252329", "goods", 28, 18, 85000, 0.6,
             ("Cement Agencies", "Cement Depot", "Building Supplies")),
    Category("cables", "854449", "goods", 18, 18, 34000, 0.8,
             ("Cables", "Wires and Cables", "Electricals")),
    Category("plastic_packaging", "392321", "goods", 18, 18, 28000, 0.6,
             ("Polypack", "Plastics", "Packaging")),
    Category("cotton_fabric", "520812", "goods", 5, 5, 120000, 0.7,
             ("Textile Mills", "Fabrics", "Weaving Mills")),
    Category("chemicals", "382499", "goods", 18, 18, 65000, 0.8,
             ("Chemicals", "Dyes and Chemicals", "Chem Industries")),
    Category("lubricants", "271019", "goods", 18, 18, 18000, 0.6,
             ("Lubricants", "Oil Traders", "Petro Products")),
    Category("edible_oil", "151219", "goods", 5, 5, 140000, 0.6,
             ("Oil Mills", "Edible Oils", "Agro Oils")),
    Category("spices", "090422", "goods", 5, 5, 60000, 0.7,
             ("Spices", "Masala Udyog", "Spice Traders")),
    Category("air_conditioners", "841510", "goods", 28, 18, 48000, 0.4,
             ("Cooling Solutions", "Aircon Systems", "Refrigeration"),
             intra_state_share=0.7),
    Category("laptops", "847130", "goods", 18, 18, 62000, 0.5,
             ("Computers", "Infotech Systems", "IT Solutions"),
             intra_state_share=0.7),
    Category("office_furniture", "940330", "goods", 18, 18, 38000, 0.6,
             ("Furniture", "Office Interiors", "Furnishers"),
             intra_state_share=0.7),
    # Services, regular GST, ad hoc
    Category("courier", "9968", "service", 18, 18, 6000, 0.7,
             ("Couriers", "Express Logistics", "Cargo Movers"),
             intra_state_share=0.7),
    Category("repairs", "9987", "service", 18, 18, 14000, 0.8,
             ("Engineering Services", "Maintenance Services", "Technical Services"),
             intra_state_share=0.9),
    Category("consulting", "9983", "service", 18, 18, 70000, 0.6,
             ("Consultants", "Advisory Services", "Management Consultants"),
             intra_state_share=0.75),
    Category("printing", "9989", "service", 18, 18, 9000, 0.7,
             ("Printers", "Print Solutions", "Offset Printers"),
             intra_state_share=0.75),
    # Services, regular GST, billed monthly
    Category("rent", "997212", "service", 18, 18, 120000, 0.0,
             ("Properties", "Estates", "Realty"),
             billing="monthly", intra_state_share=1.0),
    Category("security", "9985", "service", 18, 18, 55000, 0.0,
             ("Security Services", "Security Solutions", "Guarding Services"),
             billing="monthly", intra_state_share=1.0),
    Category("housekeeping", "9985", "service", 18, 18, 35000, 0.0,
             ("Facility Services", "Housekeeping Services", "Facility Management"),
             billing="monthly", intra_state_share=1.0),
    Category("manpower", "9985", "service", 18, 18, 180000, 0.0,
             ("Manpower Services", "Staffing Solutions", "HR Services"),
             billing="monthly", intra_state_share=1.0),
    Category("telecom", "9984", "service", 18, 18, 5500, 0.12,
             ("Telecom", "Broadband", "Netlink"),
             billing="monthly", intra_state_share=1.0),
    Category("it_support", "9983", "service", 18, 18, 30000, 0.0,
             ("IT Services", "Systems Support", "Infotech"),
             billing="monthly", intra_state_share=0.8),
    # Composition dealers: valid GSTIN, bill of supply, no GST, intra-state only
    Category("hardware_shop", "8205", "goods", 0, 0, 3500, 0.6,
             ("Hardware Stores", "Hardware Mart", "Tools Centre"),
             registration="Composition", intra_state_share=1.0),
    Category("stationery_shop", "4820", "goods", 0, 0, 2200, 0.6,
             ("Stationers", "Stationery Mart", "Paper House"),
             registration="Composition", intra_state_share=1.0),
    # Unregistered petty suppliers: no GSTIN, no GST, no HSN, no PO or GRN
    Category("local_transport", "", "petty", 0, 0, 3000, 0.6,
             ("Transport", "Tempo Service", "Goods Carrier"),
             registration="Unregistered", intra_state_share=1.0),
    Category("casual_labour", "", "petty", 0, 0, 7000, 0.5,
             ("Labour Contractor", "Loading Services", "Workforce"),
             registration="Unregistered", intra_state_share=1.0),
    Category("canteen", "", "petty", 0, 0, 2000, 0.5,
             ("Tea Stall", "Canteen Services", "Snacks Centre"),
             registration="Unregistered", intra_state_share=1.0),
]
CATEGORIES = {c.key: c for c in _CATEGORY_LIST}
RATE_CHANGED_CATEGORIES = tuple(c.key for c in _CATEGORY_LIST if c.rate_before != c.rate_after)


@dataclass(frozen=True)
class Sector:
    """A client's line of business: what it buys and how much of turnover that is."""

    key: str
    client_noun: str
    purchase_ratio: float  # GST-register purchases as a share of turnover
    adhoc_mix: dict[str, int]  # ad hoc regular-vendor categories, weighted
    monthly: tuple[str, ...]  # recurring monthly services this sector usually has
    invoice_intensity: float = 1.0  # purchase invoices per rupee of turnover, relative


SECTORS = {s.key: s for s in [
    Sector("auto_components_mfr", "Auto Components", 0.64,
           {"steel": 30, "structurals": 4, "fasteners": 12, "bearings": 8, "lubricants": 7,
            "chemicals": 4, "plastic_packaging": 6, "cables": 4, "laptops": 1,
            "office_furniture": 1, "air_conditioners": 1, "courier": 8, "repairs": 9,
            "consulting": 2, "printing": 2},
           ("rent", "security", "housekeeping", "manpower", "telecom")),
    Sector("fabrication", "Engineering Works", 0.62,
           {"steel": 35, "structurals": 10, "fasteners": 14, "cement": 3, "cables": 7,
            "lubricants": 4, "chemicals": 3, "laptops": 1, "courier": 7, "repairs": 10,
            "consulting": 2, "printing": 2},
           ("rent", "security", "manpower", "telecom")),
    Sector("textile_mfr", "Textiles", 0.70,
           {"cotton_fabric": 45, "chemicals": 14, "plastic_packaging": 8, "cables": 2,
            "lubricants": 2, "courier": 10, "repairs": 8, "consulting": 2, "printing": 3},
           ("rent", "security", "housekeeping", "manpower", "telecom")),
    Sector("food_processing", "Foods", 0.72,
           {"edible_oil": 28, "spices": 26, "plastic_packaging": 16, "chemicals": 2,
            "courier": 10, "repairs": 8, "consulting": 2, "printing": 4},
           ("rent", "security", "housekeeping", "manpower", "telecom")),
    Sector("building_materials_trader", "Building Materials", 0.88,
           {"cement": 50, "steel": 28, "structurals": 6, "cables": 4, "courier": 6,
            "repairs": 2, "printing": 2},
           ("rent", "telecom")),
    Sector("auto_parts_distributor", "Auto Distributors", 0.86,
           {"auto_parts": 60, "lubricants": 18, "bearings": 10, "courier": 8,
            "printing": 2, "repairs": 2},
           ("rent", "security", "telecom")),
    Sector("electrical_wholesaler", "Electricals", 0.87,
           {"cables": 60, "air_conditioners": 14, "fasteners": 4, "courier": 10,
            "printing": 2, "repairs": 2},
           ("rent", "security", "telecom")),
    Sector("it_services", "Technologies", 0.30,
           {"laptops": 22, "office_furniture": 6, "air_conditioners": 3, "cables": 4,
            "courier": 25, "repairs": 15, "consulting": 8, "printing": 10},
           ("rent", "security", "housekeeping", "telecom", "it_support"), 0.25),
    Sector("logistics", "Logistics", 0.38,
           {"auto_parts": 35, "lubricants": 25, "bearings": 8, "courier": 5, "repairs": 22,
            "consulting": 3, "printing": 2},
           ("rent", "security", "telecom", "it_support"), 0.7),
]}

# 25 clients: sector counts and home states (mostly Maharashtra).
CLIENT_SECTOR_COUNTS = {
    "auto_components_mfr": 5, "fabrication": 4, "textile_mfr": 3, "food_processing": 3,
    "building_materials_trader": 2, "auto_parts_distributor": 2, "electrical_wholesaler": 2,
    "it_services": 2, "logistics": 2,
}
CLIENT_STATES = ["27"] * 19 + ["24"] * 3 + ["29"] * 2 + ["30"]

NAME_PREFIXES = [
    "Shree Ganesh", "Om Sai", "Jai Bhavani", "Mahalaxmi", "Siddhivinayak", "Balaji",
    "Sai Krupa", "Shreeji", "Annapurna", "Vardhaman", "Mahavir", "Navkar", "Kaveri",
    "Sahyadri", "Narmada", "Godavari", "Pragati", "Unnati", "Samarth", "Vishwakarma",
    "Kamdhenu", "Tirupati", "Ambica", "Gajanan", "Bhagyalaxmi", "Deccan", "Konkan",
    "Satpura", "Vindhya", "Saraswati", "Ashirwad", "Rudra", "Trimurti", "Sanghvi",
    "Patil", "Kulkarni", "Deshmukh", "Joshi", "Shah", "Mehta", "Agarwal", "Iyer",
    "Reddy", "Nair", "Gupta", "Bansal", "Kapoor", "Sethi", "Rathi", "Jain", "Chheda",
    "Parekh", "Thakkar", "Gandhi", "Arihant", "Swastik", "Shubham", "Laxmi Narayan",
    "Krishna", "Omkar", "Matoshree", "Yashoda", "Surya", "Chandra", "Venkatesh",
]
SURNAMES = [
    "Patil", "Kulkarni", "Deshmukh", "Joshi", "Shah", "Mehta", "Agarwal", "Iyer",
    "Reddy", "Nair", "Gupta", "Bansal", "Kapoor", "Sethi", "Rathi", "Jain", "Pawar",
    "Shinde", "Jadhav", "More", "Chavan", "Gaikwad", "Bhosale", "Naik", "Desai",
]
FIRST_NAMES = [
    "Ramesh", "Suresh", "Vijay", "Santosh", "Mahesh", "Ganesh", "Prakash", "Sunil",
    "Anil", "Raju", "Dilip", "Sanjay", "Nitin", "Sachin", "Amol", "Rahul",
]
ENTITY_SUFFIXES = {
    "company": (("Pvt Ltd", "Private Limited", "Ltd"), (6, 3, 1)),
    "llp": (("LLP",), (1,)),
    "partnership": (("& Co", "& Sons", "Brothers", "Associates", "Corporation"), (3, 2, 2, 2, 1)),
    "proprietorship": (("Enterprises", "Traders", "Agencies", "Stores", "Works", ""),
                       (3, 2, 2, 1, 1, 4)),
}
PAN_ENTITY_CHAR = {"company": "C", "llp": "F", "partnership": "F", "proprietorship": "P"}

MONTH_WEIGHTS = {4: 0.85, 5: 0.95, 6: 0.95, 7: 1.0, 8: 1.0, 9: 1.05, 10: 1.1,
                 11: 0.9, 12: 1.0, 1: 1.0, 2: 1.05, 3: 1.3}
SUNDAY_WEIGHT = 0.15

DEFECT_RATES = {
    "missing_gstin": 0.015,
    "malformed_gstin": 0.010,
    "gstin_of_other_vendor": 0.004,
    "invoice_before_po": 0.005,
    "goods_without_grn": 0.005,
    "amount_decimal_slip": 0.0025,
    "tax_type_mismatch": 0.003,
    "tax_rate_mismatch": 0.003,
    "tax_arithmetic_error": 0.002,
    "invoice_date_after_voucher_date": 0.0015,
    "exact_duplicate": 0.010,
    "near_duplicate": 0.006,
    "control_same_day_same_amount": 0.003,
}

REGISTER_COLUMNS = [
    "record_id", "client_name", "client_gstin", "voucher_number", "voucher_date",
    "vendor_code", "vendor_name", "vendor_gstin", "invoice_number", "invoice_date",
    "po_number", "po_date", "grn_number", "grn_date", "hsn_sac", "taxable_value",
    "gst_rate", "cgst", "sgst", "igst", "invoice_value",
]
VENDOR_MASTER_COLUMNS = [
    "client_gstin", "vendor_code", "vendor_name", "vendor_gstin", "vendor_pan",
    "state_code", "registration_type", "msme_status", "category", "hsn_sac",
    "billing_pattern", "blocked", "blocked_since", "block_reason",
]
CLIENT_COLUMNS = [
    "client_name", "client_gstin", "client_pan", "state_code", "state_name", "sector",
    "turnover_cr", "purchases_taxable_cr",
]
LABEL_COLUMNS = ["record_id", "client_gstin", "defect_type", "detail", "related_record_id"]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Vendor:
    """A vendor in the global registry; may supply more than one client."""

    uid: int
    name: str
    pan: str
    gstin: str
    state_code: str
    category: Category
    entity: str
    msme_status: str
    invoice_style: str
    abbr: str
    series_multiplier: float


@dataclass
class ClientVendor:
    """A vendor as it appears in one client's vendor master."""

    vendor: Vendor
    code: str
    blocked_since: Optional[date] = None
    block_reason: str = ""


@dataclass
class Client:
    """One MSME whose purchase register is generated."""

    name: str
    pan: str
    gstin: str
    state_code: str
    sector: Sector
    turnover_cr: float
    target_rows: int
    po_style: str
    purchases_cr: float = 0.0
    vendors: list[ClientVendor] = field(default_factory=list)


@dataclass
class Row:
    """One purchase-register entry before serialisation."""

    uid: int
    client: Client
    cv: ClientVendor
    invoice_date: date
    taxable: Decimal
    po_key: Optional[int] = None
    po_date: Optional[date] = None
    has_grn: bool = False
    grn_date: Optional[date] = None
    voucher_date: Optional[date] = None
    invoice_number: str = ""
    po_number: str = ""
    grn_number: str = ""
    voucher_number: str = ""
    vendor_gstin: str = ""
    hsn_sac: str = ""
    gst_rate: int = 0
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    invoice_value: Decimal = Decimal("0")
    record_id: int = 0

    @property
    def vendor(self) -> Vendor:
        """The underlying global vendor."""
        return self.cv.vendor

    @property
    def is_intra_state(self) -> bool:
        """True when vendor and client are registered in the same state."""
        return self.vendor.state_code == self.client.state_code


@dataclass
class Label:
    """A ground-truth annotation on one register row."""

    uid: int
    defect_type: str
    detail: str = ""
    related_uid: Optional[int] = None


@dataclass
class Dataset:
    """Everything the generator produces, before writing to disk."""

    clients: list[Client]
    rows: list[Row]
    labels: list[Label]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

_PAISE = Decimal("0.01")


def money(value: float | Decimal) -> Decimal:
    """Round to paise, half-up, the way invoices are computed."""
    return Decimal(str(value)).quantize(_PAISE, rounding=ROUND_HALF_UP)


def fy_label(d: date) -> str:
    """Return the financial-year label used in document series, e.g. '25-26'."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def gst_rate_for(category: Category, invoice_date: date) -> int:
    """GST percent applicable to a category on an invoice date."""
    return category.rate_before if invoice_date < GST_RATE_CHANGE_DATE else category.rate_after


def apply_tax(row: Row, rate: int, intra_state: bool) -> None:
    """Set rate, tax heads and invoice value on a row from its taxable value."""
    row.gst_rate = rate
    row.cgst = row.sgst = row.igst = Decimal("0.00")
    if rate:
        if intra_state:
            half = money(row.taxable * Decimal(rate) / Decimal(200))
            row.cgst = row.sgst = half
        else:
            row.igst = money(row.taxable * Decimal(rate) / Decimal(100))
    row.invoice_value = money(row.taxable + row.cgst + row.sgst + row.igst)


def month_end(year: int, month: int) -> date:
    """Last calendar day of a month."""
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


FY_DAYS = [FY_START + timedelta(days=i) for i in range((FY_END - FY_START).days + 1)]
FY_DAY_WEIGHTS = [
    MONTH_WEIGHTS[d.month] * (SUNDAY_WEIGHT if d.weekday() == 6 else 1.0) for d in FY_DAYS
]
FY_MONTHS = [(2025, m) for m in range(4, 13)] + [(2026, m) for m in range(1, 4)]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class Generator:
    """Builds the dataset with one seeded RNG so output is reproducible."""

    def __init__(self, target_rows: int, seed: int) -> None:
        if target_rows < MIN_TARGET_ROWS:
            raise ValueError(f"target_rows must be at least {MIN_TARGET_ROWS}")
        self.rng = random.Random(seed)
        self.target_rows = target_rows
        self.used_pans: set[str] = set()
        self.used_names: set[str] = set()
        self.registry: dict[tuple[str, str], list[Vendor]] = {}
        self.vendors: list[Vendor] = []
        self.rows: list[Row] = []
        self.labels: list[Label] = []
        self.next_uid = 1
        self.next_po_key = 1

    # -- identities -------------------------------------------------------

    def _pan(self, entity_char: str, initial: str) -> str:
        """Unique PAN with the right entity character and name initial."""
        while True:
            pan = (
                "".join(self.rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
                + entity_char + initial
                + f"{self.rng.randint(1, 9999):04d}"
                + self.rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            )
            if pan not in self.used_pans:
                self.used_pans.add(pan)
                return pan

    def _gstin(self, state_code: str, pan: str) -> str:
        """GSTIN for a PAN in a state, with a realistic entity number."""
        entity_number = self.rng.choices("123", weights=(92, 6, 2))[0]
        base = f"{state_code}{pan}{entity_number}Z"
        return base + gstin_check_char(base)

    def _unique_name(self, build) -> str:
        """Call build() until it returns a name not used anywhere yet."""
        for _ in range(200):
            name = build()
            if name not in self.used_names:
                self.used_names.add(name)
                return name
        raise RuntimeError("could not generate a unique name")

    def _prefix(self) -> str:
        """A business-name prefix: a common name or a pair of initials."""
        if self.rng.random() < 0.2:
            letters = "ABDGHJKMNPRSVY"
            return f"{self.rng.choice(letters)} {self.rng.choice(letters)}"
        return self.rng.choice(NAME_PREFIXES)

    @staticmethod
    def _abbr(name: str) -> str:
        """Invoice-series prefix from the leading words of a name."""
        words = [w for w in re.split(r"[^A-Za-z]+", name) if w]
        return "".join(w[0] for w in words[:3]).upper()[:4] or "INV"

    def _vendor_entity(self, category: Category) -> str:
        """Pick a legal form plausible for the category."""
        if category.registration != "Regular":
            return "proprietorship"
        if category.key in ("security", "housekeeping", "manpower"):
            return "company"
        if category.key == "telecom":
            return self.rng.choices(("company", "llp"), weights=(9, 1))[0]
        if category.key == "rent":
            return self.rng.choices(
                ("proprietorship", "company", "partnership"), weights=(5, 3, 2))[0]
        return self.rng.choices(
            ("proprietorship", "partnership", "company", "llp"), weights=(40, 25, 30, 5))[0]

    def _vendor_name(self, category: Category, entity: str) -> tuple[str, str]:
        """Return (name, PAN 5th character) for a new vendor."""
        noun = self.rng.choice(category.nouns)
        if category.registration == "Unregistered":
            name = self._unique_name(
                lambda: f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(category.nouns)}")
            return name, ""
        suffixes, weights = ENTITY_SUFFIXES[entity]

        def build() -> str:
            suffix = self.rng.choices(suffixes, weights=weights)[0]
            if suffix and suffix.split()[-1] in noun.split():
                suffix = ""
            parts = [self._prefix(), noun] + ([suffix] if suffix else [])
            return " ".join(parts)

        name = self._unique_name(build)
        if entity == "proprietorship":
            initial = self.rng.choice(SURNAMES)[0]
        else:
            initial = name[0]
        return name, initial

    def _msme_status(self, entity: str, registration: str) -> str:
        """Udyam registration status as it would sit in a vendor master."""
        if registration == "Unregistered":
            options, weights = ("Micro", "Not registered"), (40, 60)
        elif entity == "company":
            options, weights = ("Micro", "Small", "Medium", "Not registered"), (25, 30, 15, 30)
        else:
            options, weights = ("Micro", "Small", "Not registered"), (55, 20, 25)
        return self.rng.choices(options, weights=weights)[0]

    def _new_vendor(self, category: Category, state_code: str) -> Vendor:
        """Create and register a brand-new vendor."""
        entity = self._vendor_entity(category)
        name, initial = self._vendor_name(category, entity)
        if category.registration == "Unregistered":
            pan, gstin = "", ""
            style = "plain"
        else:
            pan = self._pan(PAN_ENTITY_CHAR[entity], initial)
            gstin = self._gstin(state_code, pan)
            style = self.rng.choices(
                ("abbr_fy_seq", "abbr_dash", "plain", "gst_seq", "abbr_yy_seq", "inv_seq_fy"),
                weights=(30, 15, 20, 10, 15, 10))[0]
        if category.registration != "Regular":
            multiplier = self.rng.uniform(5, 40)
        elif category.billing == "monthly":
            multiplier = self.rng.uniform(1, 6)
        else:
            multiplier = self.rng.uniform(3, 30)
        vendor = Vendor(
            uid=len(self.vendors) + 1, name=name, pan=pan, gstin=gstin,
            state_code=state_code, category=category, entity=entity,
            msme_status=self._msme_status(entity, category.registration),
            invoice_style=style, abbr=self._abbr(name), series_multiplier=multiplier,
        )
        self.vendors.append(vendor)
        self.registry.setdefault((category.key, state_code), []).append(vendor)
        return vendor

    def _vendor_for(self, category: Category, client: Client, taken: set[int]) -> Vendor:
        """Reuse a registry vendor (shared across clients) or create a new one."""
        if self.rng.random() < category.intra_state_share:
            state = client.state_code
        else:
            choices = [s for s in OUT_OF_STATE_WEIGHTS if s != client.state_code]
            state = self.rng.choices(
                choices, weights=[OUT_OF_STATE_WEIGHTS[s] for s in choices])[0]
        pool = [v for v in self.registry.get((category.key, state), []) if v.uid not in taken]
        if pool and category.billing == "adhoc" and category.registration == "Regular" \
                and self.rng.random() < 0.2:
            return self.rng.choice(pool)
        return self._new_vendor(category, state)

    # -- clients ----------------------------------------------------------

    def build_clients(self) -> list[Client]:
        """Create the 25 clients and split the row target across them."""
        sectors = [k for k, n in CLIENT_SECTOR_COUNTS.items() for _ in range(n)]
        states = list(CLIENT_STATES)
        self.rng.shuffle(sectors)
        self.rng.shuffle(states)
        turnovers = [round(math.exp(self.rng.uniform(math.log(5), math.log(100))), 2)
                     for _ in sectors]
        weights = [t ** 0.75 * SECTORS[k].invoice_intensity for t, k in zip(turnovers, sectors)]
        total_w = sum(weights)
        # Every client gets a floor so fixed monthly bills never crowd out
        # its ad hoc purchases; the rest is shared by size and sector.
        spare = self.target_rows - MIN_ROWS_PER_CLIENT * len(sectors)
        shares = [MIN_ROWS_PER_CLIENT + spare * w / total_w for w in weights]
        counts = [int(s) for s in shares]
        remainder = self.target_rows - sum(counts)
        order = sorted(range(len(shares)), key=lambda i: shares[i] - counts[i], reverse=True)
        for i in order[:remainder]:
            counts[i] += 1

        clients = []
        for sector_key, state, turnover, rows in zip(sectors, states, turnovers, counts):
            sector = SECTORS[sector_key]
            entity = self.rng.choices(("company", "llp"), weights=(85, 15))[0]
            suffix = "LLP" if entity == "llp" else self.rng.choice(("Pvt Ltd", "Private Limited"))
            name = self._unique_name(lambda: f"{self._prefix()} {sector.client_noun} {suffix}")
            pan = self._pan(PAN_ENTITY_CHAR[entity], name[0])
            clients.append(Client(
                name=name, pan=pan, gstin=self._gstin(state, pan), state_code=state,
                sector=sector, turnover_cr=turnover, target_rows=rows,
                po_style=self.rng.choice(("po_fy_seq", "abbr_po_seq", "po_yy_seq")),
            ))
        return clients

    # -- invoices ---------------------------------------------------------

    def _new_row(self, client: Client, cv: ClientVendor, invoice_date: date,
                 taxable: Decimal) -> Row:
        """Append a row with a fresh uid."""
        row = Row(uid=self.next_uid, client=client, cv=cv, invoice_date=invoice_date,
                  taxable=taxable)
        self.next_uid += 1
        self.rows.append(row)
        return row

    def _add_client_vendor(self, client: Client, vendor: Vendor) -> ClientVendor:
        """Add a vendor to a client's master with the next vendor code."""
        cv = ClientVendor(vendor=vendor, code=f"V{len(client.vendors) + 1:04d}")
        client.vendors.append(cv)
        return cv

    def _monthly_invoices(self, client: Client, cv: ClientVendor) -> int:
        """Generate one invoice per month for a recurring service vendor."""
        cat = cv.vendor.category
        size = (client.turnover_cr / 20) ** 0.5
        base = cat.median_taxable * size * self.rng.lognormvariate(0, 0.25)
        step = 1000 if cat.key == "rent" else 500
        base = max(step, round(base / step) * step)
        start = 0 if self.rng.random() < 0.85 else self.rng.randint(1, 6)
        revision_month = self.rng.randint(5, 9) if self.rng.random() < 0.3 else None
        revised = round(base * self.rng.uniform(1.05, 1.10) / step) * step
        if cat.key == "rent" or cat.key == "it_support":
            day_rule = self.rng.choice((1, 5)) if cat.key == "it_support" else 1
        elif cat.key == "telecom":
            day_rule = self.rng.randint(5, 20)
        else:
            day_rule = 0  # month end
        created = 0
        for idx, (year, month) in enumerate(FY_MONTHS[start:], start=start):
            amount = revised if revision_month is not None and idx >= revision_month else base
            if cat.sigma:
                amount = amount * self.rng.lognormvariate(0, cat.sigma)
            day = month_end(year, month) if day_rule == 0 else date(year, month, day_rule)
            self._new_row(client, cv, day, money(amount))
            created += 1
        return created

    def _sample_dates(self, window: tuple[int, int], k: int) -> list[date]:
        """Sample k invoice dates from a vendor's active window."""
        a, b = window
        return self.rng.choices(FY_DAYS[a:b + 1], weights=FY_DAY_WEIGHTS[a:b + 1], k=k)

    def _vendor_window(self) -> tuple[int, int]:
        """Active trading window for a vendor (most trade all year)."""
        last = len(FY_DAYS) - 1
        if self.rng.random() < 0.75:
            return 0, last
        length = self.rng.randint(90, 300)
        start = self.rng.randint(0, last - length)
        return start, start + length

    def _adhoc_amount(self, vendor_median: float, category: Category) -> Decimal:
        """Invoice taxable value around a vendor's typical size."""
        value = vendor_median * self.rng.lognormvariate(0, category.sigma)
        if category.kind == "service":
            value = max(500, round(value / 10) * 10)
        elif category.kind == "petty":
            value = max(200, min(25000, round(value / 10) * 10))
        elif category.registration == "Composition":
            value = max(150, round(value))
        else:
            value = max(500, value)
        return money(value)

    def generate_client(self, client: Client) -> None:
        """Build one client's vendor master and invoices."""
        sector = client.sector
        taken: set[int] = set()
        rows_before = len(self.rows)

        def attach(category: Category) -> ClientVendor:
            vendor = self._vendor_for(category, client, taken)
            taken.add(vendor.uid)
            return self._add_client_vendor(client, vendor)

        # Recurring monthly services.
        monthly_rows = 0
        for key in sector.monthly:
            if self.rng.random() < (1.0 if key in ("rent", "telecom") else 0.9):
                monthly_rows += self._monthly_invoices(client, attach(CATEGORIES[key]))
        if self.rng.random() < 0.4:
            monthly_rows += self._monthly_invoices(client, attach(CATEGORIES["telecom"]))

        # Petty unregistered and composition vendors.
        # Petty volume grows with the client, up to full size at 2,000 rows.
        small_scale = min(1.0, client.target_rows / 2000)
        small_vendors: list[tuple[ClientVendor, int]] = []
        for _ in range(self.rng.randint(2, 5)):
            cat = CATEGORIES[self.rng.choice(("local_transport", "casual_labour", "canteen"))]
            small_vendors.append((attach(cat), max(3, int(self.rng.randint(10, 60) * small_scale))))
        for _ in range(self.rng.randint(1, 3)):
            cat = CATEGORIES[self.rng.choice(("hardware_shop", "stationery_shop"))]
            small_vendors.append((attach(cat), max(3, int(self.rng.randint(10, 40) * small_scale))))
        small_rows = sum(n for _, n in small_vendors)

        adhoc_quota = client.target_rows - monthly_rows - small_rows
        if adhoc_quota < 50:
            raise ValueError(f"client {client.name} has too few rows for ad hoc vendors")

        # Ad hoc regular vendors: every category in the mix gets at least one.
        n_adhoc_vendors = min(220, max(len(sector.adhoc_mix), int(20 + client.target_rows / 45)))
        mix_keys = list(sector.adhoc_mix)
        vendor_cats = list(mix_keys)
        vendor_cats += self.rng.choices(
            mix_keys, weights=[sector.adhoc_mix[k] for k in mix_keys],
            k=n_adhoc_vendors - len(mix_keys))
        adhoc: list[ClientVendor] = [attach(CATEGORIES[k]) for k in vendor_cats]
        per_cat = {k: vendor_cats.count(k) for k in mix_keys}
        weights = [
            sector.adhoc_mix[cv.vendor.category.key] / per_cat[cv.vendor.category.key]
            * min(self.rng.paretovariate(1.2), 25.0)
            for cv in adhoc
        ]
        total_w = sum(weights)
        counts = [max(1, int(adhoc_quota * w / total_w)) for w in weights]
        diff = adhoc_quota - sum(counts)
        order = sorted(range(len(adhoc)), key=lambda i: weights[i], reverse=True)
        i = 0
        while diff != 0:
            idx = order[i % len(order)]
            if diff > 0:
                counts[idx] += 1
                diff -= 1
            elif counts[idx] > 1:
                counts[idx] -= 1
                diff += 1
            i += 1

        # One or two vendors get blocked partway through the year.
        blockable = [j for j, cv in enumerate(adhoc) if counts[j] >= 15]
        for j in self.rng.sample(blockable, min(len(blockable), self.rng.randint(1, 2))):
            adhoc[j].blocked_since = FY_DAYS[self.rng.randint(100, 320)]
            adhoc[j].block_reason = self.rng.choice(
                ("GSTIN cancelled", "Quality dispute", "Duplicate vendor record",
                 "Non-filing of GST returns"))

        goods_rows: list[Row] = []
        for cv, count in zip(adhoc, counts):
            cat = cv.vendor.category
            vendor_median = cat.median_taxable * self.rng.lognormvariate(0, 0.45)
            if cat.kind == "service":
                vendor_median *= (client.turnover_cr / 20) ** 0.3
            window = self._vendor_window()
            dates = self._sample_dates(window, count)
            if cv.blocked_since is not None:
                cutoff = (cv.blocked_since - FY_START).days
                for n, d in enumerate(dates):
                    if d >= cv.blocked_since and cutoff > window[0] and self.rng.random() < 0.85:
                        dates[n] = self._sample_dates((window[0], cutoff - 1), 1)[0]
            for d in sorted(dates):
                row = self._new_row(client, cv, d, self._adhoc_amount(vendor_median, cat))
                if cat.kind == "goods":
                    goods_rows.append(row)
                if cv.blocked_since is not None and d >= cv.blocked_since:
                    self.labels.append(Label(row.uid, "blocked_vendor",
                                             f"{cv.block_reason}; blocked since {cv.blocked_since}"))

        for cv, count in small_vendors:
            cat = cv.vendor.category
            vendor_median = cat.median_taxable * self.rng.lognormvariate(0, 0.3)
            for d in sorted(self._sample_dates(self._vendor_window(), count)):
                row = self._new_row(client, cv, d, self._adhoc_amount(vendor_median, cat))

        # Scale ad hoc goods so total register spend fits the client's turnover.
        client_rows = self.rows[rows_before:]
        target = Decimal(str(client.turnover_cr * 1e7 * sector.purchase_ratio))
        goods_total = sum((r.taxable for r in goods_rows
                           if r.vendor.category.registration == "Regular"), Decimal("0"))
        other_total = sum((r.taxable for r in client_rows), Decimal("0")) - goods_total
        if goods_total > 0:
            # Clamp so unit prices stay believable; if the clamp bites, the
            # client's turnover is re-derived from its actual spend instead.
            raw_scale = (target - other_total) / goods_total
            scale = min(Decimal("3.0"), max(Decimal("0.5"), raw_scale))
            for r in goods_rows:
                if r.vendor.category.registration == "Regular":
                    r.taxable = max(money(500), money(r.taxable * scale))
        spend = sum((r.taxable for r in client_rows), Decimal("0"))
        client.purchases_cr = float(spend / Decimal(10**7))
        implied_turnover = client.purchases_cr / sector.purchase_ratio
        if abs(implied_turnover - client.turnover_cr) / client.turnover_cr > 0.05:
            logger.debug("re-deriving turnover for %s: %.2f -> %.2f",
                         client.name, client.turnover_cr, implied_turnover)
            client.turnover_cr = round(implied_turnover, 2)

    # -- PO, GRN, booking dates ------------------------------------------

    def assign_documents(self) -> None:
        """Attach POs, GRNs and voucher dates in invoice order per vendor."""
        by_cv: dict[tuple[int, int], list[Row]] = {}
        for r in self.rows:
            by_cv.setdefault((id(r.client), r.vendor.uid), []).append(r)
        for rows in by_cv.values():
            rows.sort(key=lambda r: (r.invoice_date, r.uid))
            last_po: Optional[tuple[int, date]] = None
            for r in rows:
                cat = r.vendor.category
                if cat.kind == "goods" and cat.registration == "Regular":
                    p_po = 0.8 if r.taxable >= 10000 else 0.35
                elif cat.registration == "Composition":
                    p_po = 0.1
                elif cat.key in ("consulting", "printing"):
                    p_po = 0.4
                else:
                    p_po = 0.0
                if self.rng.random() < p_po:
                    if (last_po is not None and (r.invoice_date - last_po[1]).days <= 90
                            and self.rng.random() < 0.35):
                        r.po_key, r.po_date = last_po
                    else:
                        r.po_key = self.next_po_key
                        self.next_po_key += 1
                        r.po_date = r.invoice_date - timedelta(
                            days=int(self.rng.triangular(1, 45, 7)))
                        last_po = (r.po_key, r.po_date)
                if cat.kind == "goods":
                    r.has_grn = True
                    r.grn_date = r.invoice_date + timedelta(
                        days=self.rng.choices((0, 1, 2, 3, 4, 5, 7),
                                              weights=(30, 30, 15, 10, 6, 5, 4))[0])
                anchor = r.grn_date or r.invoice_date
                delay = min(45, int(self.rng.expovariate(1 / 4)))
                if cat.billing == "monthly":
                    delay = min(delay, 5)
                r.voucher_date = anchor + timedelta(days=delay)

    # -- defect selection --------------------------------------------------

    def _count(self, defect: str) -> int:
        """Number of rows to seed for a defect type."""
        return round(DEFECT_RATES[defect] * self.target_rows)

    def _pick(self, eligible: list[Row], k: int, used: set[int]) -> list[Row]:
        """Sample k rows not already carrying a label."""
        pool = [r for r in eligible if r.uid not in used]
        chosen = self.rng.sample(pool, min(k, len(pool)))
        used.update(r.uid for r in chosen)
        return chosen

    def seed_pre_numbering(self, used: set[int]) -> None:
        """Defects and controls that must exist before document numbers are assigned."""
        po_usage: dict[int, int] = {}
        for r in self.rows:
            if r.po_key is not None:
                po_usage[r.po_key] = po_usage.get(r.po_key, 0) + 1

        single_po = [r for r in self.rows if r.po_key is not None and po_usage[r.po_key] == 1]
        for r in self._pick(single_po, self._count("invoice_before_po"), used):
            r.po_date = r.invoice_date + timedelta(days=self.rng.randint(1, 20))
            self.labels.append(Label(r.uid, "invoice_before_po",
                                     f"PO dated {(r.po_date - r.invoice_date).days} days after invoice"))

        goods = [r for r in self.rows if r.has_grn]
        for r in self._pick(goods, self._count("goods_without_grn"), used):
            r.has_grn = False
            r.grn_date = None
            self.labels.append(Label(r.uid, "goods_without_grn", "goods invoice with no GRN"))

        regular_goods = [r for r in self.rows if r.vendor.category.kind == "goods"
                         and r.vendor.category.registration == "Regular"]
        for src in self._pick(regular_goods, self._count("control_same_day_same_amount"), used):
            twin = self._new_row(src.client, src.cv, src.invoice_date, src.taxable)
            twin.po_key, twin.po_date = src.po_key, src.po_date
            twin.has_grn = src.has_grn
            twin.grn_date = src.grn_date
            twin.voucher_date = src.voucher_date
            used.add(twin.uid)
            self.labels.append(Label(twin.uid, "control_same_day_same_amount",
                                     "legitimate second invoice, different invoice number",
                                     related_uid=src.uid))

    def assign_numbers_and_tax(self) -> None:
        """Invoice, PO and GRN numbers, GSTIN, HSN and tax for every row."""
        by_vendor: dict[int, list[Row]] = {}
        for r in self.rows:
            by_vendor.setdefault(r.vendor.uid, []).append(r)
        for vendor_uid, rows in by_vendor.items():
            vendor = self.vendors[vendor_uid - 1]
            rows.sort(key=lambda r: (r.invoice_date, r.uid))
            total = min(99999, max(len(rows) + 5, int(len(rows) * vendor.series_multiplier)))
            numbers = sorted(self.rng.sample(range(1, total + 1), len(rows)))
            for r, n in zip(rows, numbers):
                r.invoice_number = self._format_invoice_number(vendor, n, r.invoice_date)

        for client in {id(r.client): r.client for r in self.rows}.values():
            rows = [r for r in self.rows if r.client is client]
            po_dates: dict[int, date] = {}
            for r in rows:
                if r.po_key is not None:
                    po_dates.setdefault(r.po_key, r.po_date)
            po_numbers: dict[int, str] = {}
            series_count: dict[str, int] = {}
            for key in sorted(po_dates, key=lambda k: (po_dates[k], k)):
                fy = fy_label(po_dates[key])
                series_count[fy] = series_count.get(fy, 0) + 1
                po_numbers[key] = self._format_po_number(client, fy, series_count[fy])
            grn_count: dict[str, int] = {}
            for r in sorted((r for r in rows if r.has_grn), key=lambda r: (r.grn_date, r.uid)):
                fy = fy_label(r.grn_date)
                grn_count[fy] = grn_count.get(fy, 0) + 1
                r.grn_number = f"GRN/{fy}/{grn_count[fy]:05d}"
            for r in rows:
                if r.po_key is not None:
                    r.po_number = po_numbers[r.po_key]

        for r in self.rows:
            cat = r.vendor.category
            r.vendor_gstin = r.vendor.gstin
            r.hsn_sac = cat.hsn_sac
            apply_tax(r, gst_rate_for(cat, r.invoice_date), r.is_intra_state)

    @staticmethod
    def _format_invoice_number(vendor: Vendor, n: int, d: date) -> str:
        """Render a vendor's invoice number in its house style."""
        fy = fy_label(d)
        yy = fy[:2]
        style = vendor.invoice_style
        if style == "abbr_fy_seq":
            text = f"{vendor.abbr}/{fy}/{n:04d}"
        elif style == "abbr_dash":
            text = f"{vendor.abbr}-{n}"
        elif style == "gst_seq":
            text = f"GST/{n:05d}"
        elif style == "abbr_yy_seq":
            text = f"{vendor.abbr}{yy}{n:05d}"
        elif style == "inv_seq_fy":
            text = f"INV/{n}/{fy}"
        else:
            text = str(n)
        assert len(text) <= MAX_INVOICE_NUMBER_LENGTH, text
        return text

    @staticmethod
    def _format_po_number(client: Client, fy: str, n: int) -> str:
        """Render a client's PO number in its house style."""
        if client.po_style == "po_fy_seq":
            return f"PO/{fy}/{n:04d}"
        if client.po_style == "abbr_po_seq":
            return f"{Generator._abbr(client.name)}/PO/{fy[:2]}{n:04d}"
        return f"PO-{fy[:2]}{n:04d}"

    # -- post-numbering defects ------------------------------------------

    def _corrupt_gstin(self, gstin: str) -> tuple[str, str]:
        """Return (bad_gstin, mode) using a realistic data-entry error."""
        lookalikes = {"0": "O", "O": "0", "1": "I", "I": "1", "5": "S", "S": "5",
                      "8": "B", "B": "8", "2": "Z", "Z": "2"}
        for _ in range(100):
            mode = self.rng.choices(
                ("adjacent_transposition", "lookalike_character", "dropped_character",
                 "doubled_character"), weights=(35, 30, 20, 15))[0]
            if mode == "adjacent_transposition":
                i = self.rng.randint(0, 13)
                if gstin[i] == gstin[i + 1]:
                    continue
                bad = gstin[:i] + gstin[i + 1] + gstin[i] + gstin[i + 2:]
            elif mode == "lookalike_character":
                positions = [i for i, ch in enumerate(gstin) if ch in lookalikes]
                if not positions:
                    continue
                i = self.rng.choice(positions)
                bad = gstin[:i] + lookalikes[gstin[i]] + gstin[i + 1:]
            elif mode == "dropped_character":
                i = self.rng.randint(0, 14)
                bad = gstin[:i] + gstin[i + 1:]
            else:
                i = self.rng.randint(0, 14)
                bad = gstin[:i] + gstin[i] + gstin[i:]
            if not is_valid_gstin(bad):
                return bad, mode
        raise RuntimeError(f"could not corrupt {gstin}")

    def seed_post_numbering(self, used: set[int]) -> None:
        """Field-level defects on finished rows."""
        registered = [r for r in self.rows if r.vendor.gstin]
        regular_taxed = [r for r in self.rows
                         if r.vendor.category.registration == "Regular" and r.gst_rate > 0]

        for r in self._pick(registered, self._count("missing_gstin"), used):
            r.vendor_gstin = ""
            self.labels.append(Label(r.uid, "missing_gstin", "registered vendor, GSTIN not captured"))

        for r in self._pick(registered, self._count("malformed_gstin"), used):
            r.vendor_gstin, mode = self._corrupt_gstin(r.vendor.gstin)
            self.labels.append(Label(r.uid, "malformed_gstin", mode))

        for r in self._pick(registered, self._count("gstin_of_other_vendor"), used):
            others = [cv.vendor for cv in r.client.vendors
                      if cv.vendor.gstin and cv.vendor.uid != r.vendor.uid]
            other = self.rng.choice(others)
            r.vendor_gstin = other.gstin
            self.labels.append(Label(r.uid, "gstin_of_other_vendor",
                                     f"GSTIN belongs to {other.name}"))

        goods = [r for r in regular_taxed if r.vendor.category.kind == "goods"
                 and r.vendor.category.billing == "adhoc"]
        for r in self._pick(goods, self._count("amount_decimal_slip"), used):
            factor = self.rng.choice((10, 100))
            r.taxable = money(r.taxable * factor)
            apply_tax(r, r.gst_rate, r.is_intra_state)
            self.labels.append(Label(r.uid, "amount_decimal_slip", f"x{factor}"))

        for r in self._pick(regular_taxed, self._count("tax_type_mismatch"), used):
            apply_tax(r, r.gst_rate, not r.is_intra_state)
            detail = ("IGST charged on intra-state purchase" if r.is_intra_state
                      else "CGST+SGST charged on inter-state purchase")
            self.labels.append(Label(r.uid, "tax_type_mismatch", detail))

        n_rate = self._count("tax_rate_mismatch")
        stale = [r for r in regular_taxed if r.vendor.category.key in RATE_CHANGED_CATEGORIES
                 and r.invoice_date >= GST_RATE_CHANGE_DATE]
        for r in self._pick(stale, n_rate // 2, used):
            apply_tax(r, r.vendor.category.rate_before, r.is_intra_state)
            self.labels.append(Label(r.uid, "tax_rate_mismatch",
                                     f"stale pre-22-Sep-2025 rate {r.gst_rate}%"))
        for r in self._pick(regular_taxed, n_rate - n_rate // 2, used):
            correct = r.gst_rate
            wrong = self.rng.choice([x for x in (5, 12, 18, 28) if x != correct])
            apply_tax(r, wrong, r.is_intra_state)
            self.labels.append(Label(r.uid, "tax_rate_mismatch",
                                     f"charged {wrong}%, schedule rate {correct}%"))

        for r in self._pick(regular_taxed, self._count("tax_arithmetic_error"), used):
            modes = ["total_excludes_tax", "total_off"] + (["cgst_sgst_unequal"] if r.is_intra_state else [])
            mode = self.rng.choice(modes)
            if mode == "total_excludes_tax":
                r.invoice_value = r.taxable
            elif mode == "total_off":
                delta = Decimal(self.rng.randint(2, 999)) * self.rng.choice((1, -1))
                r.invoice_value = money(r.invoice_value + delta)
            else:
                r.sgst = money(r.sgst + Decimal(self.rng.randint(1, 50)))
            self.labels.append(Label(r.uid, "tax_arithmetic_error", mode))

        for r in self._pick(self.rows, self._count("invoice_date_after_voucher_date"), used):
            r.invoice_date = r.voucher_date + timedelta(days=self.rng.randint(2, 40))
            self.labels.append(Label(r.uid, "invoice_date_after_voucher_date",
                                     "invoice dated after it was booked"))

    def seed_duplicates(self, used: set[int]) -> None:
        """Exact and near duplicates of clean rows, appended as new entries."""
        clean = [r for r in self.rows if r.uid not in used]

        def clone(src: Row) -> Row:
            twin = self._new_row(src.client, src.cv, src.invoice_date, src.taxable)
            for attr in ("po_key", "po_date", "has_grn", "grn_date", "invoice_number",
                         "po_number", "grn_number", "vendor_gstin", "hsn_sac", "gst_rate",
                         "cgst", "sgst", "igst", "invoice_value"):
                setattr(twin, attr, getattr(src, attr))
            twin.voucher_date = src.voucher_date + timedelta(days=self.rng.randint(0, 30))
            return twin

        for src in self._pick(clean, self._count("exact_duplicate"), used):
            twin = clone(src)
            self.labels.append(Label(twin.uid, "exact_duplicate", "same invoice booked twice",
                                     related_uid=src.uid))

        for src in self._pick(clean, self._count("near_duplicate"), used):
            modes = self._near_duplicate_modes(src)
            mode = self.rng.choice(modes)
            twin = clone(src)
            inv = src.invoice_number
            if mode == "trailing_space":
                twin.invoice_number = inv + " "
            elif mode == "lowercase":
                twin.invoice_number = inv.lower()
            elif mode == "separator_changed":
                twin.invoice_number = inv.replace("/", "-") if "/" in inv else inv.replace("-", "/")
            elif mode == "leading_zeros_dropped":
                twin.invoice_number = re.sub(r"(?<!\d)0+(\d)", r"\1", inv)
            elif mode == "prefix_dropped":
                twin.invoice_number = re.findall(r"\d+", inv)[-1] if not inv.startswith("INV/") \
                    else re.findall(r"\d+", inv)[0]
            elif mode == "day_month_swapped":
                d = src.invoice_date
                twin.invoice_date = date(d.year, d.day, d.month)
            else:  # total_rounded_to_rupee
                twin.invoice_value = src.invoice_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            self.labels.append(Label(twin.uid, "near_duplicate", mode, related_uid=src.uid))

    @staticmethod
    def _near_duplicate_modes(src: Row) -> list[str]:
        """Near-duplicate variations that actually change something for this row."""
        inv = src.invoice_number
        modes = ["trailing_space"]
        if any(ch.isalpha() for ch in inv):
            modes.append("lowercase")
            modes.append("prefix_dropped")
        if "/" in inv or "-" in inv:
            modes.append("separator_changed")
        if re.search(r"(?<!\d)0+\d", inv):
            modes.append("leading_zeros_dropped")
        d = src.invoice_date
        if d.day <= 12 and d.day != d.month:
            modes.append("day_month_swapped")
        if src.invoice_value != src.invoice_value.quantize(Decimal("1")):
            modes.append("total_rounded_to_rupee")
        return modes

    # -- finalise ----------------------------------------------------------

    def finalise(self) -> None:
        """Order like a register (client, booking date) and assign voucher numbers."""
        client_order = {}
        for r in self.rows:
            client_order.setdefault(id(r.client), len(client_order))
        self.rows.sort(key=lambda r: (client_order[id(r.client)], r.voucher_date, r.uid))
        counters: dict[tuple[int, str], int] = {}
        for record_id, r in enumerate(self.rows, start=1):
            r.record_id = record_id
            fy = fy_label(r.voucher_date)
            key = (id(r.client), fy)
            counters[key] = counters.get(key, 0) + 1
            r.voucher_number = f"PUR/{fy}/{counters[key]:05d}"

    def run(self) -> Dataset:
        """Generate the whole dataset."""
        clients = self.build_clients()
        for client in clients:
            self.generate_client(client)
        self.assign_documents()
        used: set[int] = {label.uid for label in self.labels}
        self.seed_pre_numbering(used)
        self.assign_numbers_and_tax()
        self.seed_post_numbering(used)
        self.seed_duplicates(used)
        self.finalise()
        uid_to_record = {r.uid: r.record_id for r in self.rows}
        self.labels.sort(key=lambda lb: uid_to_record[lb.uid])
        return Dataset(clients=clients, rows=self.rows, labels=self.labels)


def generate(target_rows: int = DEFAULT_TARGET_ROWS, seed: int = DEFAULT_SEED) -> Dataset:
    """Build the dataset in memory."""
    return Generator(target_rows, seed).run()


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _fmt_date(d: Optional[date]) -> str:
    """ISO date or blank."""
    return d.isoformat() if d else ""


def register_records(dataset: Dataset) -> list[dict[str, str]]:
    """Purchase-register rows as CSV-ready dicts."""
    out = []
    for r in dataset.rows:
        out.append({
            "record_id": str(r.record_id),
            "client_name": r.client.name,
            "client_gstin": r.client.gstin,
            "voucher_number": r.voucher_number,
            "voucher_date": _fmt_date(r.voucher_date),
            "vendor_code": r.cv.code,
            "vendor_name": r.vendor.name,
            "vendor_gstin": r.vendor_gstin,
            "invoice_number": r.invoice_number,
            "invoice_date": _fmt_date(r.invoice_date),
            "po_number": r.po_number,
            "po_date": _fmt_date(r.po_date) if r.po_number else "",
            "grn_number": r.grn_number,
            "grn_date": _fmt_date(r.grn_date) if r.has_grn else "",
            "hsn_sac": r.hsn_sac,
            "taxable_value": f"{r.taxable:.2f}",
            "gst_rate": str(r.gst_rate),
            "cgst": f"{r.cgst:.2f}",
            "sgst": f"{r.sgst:.2f}",
            "igst": f"{r.igst:.2f}",
            "invoice_value": f"{r.invoice_value:.2f}",
        })
    return out


def vendor_master_records(dataset: Dataset) -> list[dict[str, str]]:
    """Per-client vendor master rows."""
    out = []
    for client in dataset.clients:
        for cv in client.vendors:
            v = cv.vendor
            out.append({
                "client_gstin": client.gstin,
                "vendor_code": cv.code,
                "vendor_name": v.name,
                "vendor_gstin": v.gstin,
                "vendor_pan": v.pan,
                "state_code": v.state_code,
                "registration_type": v.category.registration,
                "msme_status": v.msme_status,
                "category": v.category.key,
                "hsn_sac": v.category.hsn_sac,
                "billing_pattern": v.category.billing,
                "blocked": "true" if cv.blocked_since else "false",
                "blocked_since": _fmt_date(cv.blocked_since),
                "block_reason": cv.block_reason,
            })
    return out


def client_records(dataset: Dataset) -> list[dict[str, str]]:
    """Client list with turnover and clean taxable spend (before seeded defects)."""
    return [{
        "client_name": c.name,
        "client_gstin": c.gstin,
        "client_pan": c.pan,
        "state_code": c.state_code,
        "state_name": STATE_NAMES[c.state_code],
        "sector": c.sector.key,
        "turnover_cr": f"{c.turnover_cr:.2f}",
        "purchases_taxable_cr": f"{c.purchases_cr:.2f}",
    } for c in dataset.clients]


def label_records(dataset: Dataset) -> list[dict[str, str]]:
    """Ground-truth labels keyed by record_id."""
    by_uid = {r.uid: r for r in dataset.rows}
    return [{
        "record_id": str(by_uid[lb.uid].record_id),
        "client_gstin": by_uid[lb.uid].client.gstin,
        "defect_type": lb.defect_type,
        "detail": lb.detail,
        "related_record_id": str(by_uid[lb.related_uid].record_id) if lb.related_uid else "",
    } for lb in dataset.labels]


def _write_csv(path: Path, columns: list[str], records: list[dict[str, str]]) -> None:
    """Write records as CSV with a fixed column order and LF line endings."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_dataset(dataset: Dataset, out_dir: Path) -> dict[str, Path]:
    """Write all outputs; the gzip copy has a pinned header so it is reproducible."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "register": out_dir / "purchase_register.csv",
        "register_gz": out_dir / "purchase_register.csv.gz",
        "vendor_master": out_dir / "vendor_master.csv",
        "clients": out_dir / "clients.csv",
        "labels": out_dir / "labels.csv",
    }
    _write_csv(paths["register"], REGISTER_COLUMNS, register_records(dataset))
    with paths["register"].open("rb") as src, paths["register_gz"].open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz:
            gz.write(src.read())
    _write_csv(paths["vendor_master"], VENDOR_MASTER_COLUMNS, vendor_master_records(dataset))
    _write_csv(paths["clients"], CLIENT_COLUMNS, client_records(dataset))
    _write_csv(paths["labels"], LABEL_COLUMNS, label_records(dataset))
    return paths


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=DEFAULT_TARGET_ROWS,
                        help="base rows before duplicates are added (default 100000)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    dataset = generate(args.rows, args.seed)
    paths = write_dataset(dataset, args.out_dir)

    counts: dict[str, int] = {}
    for lb in dataset.labels:
        counts[lb.defect_type] = counts.get(lb.defect_type, 0) + 1
    logger.info("register rows: %d across %d clients", len(dataset.rows), len(dataset.clients))
    logger.info("vendor master rows: %d", sum(len(c.vendors) for c in dataset.clients))
    for defect, n in sorted(counts.items()):
        logger.info("  %-34s %6d", defect, n)
    for name, path in paths.items():
        logger.info("wrote %s -> %s", name, path)


if __name__ == "__main__":
    main()
