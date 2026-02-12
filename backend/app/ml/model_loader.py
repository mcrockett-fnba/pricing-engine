"""Model loader — scans MODEL_DIR, reads manifest, loads available models."""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelManifest:
    version: str = "0.0.0"
    generated_at: str = ""
    models: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> "ModelManifest":
        data = json.loads(path.read_text())
        return cls(
            version=data.get("version", "0.0.0"),
            generated_at=data.get("generated_at", ""),
            models=data.get("models", {}),
        )


class ModelRegistry:
    """Singleton that loads manifest, bucket definitions, and survival curves."""

    _instance: "ModelRegistry | None" = None

    def __init__(self) -> None:
        self.manifest: ModelManifest | None = None
        self.bucket_definitions: list[dict[str, Any]] = []
        self.survival_curves: dict[int, list[float]] = {}  # bucket_id -> [prob_m1..m360]
        self.xgb_model: Any = None
        self._loaded = False
        self._model_dir: Path | None = None

    @classmethod
    def get(cls) -> "ModelRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton — mainly for testing."""
        cls._instance = None

    def load(self, model_dir: str | Path | None = None) -> None:
        self._model_dir = Path(model_dir or settings.MODEL_DIR).resolve()
        logger.info("Loading models from %s", self._model_dir)

        if not self._model_dir.is_dir():
            logger.warning("Model directory %s not found — using defaults", self._model_dir)
            self._loaded = True
            return

        self._load_manifest()
        self._load_bucket_definitions()
        self._load_xgb_model()
        self._load_survival_curves()
        self._loaded = True
        logger.info("Model loading complete")

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------
    def _load_manifest(self) -> None:
        manifest_path = self._model_dir / "manifest.json"
        if manifest_path.is_file():
            self.manifest = ModelManifest.from_file(manifest_path)
            logger.info("Loaded manifest v%s", self.manifest.version)
        else:
            logger.warning("No manifest.json found")

    def _load_bucket_definitions(self) -> None:
        defs_path = self._model_dir / "survival" / "bucket_definitions.json"
        if defs_path.is_file():
            data = json.loads(defs_path.read_text())
            self.bucket_definitions = data.get("buckets", [])
            logger.info("Loaded %d bucket definitions", len(self.bucket_definitions))
        else:
            logger.warning("No bucket_definitions.json found")

    def _load_xgb_model(self) -> None:
        model_path = self._model_dir / "survival" / "model.pkl"
        if not model_path.is_file():
            return
        try:
            import joblib
            self.xgb_model = joblib.load(model_path)
            logger.info("Loaded XGBoost model from %s", model_path)
        except ImportError:
            logger.info("joblib not installed — skipping XGBoost model")
        except Exception as e:
            logger.warning("Failed to load XGBoost model: %s", e)

    def _load_survival_curves(self) -> None:
        parquet_path = self._model_dir / "survival" / "survival_curves.parquet"
        if not parquet_path.is_file():
            logger.info("No survival_curves.parquet — will use generated stubs")
            return
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(str(parquet_path))
            bucket_ids = table.column("bucket_id").to_pylist()
            months = table.column("month").to_pylist()
            probs = table.column("survival_prob").to_pylist()

            curves: dict[int, list[tuple[int, float]]] = {}
            for bid, m, p in zip(bucket_ids, months, probs):
                curves.setdefault(bid, []).append((m, p))

            for bid, pairs in curves.items():
                pairs.sort(key=lambda x: x[0])
                self.survival_curves[bid] = [p for _, p in pairs]

            logger.info(
                "Loaded survival curves: %d buckets, %d total rows",
                len(self.survival_curves),
                len(bucket_ids),
            )
        except ImportError:
            logger.info("pyarrow not installed — will use generated stubs")
        except Exception as e:
            logger.warning("Failed to load survival curves: %s", e)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get_status(self) -> dict[str, Any]:
        if not self._loaded:
            return {"status": "not_loaded"}

        if self.manifest:
            models_status = {}
            for name, info in self.manifest.models.items():
                models_status[name] = {
                    "status": info.get("status", "unknown"),
                    "version": self.manifest.version,
                }
            return {
                "status": "loaded",
                "version": self.manifest.version,
                "generated_at": self.manifest.generated_at,
                "models": models_status,
            }

        return {
            "status": "loaded",
            "version": "0.0.0",
            "models": {
                name: {"status": "stub", "version": "0.0.0"}
                for name in ("survival", "deq", "default", "recovery")
            },
        }
