"""Tests for model_loader — ModelRegistry, ModelManifest."""
import json

import pytest

from app.ml.model_loader import ModelManifest, ModelRegistry


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset singleton before each test."""
    ModelRegistry.reset()
    yield
    ModelRegistry.reset()


def test_registry_handles_missing_dir(tmp_path):
    """Registry loads cleanly when model dir doesn't exist."""
    reg = ModelRegistry.get()
    reg.load(tmp_path / "nonexistent")
    assert reg.is_loaded
    assert reg.manifest is None
    assert reg.bucket_definitions == []
    assert reg.survival_curves == {}


def test_registry_loads_manifest(tmp_path):
    """Registry parses manifest.json from a temp directory."""
    manifest = {
        "version": "0.2.0",
        "generated_at": "2025-01-01T00:00:00Z",
        "models": {
            "survival": {"status": "stub", "path": "survival/"},
            "deq": {"status": "stub", "path": "deq/"},
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    reg = ModelRegistry.get()
    reg.load(tmp_path)

    assert reg.is_loaded
    assert reg.manifest is not None
    assert reg.manifest.version == "0.2.0"
    assert "survival" in reg.manifest.models


def test_registry_loads_bucket_definitions(tmp_path):
    """Registry parses bucket_definitions.json."""
    survival_dir = tmp_path / "survival"
    survival_dir.mkdir()
    defs = {
        "buckets": [
            {"bucket_id": 1, "label": "A", "rules": []},
            {"bucket_id": 2, "label": "B", "rules": []},
        ]
    }
    (survival_dir / "bucket_definitions.json").write_text(json.dumps(defs))
    reg = ModelRegistry.get()
    reg.load(tmp_path)

    assert len(reg.bucket_definitions) == 2
    assert reg.bucket_definitions[0]["label"] == "A"


def test_get_status_not_loaded():
    """Status is not_loaded before load() is called."""
    reg = ModelRegistry.get()
    status = reg.get_status()
    assert status["status"] == "not_loaded"


def test_get_status_loaded_no_manifest(tmp_path):
    """Status shows default stubs when no manifest file exists."""
    reg = ModelRegistry.get()
    reg.load(tmp_path)
    status = reg.get_status()
    assert status["status"] == "loaded"
    assert "models" in status
    assert status["models"]["survival"]["status"] == "stub"


def test_get_status_loaded_with_manifest(tmp_path):
    """Status reflects manifest data."""
    manifest = {
        "version": "1.0.0",
        "generated_at": "2025-06-01T12:00:00Z",
        "models": {
            "survival": {"status": "trained", "path": "survival/"},
            "deq": {"status": "stub", "path": "deq/"},
            "default": {"status": "stub", "path": "default/"},
            "recovery": {"status": "stub", "path": "recovery/"},
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    reg = ModelRegistry.get()
    reg.load(tmp_path)
    status = reg.get_status()

    assert status["status"] == "loaded"
    assert status["version"] == "1.0.0"
    assert status["models"]["survival"]["status"] == "trained"
    assert status["models"]["deq"]["status"] == "stub"
