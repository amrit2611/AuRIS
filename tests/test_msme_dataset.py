"""Invariant tests for the synthetic Indian MSME purchase-register generator.

The dataset is only useful if its ground truth is trustworthy: clean rows
must really be clean and every labelled row must really carry its defect.
These tests generate a small dataset in memory and check both directions.
"""
import importlib.util
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

_GENERATOR_PATH = Path(__file__).resolve().parent.parent / "generate_msme_dataset.py"
_spec = importlib.util.spec_from_file_location("generate_msme_dataset", _GENERATOR_PATH)
gen = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gen  # dataclasses resolve their module through sys.modules
_spec.loader.exec_module(gen)

ROWS = 12000


@pytest.fixture(scope="module")
def dataset():
    """A small seeded dataset shared by every test in this module."""
    return gen.generate(target_rows=ROWS, seed=7)


@pytest.fixture(scope="module")
def labels_by_uid(dataset):
    """uid -> Label for quick lookup."""
    return {lb.uid: lb for lb in dataset.labels}


@pytest.fixture(scope="module")
def clean_rows(dataset, labels_by_uid):
    """Rows that carry no label at all."""
    return [r for r in dataset.rows if r.uid not in labels_by_uid]


def _rows_with(dataset, labels_by_uid, defect):
    """Rows labelled with a given defect type."""
    return [r for r in dataset.rows
            if r.uid in labels_by_uid and labels_by_uid[r.uid].defect_type == defect]


class TestGstinHelpers:
    def test_published_gstn_example_validates(self):
        """The algorithm reproduces the check digit of GSTN's published example."""
        assert gen.gstin_check_char("27AAPFU0939F1Z") == "V"
        assert gen.is_valid_gstin("27AAPFU0939F1ZV")

    def test_rejects_bad_values(self):
        """Blank, short and wrong-check-digit GSTINs fail."""
        assert not gen.is_valid_gstin("")
        assert not gen.is_valid_gstin(None)
        assert not gen.is_valid_gstin("27AAPFU0939F1Z")
        assert not gen.is_valid_gstin("27AAPFU0939F1ZW")


class TestShape:
    def test_refuses_tiny_targets(self):
        """Below the minimum, clients would be too small to be realistic."""
        with pytest.raises(ValueError):
            gen.generate(target_rows=5000)

    def test_row_count_includes_duplicates(self, dataset):
        """Base rows hit the target exactly; duplicates add on top."""
        dup_types = {"exact_duplicate", "near_duplicate", "control_same_day_same_amount"}
        n_added = sum(1 for lb in dataset.labels if lb.defect_type in dup_types)
        assert len(dataset.rows) == ROWS + n_added

    def test_defect_counts_match_rates(self, dataset):
        """Every fixed-rate defect is seeded at its configured count."""
        counts = Counter(lb.defect_type for lb in dataset.labels)
        for defect, rate in gen.DEFECT_RATES.items():
            assert counts[defect] == round(rate * ROWS), defect
        assert counts["blocked_vendor"] > 0

    def test_one_label_per_row(self, dataset):
        """Defects are disjoint so each can be scored on its own."""
        uids = [lb.uid for lb in dataset.labels]
        assert len(uids) == len(set(uids))

    def test_deterministic(self):
        """Same seed, same output."""
        a = gen.register_records(gen.generate(target_rows=10000, seed=11))
        b = gen.register_records(gen.generate(target_rows=10000, seed=11))
        assert a == b

    def test_write_is_byte_reproducible(self, tmp_path):
        """Two writes of the same dataset produce identical files, gzip included."""
        ds = gen.generate(target_rows=10000, seed=11)
        first = gen.write_dataset(ds, tmp_path / "a")
        second = gen.write_dataset(ds, tmp_path / "b")
        for key in first:
            assert first[key].read_bytes() == second[key].read_bytes(), key


class TestCleanRowsAreClean:
    def test_gstin_matches_vendor(self, clean_rows):
        """Registered vendors carry their own valid GSTIN; unregistered carry none."""
        for r in clean_rows:
            assert r.vendor_gstin == r.vendor.gstin
            if r.vendor.category.registration == "Unregistered":
                assert r.vendor_gstin == ""
            else:
                assert gen.is_valid_gstin(r.vendor_gstin)
                assert r.vendor_gstin[2:12] == r.vendor.pan
                assert r.vendor_gstin[:2] == r.vendor.state_code

    def test_tax_is_correct(self, clean_rows):
        """Rate follows the schedule by date; heads follow intra or inter state."""
        for r in clean_rows:
            cat = r.vendor.category
            assert r.gst_rate == gen.gst_rate_for(cat, r.invoice_date)
            if r.gst_rate == 0:
                assert r.cgst == r.sgst == r.igst == 0
            elif r.is_intra_state:
                assert r.cgst == r.sgst == gen.money(r.taxable * r.gst_rate / Decimal(200))
                assert r.igst == 0
            else:
                assert r.igst == gen.money(r.taxable * r.gst_rate / Decimal(100))
                assert r.cgst == r.sgst == 0
            assert r.invoice_value == gen.money(r.taxable + r.cgst + r.sgst + r.igst)

    def test_rate_change_is_applied(self, clean_rows):
        """Categories cut from 28% to 18% show both rates around 22 Sep 2025."""
        changed = [r for r in clean_rows if r.vendor.category.key in gen.RATE_CHANGED_CATEGORIES]
        before = {r.gst_rate for r in changed if r.invoice_date < gen.GST_RATE_CHANGE_DATE}
        after = {r.gst_rate for r in changed if r.invoice_date >= gen.GST_RATE_CHANGE_DATE}
        assert before == {28}
        assert after == {18}

    def test_document_dates_are_ordered(self, clean_rows):
        """PO before invoice, GRN after invoice, voucher after both, invoice in FY."""
        for r in clean_rows:
            assert gen.FY_START <= r.invoice_date <= gen.FY_END
            if r.po_number:
                assert r.po_date <= r.invoice_date
            if r.has_grn:
                assert r.invoice_date <= r.grn_date <= r.voucher_date
            assert r.voucher_date >= r.invoice_date

    def test_grn_only_on_goods(self, clean_rows):
        """Goods carry a GRN, services and petty purchases never do."""
        for r in clean_rows:
            assert r.has_grn == (r.vendor.category.kind == "goods")
            assert bool(r.grn_number) == r.has_grn

    def test_composition_and_unregistered_rules(self, clean_rows):
        """No GST from composition or unregistered vendors; composition is intra-state."""
        for r in clean_rows:
            reg = r.vendor.category.registration
            if reg != "Regular":
                assert r.gst_rate == 0
            if reg == "Composition":
                assert r.is_intra_state
            if reg == "Unregistered":
                assert not r.po_number and not r.hsn_sac

    def test_invoice_numbers_unique_and_short(self, dataset, labels_by_uid):
        """Rule 46: unique per vendor per FY, at most 16 characters."""
        seen = set()
        for r in dataset.rows:
            label = labels_by_uid.get(r.uid)
            if label and label.defect_type in ("exact_duplicate", "near_duplicate"):
                continue
            assert len(r.invoice_number) <= gen.MAX_INVOICE_NUMBER_LENGTH
            key = (r.vendor.uid, r.invoice_number)
            assert key not in seen
            seen.add(key)

    def test_pan_entity_character(self, dataset):
        """Companies have PAN type C; LLPs and firms F; proprietors P."""
        for v in {id(cv.vendor): cv.vendor for c in dataset.clients for cv in c.vendors}.values():
            if v.pan:
                assert v.pan[3] == gen.PAN_ENTITY_CHAR[v.entity]


class TestLabelledRowsAreDefective:
    def test_gstin_defects(self, dataset, labels_by_uid):
        """Missing is blank, malformed fails validation, other-vendor is valid but wrong."""
        for r in _rows_with(dataset, labels_by_uid, "missing_gstin"):
            assert r.vendor_gstin == "" and r.vendor.gstin
        for r in _rows_with(dataset, labels_by_uid, "malformed_gstin"):
            assert not gen.is_valid_gstin(r.vendor_gstin)
        for r in _rows_with(dataset, labels_by_uid, "gstin_of_other_vendor"):
            assert gen.is_valid_gstin(r.vendor_gstin)
            assert r.vendor_gstin != r.vendor.gstin
            assert r.vendor_gstin in {cv.vendor.gstin for cv in r.client.vendors}

    def test_document_defects(self, dataset, labels_by_uid):
        """PO after invoice, goods without GRN, invoice dated after booking."""
        for r in _rows_with(dataset, labels_by_uid, "invoice_before_po"):
            assert r.po_date > r.invoice_date
        for r in _rows_with(dataset, labels_by_uid, "goods_without_grn"):
            assert r.vendor.category.kind == "goods" and not r.has_grn
        for r in _rows_with(dataset, labels_by_uid, "invoice_date_after_voucher_date"):
            assert r.invoice_date > r.voucher_date

    def test_blocked_vendor_rows(self, dataset, labels_by_uid):
        """Blocked label exactly when the invoice is on or after the block date."""
        for r in dataset.rows:
            if r.cv.blocked_since is None:
                continue
            labelled = labels_by_uid.get(r.uid)
            is_blocked_label = labelled is not None and labelled.defect_type == "blocked_vendor"
            if is_blocked_label:
                assert r.invoice_date >= r.cv.blocked_since
            elif labelled is None:
                assert r.invoice_date < r.cv.blocked_since

    def test_tax_defects(self, dataset, labels_by_uid):
        """Each tax defect breaks the specific rule it claims to break."""
        for r in _rows_with(dataset, labels_by_uid, "tax_type_mismatch"):
            assert (r.igst > 0) if r.is_intra_state else (r.cgst > 0)
        for r in _rows_with(dataset, labels_by_uid, "tax_rate_mismatch"):
            assert r.gst_rate != gen.gst_rate_for(r.vendor.category, r.invoice_date)
        for r in _rows_with(dataset, labels_by_uid, "tax_arithmetic_error"):
            assert (r.invoice_value != gen.money(r.taxable + r.cgst + r.sgst + r.igst)
                    or r.cgst != r.sgst)

    def test_duplicates_and_controls(self, dataset, labels_by_uid):
        """Exact copies match their source, near copies differ in one field, controls differ in number."""
        by_uid = {r.uid: r for r in dataset.rows}

        def key(r):
            return (r.vendor.uid, r.vendor_gstin, r.invoice_number, r.invoice_date,
                    r.taxable, r.invoice_value)

        for r in _rows_with(dataset, labels_by_uid, "exact_duplicate"):
            src = by_uid[labels_by_uid[r.uid].related_uid]
            assert key(r) == key(src)
            assert r.voucher_number != src.voucher_number
        for r in _rows_with(dataset, labels_by_uid, "near_duplicate"):
            src = by_uid[labels_by_uid[r.uid].related_uid]
            assert sum(a != b for a, b in zip(key(r), key(src))) == 1
        for r in _rows_with(dataset, labels_by_uid, "control_same_day_same_amount"):
            src = by_uid[labels_by_uid[r.uid].related_uid]
            assert (r.vendor.uid, r.invoice_date, r.taxable) == (src.vendor.uid, src.invoice_date, src.taxable)
            assert r.invoice_number != src.invoice_number
            assert src.uid not in labels_by_uid
