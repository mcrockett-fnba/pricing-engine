#!/usr/bin/env python3
"""Generate stub model artifacts in the project-root models/ directory.

Produces:
  models/manifest.json
  models/survival/bucket_definitions.json
  models/survival/survival_curves.parquet
  models/survival/metadata.json
  models/deq/metadata.json
  models/default/metadata.json
  models/recovery/metadata.json

Usage:
  cd backend && python scripts/generate_stub_models.py
"""
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# -------------------------------------------------------------------
# Resolve models/ at project root (one level above backend/)
# -------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
MODELS_DIR = PROJECT_ROOT / "models"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  wrote {path.relative_to(PROJECT_ROOT)}")


def generate_manifest() -> None:
    manifest = {
        "version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": {
            "survival": {"status": "stub", "path": "survival/"},
            "deq": {"status": "stub", "path": "deq/"},
            "default": {"status": "stub", "path": "default/"},
            "recovery": {"status": "stub", "path": "recovery/"},
            "prepayment": {"status": "stub", "path": "prepayment/"},
            "apex2": {"status": "real", "path": "apex2/"},
        },
    }
    _write_json(MODELS_DIR / "manifest.json", manifest)


def generate_bucket_definitions() -> list[dict]:
    """5 risk buckets based on credit_score and LTV."""
    buckets = [
        {
            "bucket_id": 1,
            "label": "Prime",
            "rules": [
                {"feature": "credit_score", "operator": ">=", "value": 740},
                {"feature": "ltv", "operator": "<", "value": 0.70},
            ],
        },
        {
            "bucket_id": 2,
            "label": "Near-Prime",
            "rules": [
                {"feature": "credit_score", "operator": ">=", "value": 700},
                {"feature": "ltv", "operator": "<", "value": 0.80},
            ],
        },
        {
            "bucket_id": 3,
            "label": "Non-Prime",
            "rules": [
                {"feature": "credit_score", "operator": ">=", "value": 660},
                {"feature": "ltv", "operator": "<", "value": 0.90},
            ],
        },
        {
            "bucket_id": 4,
            "label": "Sub-Prime",
            "rules": [
                {"feature": "credit_score", "operator": ">=", "value": 600},
                {"feature": "ltv", "operator": "<", "value": 1.00},
            ],
        },
        {
            "bucket_id": 5,
            "label": "Deep Sub-Prime",
            "rules": [],  # catch-all
        },
    ]
    _write_json(MODELS_DIR / "survival" / "bucket_definitions.json", {"buckets": buckets})
    return buckets


def generate_survival_curves(buckets: list[dict]) -> None:
    """Create survival_curves.parquet: 5 buckets x 360 months = 1800 rows."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print("  WARNING: pyarrow not installed — writing CSV fallback instead")
        _generate_survival_curves_csv(buckets)
        return

    # Annual hazard rates per bucket (higher = riskier)
    hazard_rates = {1: 0.005, 2: 0.010, 3: 0.020, 4: 0.040, 5: 0.070}
    n_months = 360

    bucket_ids = []
    months = []
    survival_probs = []

    for b in buckets:
        bid = b["bucket_id"]
        annual_hazard = hazard_rates[bid]
        monthly_hazard = annual_hazard / 12
        for m in range(1, n_months + 1):
            bucket_ids.append(bid)
            months.append(m)
            survival_probs.append(math.exp(-monthly_hazard * m))

    table = pa.table(
        {
            "bucket_id": pa.array(bucket_ids, type=pa.int32()),
            "month": pa.array(months, type=pa.int32()),
            "survival_prob": pa.array(survival_probs, type=pa.float64()),
        }
    )
    out = MODELS_DIR / "survival" / "survival_curves.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, str(out))
    print(f"  wrote {out.relative_to(PROJECT_ROOT)}  ({len(bucket_ids)} rows)")


def _generate_survival_curves_csv(buckets: list[dict]) -> None:
    """Fallback if pyarrow is not available."""
    import csv

    hazard_rates = {1: 0.005, 2: 0.010, 3: 0.020, 4: 0.040, 5: 0.070}
    n_months = 360
    out = MODELS_DIR / "survival" / "survival_curves.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["bucket_id", "month", "survival_prob"])
        for b in buckets:
            bid = b["bucket_id"]
            annual_hazard = hazard_rates[bid]
            monthly_hazard = annual_hazard / 12
            for m in range(1, n_months + 1):
                writer.writerow([bid, m, math.exp(-monthly_hazard * m)])
    print(f"  wrote {out.relative_to(PROJECT_ROOT)} (CSV fallback)")


def generate_apex2_tables() -> None:
    """Write APEX2 dimensional lookup tables as JSON files."""
    apex2_dir = MODELS_DIR / "apex2"
    _write_json(apex2_dir / "credit_rates.json", {
        "<576": 1.3583, "576-600": 1.5713, "601-625": 1.8124,
        "626-650": 2.1814, "651-675": 2.4668, "676-700": 2.7220,
        "701-725": 2.7022, "726-750": 2.7284, ">=751": 2.7159,
    })
    _write_json(apex2_dir / "rate_delta_rates.json", {
        "<=-3%": 1.4307, "-2 to -2.99%": 1.2733, "-1 to -1.99%": 1.7116,
        "-0.99 to 0.99%": 1.8363, "1 to 1.99%": 2.0108,
        "2 to 2.99%": 2.4278, ">=3%": 2.3215,
    })
    _write_json(apex2_dir / "ltv_rates.json", {
        "< 75%": 2.2420, "75% - 79.99%": 2.5268,
        "80% - 84.99%": 2.5173, "85% - 89.99%": 2.0415,
        ">= 90%": 1.6916,
    })
    _write_json(apex2_dir / "loan_size_rates.json", {
        "$0 - $49,999": 1.3169, "$50,000 - $99,999": 1.6846,
        "$100,000 - $149,999": 2.2964, "$150,000 - $199,999": 2.6937,
        "$200,000 - $249,999": 2.8286, "$250,000 - $499,999": 2.9982,
        "$500,000 - $999,999": 3.3578, "$1,000,000+": 3.3335,
    })
    _write_json(apex2_dir / "metadata.json", {
        "model_type": "apex2",
        "version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": "APEX2 dimensional prepayment lookup tables (Not-ITIN). "
                       "Four dimensions: credit score, rate delta, LTV, and loan size. "
                       "Production multipliers from APEX2 system.",
    })


def generate_metadata() -> None:
    """Create metadata.json files for each stub model sub-directory."""
    for name in ("survival", "deq", "default", "recovery", "prepayment"):
        meta = {
            "model_type": name,
            "version": "0.1.0-stub",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "description": f"Stub {name} model — formula-based, no trained artifact",
        }
        _write_json(MODELS_DIR / name / "metadata.json", meta)


def main() -> None:
    print(f"Generating stub models in {MODELS_DIR}")
    generate_manifest()
    buckets = generate_bucket_definitions()
    generate_survival_curves(buckets)
    generate_metadata()
    generate_apex2_tables()
    print("Done.")


if __name__ == "__main__":
    main()
