"""Generate a realistic synthetic transaction dataset for AuRIS testing."""
import csv
import random
from datetime import datetime, timedelta

VENDORS = [
    "ABC Corp", "XYZ Ltd", "DEF Inc", "GHI Ltd", "JKL LLC",
    "MNO Inc", "PQR Ltd", "RST Pvt", "UVW Co", "IJK Inc",
    "LMN Ltd", "OPQ Corp", "RST Inc", "XYZ Pvt", "ABC Ltd",
    "DEF Co", "GHI Inc", "JKL Pvt", "Apex Trading", "Nova Supplies",
    "Bright Solutions", "Omega Services", "Delta Logistics", "Sigma Tech",
    "Prime Vendors", "Atlas Materials", "Zenith Partners", "Vanguard Corp",
    "Pinnacle Ltd", "Quantum Industries",
]

DESCRIPTIONS = [
    "Goods Purchase", "Services", "Equipment", "Consulting", "Marketing",
    "Supplies", "Maintenance", "Logistics", "Software License", "Training",
    "Insurance Premium", "Office Supplies", "Travel Reimbursement",
    "Raw Materials", "Utilities", "Subscription", "Advertising",
    "Professional Fees", "Repair & Maintenance", "Catering",
]

NUM_ROWS = 10000
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2025, 12, 31)
OUTPUT_FILE = "transactions.csv"


def random_date():
    delta = END_DATE - START_DATE
    return START_DATE + timedelta(days=random.randint(0, delta.days))


def generate_amount(vendor):
    base = hash(vendor) % 5000 + 2000
    return round(random.gauss(base, base * 0.4), 2)


def main():
    random.seed(42)
    rows = []

    vendor_weights = [random.randint(1, 10) for _ in VENDORS]

    for i in range(1, NUM_ROWS + 1):
        vendor = random.choices(VENDORS, weights=vendor_weights, k=1)[0]
        amount = generate_amount(vendor)
        date = random_date().strftime("%Y-%m-%d")
        description = random.choice(DESCRIPTIONS)

        # ~2% chance of missing amount (set to empty string)
        if random.random() < 0.02:
            amount = ""

        # ~1% chance of missing description
        if random.random() < 0.01:
            description = ""

        rows.append({
            "invoice_id": i,
            "vendor": vendor,
            "amount": amount,
            "date": date,
            "description": description,
        })

    # Inject ~150 exact duplicates (same vendor, amount, date)
    for _ in range(150):
        src = random.choice(rows)
        dup = src.copy()
        dup["invoice_id"] = len(rows) + 1
        rows.append(dup)

    # Inject ~50 extreme outliers
    for _ in range(50):
        vendor = random.choice(VENDORS)
        rows.append({
            "invoice_id": len(rows) + 1,
            "vendor": vendor,
            "amount": round(random.uniform(80000, 200000), 2),
            "date": random_date().strftime("%Y-%m-%d"),
            "description": random.choice(DESCRIPTIONS),
        })

    random.shuffle(rows)

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["invoice_id", "vendor", "amount", "date", "description"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} transactions -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
