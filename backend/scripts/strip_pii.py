"""Strip PII columns from loan tape Excel/CSV files.

Usage:
    python scripts/strip_pii.py input_file.xlsx [output_file.xlsx]
    python scripts/strip_pii.py input_file.csv [output_file.csv]

If no output file is specified, writes to {input}_clean.{ext}
"""
import sys
from pathlib import Path

import pandas as pd

# ── Columns to ALWAYS strip (definite PII) ──────────────────────────────
PII_STRIP = [
    "Borrower First Name",
    "Borrower Last Name",
    "Borrower SSN",
    "Co-borrower First Name",
    "Co-borrower Last Name",
    "Co-borrower SSN",
    "Property Address",
    "Parcel Number/Pin",
]

# ── Columns to strip (internal IDs that could cross-reference to PII) ───
ID_STRIP = [
    "FNBA Account #",
    "Seller Loan Number",
    "Servicer Loan Number",
]

ALL_STRIP = PII_STRIP + ID_STRIP

# ── Fuzzy detection: flag any column whose name contains these tokens ────
PII_TOKENS = [
    "ssn", "social", "borrower first", "borrower last",
    "co-borrower first", "co-borrower last", "coborrower first", "coborrower last",
    "first name", "last name", "full name", "borrower name",
    "parcel number", "parcel num", "pin number",
    "property address", "street address", "mailing address",
    "email", "phone", "cell", "fax",
    "employer", "employer name", "company name",
    "dob", "date of birth", "birth date",
    "driver", "license",
    "tax id", "tin ",
    "account #", "account number", "acct #", "acct num",
    "seller loan", "servicer loan",
]


def find_pii_columns(columns: list[str]) -> dict[str, str]:
    """Return dict of {column_name: reason} for columns flagged as PII."""
    flagged = {}

    for col in columns:
        col_lower = col.strip().lower()

        # Exact match against known PII columns
        for known in ALL_STRIP:
            if col_lower == known.lower():
                reason = "PII (name/SSN)" if known in PII_STRIP else "Cross-reference ID"
                flagged[col] = reason
                break
        else:
            # Fuzzy token match
            for token in PII_TOKENS:
                if token in col_lower:
                    flagged[col] = f"Fuzzy match on '{token}'"
                    break

    return flagged


def strip_pii(input_path: str, output_path: str | None = None) -> None:
    inp = Path(input_path)
    if not inp.exists():
        print(f"ERROR: File not found: {inp}")
        sys.exit(1)

    # Read file
    if inp.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(inp)
    elif inp.suffix.lower() == ".csv":
        df = pd.read_csv(inp)
    else:
        print(f"ERROR: Unsupported file type: {inp.suffix}")
        sys.exit(1)

    print(f"Loaded {len(df)} rows, {len(df.columns)} columns from {inp.name}")
    print()

    # Detect PII columns
    flagged = find_pii_columns(list(df.columns))

    if not flagged:
        print("No PII columns detected.")
    else:
        print(f"{'='*60}")
        print(f" FLAGGED PII COLUMNS ({len(flagged)})")
        print(f"{'='*60}")
        for col, reason in flagged.items():
            sample = df[col].dropna().head(3).tolist()
            sample_str = ", ".join(str(s)[:30] for s in sample)
            print(f"  STRIP: {col}")
            print(f"         Reason: {reason}")
            print(f"         Sample: [{sample_str}]")
            print()

    # Strip flagged columns
    cols_to_drop = [c for c in flagged if c in df.columns]
    df_clean = df.drop(columns=cols_to_drop)

    # Determine output path
    if output_path is None:
        out = inp.parent / f"{inp.stem}_clean{inp.suffix}"
    else:
        out = Path(output_path)

    # Write output
    if out.suffix.lower() in (".xlsx", ".xls"):
        df_clean.to_excel(out, index=False)
    else:
        df_clean.to_csv(out, index=False)

    print(f"{'='*60}")
    print(f" RESULT")
    print(f"{'='*60}")
    print(f"  Stripped: {len(cols_to_drop)} columns")
    print(f"  Remaining: {len(df_clean.columns)} columns")
    print(f"  Output: {out}")
    print()

    # Print remaining columns for review
    print(f"{'='*60}")
    print(f" REMAINING COLUMNS ({len(df_clean.columns)})")
    print(f"{'='*60}")
    for i, col in enumerate(df_clean.columns, 1):
        print(f"  {i:3d}. {col}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    strip_pii(input_file, output_file)
