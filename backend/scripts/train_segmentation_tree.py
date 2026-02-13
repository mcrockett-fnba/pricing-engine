#!/usr/bin/env python3
"""Train a segmentation decision tree on blended FNBA + Freddie Mac data.

Produces:
  models/segmentation/segmentation_tree.pkl
  models/segmentation/tree_structure.json
  models/segmentation/segmentation_metadata.json
  models/segmentation/leaves/leaf_{id}_loans.parquet
  models/survival/survival_curves.parquet  (overwritten with leaf-keyed curves)
  models/manifest.json  (updated with segmentation entry)

Usage:
  cd backend
  source .venv/bin/activate
  python scripts/train_segmentation_tree.py
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time as _time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeRegressor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _json_default(obj):
    """Handle numpy types in JSON serialization."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "inprogress" / "Pricing"
MODEL_DIR = PROJECT_ROOT / "models"
SEG_DIR = MODEL_DIR / "segmentation"
LEAF_DIR = SEG_DIR / "leaves"
SURVIVAL_DIR = MODEL_DIR / "survival"

FNBA_PATH = DATA_DIR / "fnbaYear.xlsx"
FREDDIE_PATH = DATA_DIR / "freddieMacWithCollateralAndState.csv"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FREDDIE_SAMPLE_FRAC = 0.10
MAX_LEAF_NODES = 75
MIN_SAMPLES_LEAF = 10_000
RANDOM_STATE = 42
KM_MAX_MONTH = 360
KM_EMA_SPAN = 6  # months for exponential moving average smoothing

FEATURE_COLS = [
    "noteDateYear",
    "creditScore",
    "dti",
    "ltv",
    "interestRate",
    "loanSize",
    "stateGroup",
    "ITIN",
    "origCustAmortMonth",
]
TARGET_COL = "time"


# ===================================================================
# Step 1: Load and blend data
# ===================================================================
def load_fnba(path: Path) -> pd.DataFrame:
    """Load ALL FNBA loans (both event==0 and event==1)."""
    logger.info("Loading FNBA data from %s", path)
    df = pd.read_excel(path)
    df["source"] = "fnba"
    df["source_row_id"] = df.index.values
    logger.info(
        "FNBA: %d loans (%d payoffs, %d censored)",
        len(df),
        (df["event"] == 1).sum(),
        (df["event"] == 0).sum(),
    )
    return df


def load_freddie(path: Path, sample_frac: float) -> pd.DataFrame:
    """Load Freddie Mac CSV with chunked 10% sampling to manage memory."""
    logger.info("Loading Freddie Mac data from %s (%.0f%% sample)", path, sample_frac * 100)
    rng = np.random.RandomState(RANDOM_STATE)
    chunks = []
    chunk_size = 500_000
    total_rows = 0

    for chunk in pd.read_csv(path, chunksize=chunk_size, dtype={"collateralState": "category"}):
        total_rows += len(chunk)
        sampled = chunk.sample(frac=sample_frac, random_state=rng)
        chunks.append(sampled)
        if total_rows % 5_000_000 == 0:
            logger.info("  ... read %dM rows so far", total_rows // 1_000_000)

    df = pd.concat(chunks, ignore_index=True)
    df["source"] = "freddie"
    df["source_row_id"] = df.index.values
    df["ITIN"] = 0  # Freddie has no ITIN loans

    # Drop collateralType if present (not needed)
    if "collateralType" in df.columns:
        df.drop(columns=["collateralType"], inplace=True)

    logger.info(
        "Freddie: %d sampled loans from %d total (%d payoffs, %d censored)",
        len(df),
        total_rows,
        (df["event"] == 1).sum(),
        (df["event"] == 0).sum(),
    )
    return df


def blend_data(fnba: pd.DataFrame, freddie: pd.DataFrame) -> pd.DataFrame:
    """Combine FNBA and Freddie into a single training set."""
    # Ensure consistent columns
    common_cols = [
        "time", "event", "noteDateYear", "creditScore", "dti", "ltv",
        "interestRate", "loanSize", "origCustAmortMonth", "collateralState",
        "ITIN", "source", "source_row_id",
    ]
    fnba_aligned = fnba[common_cols].copy()
    freddie_aligned = freddie[common_cols].copy()

    df = pd.concat([fnba_aligned, freddie_aligned], ignore_index=True)

    # Fill missing values
    df["dti"] = df["dti"].fillna(36.0)
    df["ltv"] = df["ltv"].fillna(80.0)
    df["ITIN"] = df["ITIN"].fillna(0).astype(int)
    df["origCustAmortMonth"] = df["origCustAmortMonth"].fillna(360).astype(int)
    df["creditScore"] = df["creditScore"].fillna(df["creditScore"].median())

    # Drop rows with missing target or key features
    before = len(df)
    df = df.dropna(subset=["time", "creditScore", "interestRate", "loanSize"])
    if len(df) < before:
        logger.info("Dropped %d rows with missing target/key features", before - len(df))

    logger.info("Blended dataset: %d total loans", len(df))
    return df


# ===================================================================
# Step 2: Pre-bin collateralState
# ===================================================================
def bin_states(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Group states into ~6 bins by median payoff time among event==1 loans."""
    payoffs = df[df["event"] == 1]

    state_medians = payoffs.groupby("collateralState")["time"].median()

    # Create 6 bins using quantiles of state medians
    n_bins = 6
    bins = pd.qcut(state_medians, q=n_bins, labels=False, duplicates="drop")

    # Build mapping: state -> bin number (ensure plain int, not numpy int64)
    state_to_group: dict[str, int] = {}
    for state, group in bins.items():
        state_to_group[str(state)] = int(group)  # int() strips numpy wrapper

    # Assign to dataframe; unknown states get median bin
    median_bin = n_bins // 2
    df["stateGroup"] = (
        df["collateralState"]
        .astype(str)
        .map(state_to_group)
        .fillna(median_bin)
        .astype(int)
    )

    logger.info(
        "State binning: %d states → %d groups (group sizes: %s)",
        len(state_to_group),
        len(set(state_to_group.values())),
        dict(df["stateGroup"].value_counts().sort_index()),
    )
    return df, state_to_group


# ===================================================================
# Step 3: Train tree
# ===================================================================
def train_tree(df: pd.DataFrame) -> DecisionTreeRegressor:
    """Train DecisionTreeRegressor on all loans (censored get observation time)."""
    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    tree = DecisionTreeRegressor(
        max_leaf_nodes=MAX_LEAF_NODES,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        random_state=RANDOM_STATE,
    )
    tree.fit(X, y)

    n_leaves = tree.get_n_leaves()
    logger.info(
        "Tree trained: %d leaves, max_depth=%d, features=%s",
        n_leaves,
        tree.get_depth(),
        FEATURE_COLS,
    )
    return tree


# ===================================================================
# Step 4: Extract rules per leaf
# ===================================================================
def extract_tree_structure(
    tree: DecisionTreeRegressor,
    feature_names: list[str],
) -> dict:
    """Walk tree structure, extract rules per leaf, build nested + flat representations."""
    t = tree.tree_
    n_nodes = t.node_count

    # Map sklearn node_id to sequential leaf_id
    node_to_leaf: dict[int, int] = {}
    leaf_id_counter = 0
    for node_id in range(n_nodes):
        if t.children_left[node_id] == t.children_right[node_id]:  # leaf
            leaf_id_counter += 1
            node_to_leaf[node_id] = leaf_id_counter

    def _build_node(node_id: int, rules_so_far: list[dict]) -> dict:
        """Recursively build tree node dict."""
        if t.children_left[node_id] == t.children_right[node_id]:
            # Leaf node
            leaf_id = node_to_leaf[node_id]
            return {
                "type": "leaf",
                "node_id": int(node_id),
                "leaf_id": leaf_id,
                "samples": int(t.n_node_samples[node_id]),
                "mean_time": round(float(t.value[node_id][0][0]), 2),
                "rules": list(rules_so_far),
            }
        else:
            # Internal node
            feat_idx = int(t.feature[node_id])
            feat_name = feature_names[feat_idx]
            threshold = float(t.threshold[node_id])

            left_rules = rules_so_far + [
                {"feature": feat_name, "operator": "<=", "threshold": round(threshold, 4)}
            ]
            right_rules = rules_so_far + [
                {"feature": feat_name, "operator": ">", "threshold": round(threshold, 4)}
            ]

            return {
                "type": "internal",
                "node_id": int(node_id),
                "feature": feat_name,
                "threshold": round(threshold, 4),
                "samples": int(t.n_node_samples[node_id]),
                "left": _build_node(int(t.children_left[node_id]), left_rules),
                "right": _build_node(int(t.children_right[node_id]), right_rules),
            }

    nested = _build_node(0, [])

    # Flatten leaves
    flat_leaves = []

    def _collect_leaves(node: dict):
        if node["type"] == "leaf":
            # Generate human-readable label from top 2-3 splits
            label_parts = []
            for rule in node["rules"][:3]:
                feat = rule["feature"]
                op = rule["operator"]
                val = rule["threshold"]
                # Shorten feature names
                short = {
                    "noteDateYear": "year",
                    "creditScore": "credit",
                    "interestRate": "rate",
                    "loanSize": "size",
                    "stateGroup": "region",
                    "origCustAmortMonth": "term",
                }.get(feat, feat)
                label_parts.append(f"{short}{op}{val}")
            node["label"] = " & ".join(label_parts) if label_parts else f"leaf_{node['leaf_id']}"
            flat_leaves.append(node)
        else:
            _collect_leaves(node["left"])
            _collect_leaves(node["right"])

    _collect_leaves(nested)

    logger.info("Extracted %d leaves from tree", len(flat_leaves))

    return {
        "nested_tree": nested,
        "leaves": flat_leaves,
        "node_to_leaf": {str(k): v for k, v in node_to_leaf.items()},
        "feature_names": feature_names,
    }


# ===================================================================
# Step 5: Kaplan-Meier survival curves per leaf
# ===================================================================
def kaplan_meier(times: np.ndarray, events: np.ndarray, max_month: int) -> np.ndarray:
    """Compute KM survival curve for months 1..max_month.

    Returns array of length max_month with S(t) values.
    Handles censored observations correctly.
    """
    n = len(times)
    if n == 0:
        return np.ones(max_month)

    # Build event table: at each time, count deaths and censorings
    time_events: dict[int, list[int, int]] = defaultdict(lambda: [0, 0])
    for t, e in zip(times, events):
        t_int = max(1, int(t))
        if e == 1:
            time_events[t_int][0] += 1  # deaths
        else:
            time_events[t_int][1] += 1  # censorings

    sorted_times = sorted(time_events.keys())

    # KM estimator
    survival = np.ones(max_month + 1)  # S(0) = 1.0
    at_risk = n
    s = 1.0

    time_idx = 0
    for month in range(1, max_month + 1):
        # Process events at this month
        if time_idx < len(sorted_times) and sorted_times[time_idx] == month:
            t = sorted_times[time_idx]
            deaths = time_events[t][0]
            censored = time_events[t][1]

            if at_risk > 0 and deaths > 0:
                s *= (1.0 - deaths / at_risk)

            at_risk -= (deaths + censored)
            at_risk = max(at_risk, 0)
            time_idx += 1

        survival[month] = s

    return survival[1:]  # months 1..max_month


def compute_leaf_survival_curves(
    df: pd.DataFrame,
    leaf_assignments: np.ndarray,
    node_to_leaf: dict[int, int],
    max_month: int = KM_MAX_MONTH,
    ema_span: int = KM_EMA_SPAN,
) -> dict[int, np.ndarray]:
    """Compute KM survival curve for each leaf, smooth with EMA."""
    curves: dict[int, np.ndarray] = {}

    for node_id, leaf_id in node_to_leaf.items():
        mask = leaf_assignments == int(node_id)
        leaf_df = df[mask]

        if len(leaf_df) == 0:
            curves[leaf_id] = np.ones(max_month)
            continue

        raw = kaplan_meier(
            leaf_df["time"].values,
            leaf_df["event"].values,
            max_month,
        )

        # Smooth with EMA (copy to make writable)
        smoothed = pd.Series(raw).ewm(span=ema_span, adjust=False).mean().values.copy()

        # Ensure monotonically non-increasing
        for i in range(1, len(smoothed)):
            if smoothed[i] > smoothed[i - 1]:
                smoothed[i] = smoothed[i - 1]

        # Extrapolate sparse tail via exponential decay if curve is flat at end
        # Find last month with meaningful data (at least some events/censorings)
        leaf_max_time = int(leaf_df["time"].max())
        if leaf_max_time < max_month and smoothed[leaf_max_time - 1] > 0.01:
            # Fit exponential decay from the last observed point
            s_last = smoothed[leaf_max_time - 1]
            if leaf_max_time > 1 and smoothed[0] > 0:
                # Estimate monthly hazard from overall curve
                monthly_hazard = -math.log(max(s_last, 0.001)) / leaf_max_time
                for m in range(leaf_max_time, max_month):
                    smoothed[m] = s_last * math.exp(-monthly_hazard * (m - leaf_max_time + 1))
                    smoothed[m] = max(smoothed[m], 0.0)

        curves[leaf_id] = smoothed

    logger.info("Computed KM survival curves for %d leaves", len(curves))
    return curves


# ===================================================================
# Step 6: Store training loan membership per leaf
# ===================================================================
def store_leaf_loans(
    df: pd.DataFrame,
    leaf_assignments: np.ndarray,
    node_to_leaf: dict[int, int],
    out_dir: Path,
):
    """Save per-leaf parquet files with training loan details."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Add leaf_id to df
    leaf_ids = np.zeros(len(df), dtype=int)
    for node_id, leaf_id in node_to_leaf.items():
        mask = leaf_assignments == int(node_id)
        leaf_ids[mask] = leaf_id
    df = df.copy()
    df["leaf_id"] = leaf_ids

    keep_cols = [
        "source", "source_row_id", "time", "event",
        "creditScore", "interestRate", "loanSize", "ltv",
        "collateralState", "ITIN", "noteDateYear", "dti",
        "origCustAmortMonth", "leaf_id",
    ]
    available = [c for c in keep_cols if c in df.columns]

    for leaf_id in sorted(node_to_leaf.values()):
        leaf_df = df[df["leaf_id"] == leaf_id][available]
        path = out_dir / f"leaf_{leaf_id}_loans.parquet"
        leaf_df.to_parquet(path, index=False)

    logger.info("Saved %d leaf loan files to %s", len(node_to_leaf), out_dir)


# ===================================================================
# Step 7: Save all artifacts
# ===================================================================
def save_survival_parquet(curves: dict[int, np.ndarray], out_path: Path):
    """Save survival curves as parquet: bucket_id, month, survival_prob."""
    rows = []
    for leaf_id, curve in sorted(curves.items()):
        for month_idx, prob in enumerate(curve):
            rows.append({
                "bucket_id": leaf_id,
                "month": month_idx + 1,
                "survival_prob": round(float(prob), 6),
            })
    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Saved survival curves: %d rows to %s", len(df), out_path)


def update_manifest(manifest_path: Path):
    """Add segmentation entry to manifest.json."""
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"version": "0.2.0", "models": {}}

    manifest["models"]["segmentation"] = {
        "status": "real",
        "path": "segmentation/",
        "description": (
            "Decision tree segmentation with Kaplan-Meier survival curves. "
            "Trained on blended FNBA internal + Freddie Mac data."
        ),
    }

    # Also update survival to real since we now have KM-based curves
    if "survival" in manifest["models"]:
        manifest["models"]["survival"]["status"] = "real"
        manifest["models"]["survival"]["description"] = (
            "Per-leaf Kaplan-Meier survival curves from segmentation tree. "
            "Trained on blended FNBA + Freddie Mac data (all loans incl. censored)."
        )

    manifest["version"] = "0.2.0"
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    logger.info("Updated manifest at %s", manifest_path)


def save_metadata(
    seg_dir: Path,
    n_fnba: int,
    n_freddie: int,
    n_leaves: int,
    tree_depth: int,
    state_mapping: dict[str, int],
):
    """Save training metadata."""
    meta = {
        "model_type": "decision_tree_regressor",
        "target": "time (months to payoff / censoring)",
        "data_sources": {
            "fnba": {"path": str(FNBA_PATH.name), "n_loans": n_fnba},
            "freddie": {
                "path": str(FREDDIE_PATH.name),
                "sample_fraction": FREDDIE_SAMPLE_FRAC,
                "n_loans": n_freddie,
            },
        },
        "includes_censored": True,
        "features": FEATURE_COLS,
        "tree_config": {
            "max_leaf_nodes": MAX_LEAF_NODES,
            "min_samples_leaf": MIN_SAMPLES_LEAF,
            "random_state": RANDOM_STATE,
        },
        "results": {
            "n_leaves": n_leaves,
            "tree_depth": tree_depth,
        },
        "km_config": {
            "max_month": KM_MAX_MONTH,
            "ema_span": KM_EMA_SPAN,
        },
        "state_group_mapping": {k: int(v) for k, v in state_mapping.items()},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": __import__("sklearn").__version__,
    }
    path = seg_dir / "segmentation_metadata.json"
    path.write_text(json.dumps(meta, indent=2, default=_json_default) + "\n")
    logger.info("Saved metadata to %s", path)


# ===================================================================
# Main
# ===================================================================
def main():
    start = _time.time()

    # Verify data files exist
    for p in [FNBA_PATH, FREDDIE_PATH]:
        if not p.is_file():
            logger.error("Data file not found: %s", p)
            sys.exit(1)

    # Create output directories
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    LEAF_DIR.mkdir(parents=True, exist_ok=True)
    SURVIVAL_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Load and blend
    fnba = load_fnba(FNBA_PATH)
    freddie = load_freddie(FREDDIE_PATH, FREDDIE_SAMPLE_FRAC)
    df = blend_data(fnba, freddie)

    n_fnba = len(fnba)
    n_freddie = len(freddie)
    del fnba, freddie  # free memory

    # Step 2: Pre-bin states
    df, state_mapping = bin_states(df)

    # Step 3: Train tree
    tree = train_tree(df)

    # Get leaf assignments for all loans
    leaf_assignments = tree.apply(df[FEATURE_COLS].values)

    # Build node_to_leaf mapping
    node_to_leaf: dict[int, int] = {}
    leaf_id_counter = 0
    t = tree.tree_
    for node_id in range(t.node_count):
        if t.children_left[node_id] == t.children_right[node_id]:
            leaf_id_counter += 1
            node_to_leaf[node_id] = leaf_id_counter

    # Step 4: Extract rules
    tree_structure = extract_tree_structure(tree, FEATURE_COLS)
    tree_structure["state_group_mapping"] = state_mapping

    # Add per-leaf source breakdown to flat leaves
    for leaf in tree_structure["leaves"]:
        node_id = leaf["node_id"]
        mask = leaf_assignments == node_id
        leaf_df = df[mask]
        leaf["n_fnba"] = int((leaf_df["source"] == "fnba").sum())
        leaf["n_freddie"] = int((leaf_df["source"] == "freddie").sum())
        leaf["n_payoffs"] = int((leaf_df["event"] == 1).sum())
        leaf["n_censored"] = int((leaf_df["event"] == 0).sum())
        leaf["median_time"] = round(float(leaf_df["time"].median()), 1)

    # Step 5: KM survival curves
    curves = compute_leaf_survival_curves(df, leaf_assignments, node_to_leaf)

    # Step 6: Store training loan membership
    store_leaf_loans(df, leaf_assignments, node_to_leaf, LEAF_DIR)

    # Step 7: Save artifacts
    # Tree pickle
    tree_path = SEG_DIR / "segmentation_tree.pkl"
    joblib.dump(tree, tree_path)
    logger.info("Saved tree to %s", tree_path)

    # Tree structure JSON
    structure_path = SEG_DIR / "tree_structure.json"
    structure_path.write_text(json.dumps(tree_structure, indent=2, default=str) + "\n")
    logger.info("Saved tree structure to %s", structure_path)

    # Survival curves parquet
    save_survival_parquet(curves, SURVIVAL_DIR / "survival_curves.parquet")

    # Metadata
    save_metadata(
        SEG_DIR,
        n_fnba=n_fnba,
        n_freddie=n_freddie,
        n_leaves=tree.get_n_leaves(),
        tree_depth=tree.get_depth(),
        state_mapping=state_mapping,
    )

    # Manifest
    update_manifest(MODEL_DIR / "manifest.json")

    elapsed = _time.time() - start
    logger.info(
        "Done in %.1fs. %d leaves trained on %d loans (%d FNBA + %d Freddie)",
        elapsed,
        tree.get_n_leaves(),
        len(df),
        n_fnba,
        n_freddie,
    )

    # Print summary
    print("\n" + "=" * 60)
    print(f"Segmentation Tree Summary")
    print(f"  Leaves:    {tree.get_n_leaves()}")
    print(f"  Depth:     {tree.get_depth()}")
    print(f"  FNBA:      {n_fnba:,} loans")
    print(f"  Freddie:   {n_freddie:,} loans")
    print(f"  Total:     {len(df):,} loans")
    print(f"\nLeaf breakdown:")
    for leaf in sorted(tree_structure["leaves"], key=lambda x: x["leaf_id"]):
        print(
            f"  Leaf {leaf['leaf_id']:3d}: "
            f"{leaf['samples']:8,} loans "
            f"(FNBA:{leaf['n_fnba']:6,} Freddie:{leaf['n_freddie']:7,}) "
            f"mean={leaf['mean_time']:5.1f}mo "
            f"median={leaf['median_time']:5.1f}mo  "
            f"{leaf['label']}"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
