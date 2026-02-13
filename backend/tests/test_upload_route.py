"""Tests for the POST /packages/upload endpoint."""
import io
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app

client = TestClient(app)


def _make_excel_bytes(rows, columns=None):
    """Create an in-memory Excel file and return bytes."""
    wb = Workbook()
    ws = wb.active
    if columns is None:
        columns = [
            "Current Balance", "Current Rate",
            "Most Recent Blended Credit Score for Pricing",
            "LTV used for Pricing (%)", "Seasoning", "FNBA Calculated Rem Term",
        ]
    ws.append(columns)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestUploadRoute:
    def test_valid_upload(self):
        """POST valid Excel -> 200 with correct Package structure."""
        data = _make_excel_bytes([
            [250000, 7.2, 660, 85, 80, 280],
            [150000, 6.8, 700, 75, 60, 300],
        ])
        response = client.post(
            "/api/packages/upload",
            files={"file": ("test_tape.xlsx", io.BytesIO(data), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 200
        pkg = response.json()
        assert pkg["loan_count"] == 2
        assert len(pkg["loans"]) == 2
        assert pkg["package_id"].startswith("PKG-UPLOAD")

    def test_non_excel_rejected(self):
        """POST non-Excel file -> 400."""
        response = client.post(
            "/api/packages/upload",
            files={"file": ("data.csv", io.BytesIO(b"a,b,c\n1,2,3"), "text/csv")},
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_conversions_in_upload(self):
        """Verify rate and LTV are converted correctly through the endpoint."""
        data = _make_excel_bytes([
            [200000, 7.2, 720, 85, 24, 336],
        ])
        response = client.post(
            "/api/packages/upload",
            files={"file": ("tape.xlsx", io.BytesIO(data), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 200
        loan = response.json()["loans"][0]
        assert abs(loan["interest_rate"] - 0.072) < 1e-6
        assert abs(loan["ltv"] - 0.85) < 1e-6
        assert loan["original_term"] == 360  # 336 + 24
