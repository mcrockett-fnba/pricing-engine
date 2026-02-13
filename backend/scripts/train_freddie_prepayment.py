#!/usr/bin/env python3
"""Train XGBoost regression model on Freddie Mac data to predict months-to-payoff.

Reads the Freddie Mac CSV, trains an XGBRegressor with early stopping,
evaluates on a held-out test set, and saves the model artifact.

Usage:
    cd backend
    python scripts/train_freddie_prepayment.py

Outputs:
    models/prepayment/freddie_payoff_model.pkl
    models/prepayment/freddie_payoff_metadata.json
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split

# ── Paths ────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_PATH = PROJECT_ROOT / "inprogress" / "Pricing" / "freddieMacWithCollateralAndState.csv"
MODELS_DIR = PROJECT_ROOT / "models" / "prepayment"

FEATURE_COLS = [
    "noteDateYear",
    "creditScore",
    "dti",
    "ltv",
    "interestRate",
    "loanSize",
    "collateralState",
]


def load_and_prepare(csv_path: Path, sample_frac: float = 0.1) -> pd.DataFrame:
    """Load Freddie Mac CSV, sample, filter to payoff events, clean."""
    print(f"Loading {csv_path} ...")
    df = pd.read_csv(csv_path)
    print(f"  Raw rows: {len(df):,}")

    df = df.sample(frac=sample_frac, random_state=42)
    print(f"  After {sample_frac:.0%} sample: {len(df):,}")

    df = df[df["event"] == 1]
    print(f"  After event=1 filter: {len(df):,}")

    df = df.drop(columns=["collateralType", "origCustAmortMonth"], errors="ignore")
    df["collateralState"] = df["collateralState"].astype("category")

    print(f"  Features: {list(df.columns)}")
    print(f"  Target stats — mean: {df['time'].mean():.1f}, "
          f"median: {df['time'].median():.1f}, std: {df['time'].std():.1f}")
    return df


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> xgb.XGBRegressor:
    """Train XGBRegressor with early stopping."""
    model = xgb.XGBRegressor(
        n_estimators=1000,
        learning_rate=0.025,
        max_depth=8,
        max_leaves=63,
        subsample=0.7,
        colsample_bytree=0.8,
        colsample_bylevel=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        gamma=0.1,
        tree_method="hist",
        max_bin=256,
        objective="reg:squarederror",
        random_state=42,
        enable_categorical=True,
        early_stopping_rounds=50,
        n_jobs=-1,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )
    return model


def evaluate(
    model: xgb.XGBRegressor,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict:
    """Evaluate model and return metrics dict."""
    y_pred = model.predict(X_test)
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae = float(mean_absolute_error(y_test, y_pred))
    median_time = float(y_test.median())

    print(f"\n{'=' * 50}")
    print(f"  RMSE:  {rmse:.4f}")
    print(f"  MAE:   {mae:.4f}")
    print(f"  MAE / median time: {mae / median_time:.4f}")
    print(f"  Test samples: {len(y_test):,}")
    print(f"{'=' * 50}\n")

    return {
        "rmse": round(rmse, 4),
        "mae": round(mae, 4),
        "mae_over_median": round(mae / median_time, 4),
        "test_samples": len(y_test),
        "median_time": round(median_time, 1),
    }


def save_model(
    model: xgb.XGBRegressor,
    metrics: dict,
    feature_names: list[str],
) -> Path:
    """Save model artifact and metadata JSON."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODELS_DIR / "freddie_payoff_model.pkl"
    joblib.dump(model, model_path)
    print(f"Saved model to {model_path}")

    metadata = {
        "model_type": "xgboost_regressor",
        "target": "time (months to payoff)",
        "data_source": "freddieMacWithCollateralAndState.csv",
        "sample_fraction": 0.1,
        "event_filter": "event == 1",
        "features": feature_names,
        "best_iteration": model.best_iteration,
        "metrics": metrics,
        "hyperparameters": model.get_params(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "xgboost_version": xgb.__version__,
    }
    meta_path = MODELS_DIR / "freddie_payoff_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, default=str) + "\n")
    print(f"Saved metadata to {meta_path}")

    return model_path


def main() -> None:
    if not DATA_PATH.exists():
        print(f"ERROR: Data file not found at {DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    start = time.time()

    # Load and prep
    df = load_and_prepare(DATA_PATH)

    # Split
    X = df[FEATURE_COLS]
    y = df["time"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.1, random_state=4
    )
    print(f"Train: {len(X_train):,}  Test: {len(X_test):,}")

    # Train
    print("\nTraining XGBRegressor ...")
    model = train_model(X_train, y_train, X_test, y_test)

    # Evaluate
    metrics = evaluate(model, X_test, y_test)

    # Save
    model_path = save_model(model, metrics, FEATURE_COLS)

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s. Model artifact: {model_path}")


if __name__ == "__main__":
    main()
