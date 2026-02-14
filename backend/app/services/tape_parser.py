"""Parse an uploaded Excel loan tape into a Package.

Column matching is flexible (partial, case-insensitive) following the same
approach used in scripts/apex2_comparison.py.  Unit conversions handle the
common tape convention of rates and LTVs expressed as percentages.
"""
from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import BinaryIO

from app.models.loan import Loan
from app.models.package import Package

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column matching helpers
# ---------------------------------------------------------------------------
_COLUMN_PATTERNS: dict[str, list[str]] = {
    "balance": ["current balance", "balance", "upb", "unpaid"],
    "rate": ["current rate", "interest rate", "rate", "note rate"],
    "credit": [
        "most recent blended credit",
        "blended recent credit",
        "recent.*credit score",
        "credit score for pricing",
        "credit score",
        "fico",
        "blended credit",
        "credit",
    ],
    "ltv": ["ltv used for pricing", "ltv"],
    "seasoning": ["seasoning", "loan age", "age"],
    "rem_term": ["rem term", "remaining term", "rem_term", "fnba calculated rem"],
    "orig_term": ["original amort", "orig term", "original term"],
    "property_state": ["property state", "state"],
}


def _find_column(columns: list[str], key: str) -> str | None:
    """Find a column name by partial case-insensitive match.

    Patterns are tried in order (most specific first).  A pattern containing
    regex metacharacters (``.*``, ``\\d``, etc.) is treated as a regex;
    otherwise plain substring matching is used.
    """
    patterns = _COLUMN_PATTERNS.get(key, [key])
    col_lower = {c: c.lower().strip() for c in columns}
    for pattern in patterns:
        pat = pattern.lower()
        # Use regex if pattern contains metacharacters, else substring match
        if any(ch in pat for ch in ("*", "+", "?", "\\", "^", "$", "|")):
            try:
                rx = re.compile(pat)
                for orig, low in col_lower.items():
                    if rx.search(low):
                        return orig
            except re.error:
                pass  # fall through to next pattern
        else:
            for orig, low in col_lower.items():
                if pat in low:
                    return orig
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse_loan_tape(file: BinaryIO, filename: str) -> Package:
    """Parse an Excel loan tape into a Package.

    Raises ValueError on invalid / empty data.
    """
    try:
        import openpyxl  # noqa: F401 — ensure dependency available
    except ImportError:
        raise ValueError("openpyxl is required to parse Excel files")

    import pandas as pd

    data = file.read()
    if not data:
        raise ValueError("Uploaded file is empty")

    df = pd.read_excel(BytesIO(data))
    df.columns = [str(c).strip() for c in df.columns]

    if df.empty:
        raise ValueError("Spreadsheet contains no data rows")

    # Map columns
    col_map: dict[str, str | None] = {}
    for key in _COLUMN_PATTERNS:
        col_map[key] = _find_column(list(df.columns), key)

    logger.info("Tape columns: %s", list(df.columns))
    logger.info("Column mapping: %s", col_map)

    balance_col = col_map.get("balance")
    if not balance_col:
        raise ValueError(
            f"Cannot find a balance column. Available columns: {list(df.columns)}"
        )

    # Filter bad rows (missing/zero/extreme balance)
    df = df[
        df[balance_col].notna()
        & (df[balance_col] > 0)
        & (df[balance_col] < 10_000_000)
    ].copy()

    if df.empty:
        raise ValueError("No valid loan rows after filtering")

    # Build loans
    loans: list[Loan] = []
    for idx, row in df.iterrows():
        balance = float(row[balance_col])

        # Rate: convert percent -> decimal if > 1
        rate = _safe_float(row, col_map.get("rate"), 0.07)
        if rate > 1:
            rate = rate / 100.0

        # Credit score
        credit = _safe_int(row, col_map.get("credit"), 700)

        # LTV: convert percent -> decimal if > 1
        ltv = _safe_float(row, col_map.get("ltv"), 0.80)
        if ltv > 1:
            ltv = ltv / 100.0

        # Seasoning / loan age
        loan_age = _safe_int(row, col_map.get("seasoning"), 0)

        # Remaining term
        remaining_term = _safe_int(row, col_map.get("rem_term"), 360)

        # Original term: prefer tape column, else derive from rem + age
        orig_from_tape = _safe_int(row, col_map.get("orig_term"), 0)
        original_term = orig_from_tape if orig_from_tape > 0 else remaining_term + loan_age

        # Property state (2-letter code, optional)
        state_col = col_map.get("property_state")
        property_state = None
        if state_col is not None:
            raw_state = row.get(state_col)
            if isinstance(raw_state, str) and len(raw_state.strip()) == 2:
                property_state = raw_state.strip().upper()

        loan_id = f"LN-{len(loans) + 1:04d}"
        loan_kwargs: dict = dict(
            loan_id=loan_id,
            unpaid_balance=balance,
            interest_rate=rate,
            original_term=original_term,
            remaining_term=remaining_term,
            loan_age=loan_age,
            credit_score=credit if credit >= 300 else None,
            ltv=ltv,
        )
        if property_state:
            loan_kwargs["state"] = property_state
        loans.append(Loan(**loan_kwargs))

    if not loans:
        raise ValueError("No valid loans could be parsed from the file")

    # Derive package name from filename
    name = re.sub(r"\.(xlsx?|csv)$", "", filename, flags=re.IGNORECASE)
    name = name.replace("_", " ").replace("-", " ").strip()
    total_upb = sum(l.unpaid_balance for l in loans)

    return Package(
        package_id=f"PKG-UPLOAD-{len(loans):04d}",
        name=name,
        loan_count=len(loans),
        total_upb=total_upb,
        loans=loans,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _safe_float(row, col: str | None, default: float) -> float:
    if col is None:
        return default
    try:
        val = float(row[col])
        if val != val:  # NaN check
            return default
        return val
    except (ValueError, TypeError, KeyError):
        return default


def _safe_int(row, col: str | None, default: int) -> int:
    if col is None:
        return default
    try:
        val = row[col]
        if val != val:  # NaN check
            return default
        return int(float(val))
    except (ValueError, TypeError, KeyError):
        return default
