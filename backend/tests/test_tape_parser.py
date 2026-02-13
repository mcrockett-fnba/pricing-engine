"""Tests for the Excel loan tape parser."""
import io
import pytest
from openpyxl import Workbook

from app.services.tape_parser import parse_loan_tape


def _make_excel(rows, columns=None):
    """Create an in-memory Excel file with given rows and return a BytesIO."""
    wb = Workbook()
    ws = wb.active
    if columns is None:
        columns = [
            "Current Balance", "Current Rate", "Most Recent Blended Credit Score for Pricing",
            "LTV used for Pricing (%)", "Seasoning", "FNBA Calculated Rem Term",
        ]
    ws.append(columns)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class TestParseLoanTape:
    def test_basic_parse(self):
        """Parse a small tape with valid data."""
        rows = [
            [250000, 7.2, 660, 85, 80, 280],
            [150000, 6.8, 700, 75, 60, 300],
        ]
        tape = _make_excel(rows)
        pkg = parse_loan_tape(tape, "test_tape.xlsx")

        assert pkg.loan_count == 2
        assert len(pkg.loans) == 2
        assert pkg.package_id.startswith("PKG-UPLOAD")
        assert pkg.name == "test tape"

    def test_unit_conversions(self):
        """Rate 7.2 -> 0.072, LTV 85 -> 0.85."""
        rows = [
            [200000, 7.2, 720, 85, 24, 336],
        ]
        tape = _make_excel(rows)
        pkg = parse_loan_tape(tape, "conversions.xlsx")
        loan = pkg.loans[0]

        assert abs(loan.interest_rate - 0.072) < 1e-6
        assert abs(loan.ltv - 0.85) < 1e-6

    def test_original_term_derived(self):
        """original_term = remaining_term + loan_age."""
        rows = [
            [300000, 6.5, 680, 80, 60, 300],
        ]
        tape = _make_excel(rows)
        pkg = parse_loan_tape(tape, "term_test.xlsx")
        loan = pkg.loans[0]

        assert loan.remaining_term == 300
        assert loan.loan_age == 60
        assert loan.original_term == 360  # 300 + 60

    def test_bad_rows_filtered(self):
        """Rows with zero, negative, or extreme balance are dropped."""
        rows = [
            [250000, 7.0, 700, 80, 12, 348],   # good
            [0, 7.0, 700, 80, 12, 348],          # zero balance
            [-50000, 7.0, 700, 80, 12, 348],     # negative
            [15000000, 7.0, 700, 80, 12, 348],   # too large (>10M)
            [100000, 6.5, 650, 90, 24, 336],     # good
        ]
        tape = _make_excel(rows)
        pkg = parse_loan_tape(tape, "filtered.xlsx")

        assert pkg.loan_count == 2
        assert pkg.loans[0].loan_id == "LN-0001"
        assert pkg.loans[1].loan_id == "LN-0002"

    def test_empty_file_error(self):
        """Empty file raises ValueError."""
        buf = io.BytesIO(b"")
        with pytest.raises(ValueError, match="empty"):
            parse_loan_tape(buf, "empty.xlsx")

    def test_no_valid_rows_error(self):
        """File with only bad rows raises ValueError."""
        rows = [
            [0, 7.0, 700, 80, 12, 348],
            [-100, 7.0, 700, 80, 12, 348],
        ]
        tape = _make_excel(rows)
        with pytest.raises(ValueError, match="No valid loan rows"):
            parse_loan_tape(tape, "bad_rows.xlsx")

    def test_loan_ids_sequential(self):
        """Loan IDs are LN-0001, LN-0002, etc."""
        rows = [
            [100000, 7.0, 700, 80, 12, 348],
            [200000, 6.5, 650, 75, 24, 336],
            [300000, 8.0, 600, 90, 6, 354],
        ]
        tape = _make_excel(rows)
        pkg = parse_loan_tape(tape, "ids.xlsx")

        assert [l.loan_id for l in pkg.loans] == ["LN-0001", "LN-0002", "LN-0003"]

    def test_total_upb_calculated(self):
        """Package total_upb is sum of loan balances."""
        rows = [
            [100000, 7.0, 700, 80, 12, 348],
            [200000, 6.5, 650, 75, 24, 336],
        ]
        tape = _make_excel(rows)
        pkg = parse_loan_tape(tape, "upb.xlsx")

        assert abs(pkg.total_upb - 300000) < 1e-2
