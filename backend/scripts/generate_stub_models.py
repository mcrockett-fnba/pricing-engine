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


def generate_metadata() -> None:
    """Create metadata.json files for each model sub-directory."""
    for name in ("survival", "deq", "default", "recovery"):
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
    print("Done.")


if __name__ == "__main__":
    main()
