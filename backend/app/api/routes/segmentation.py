"""Segmentation tree API — tree visualization, leaf details, training loan drill-through."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.ml.model_loader import ModelRegistry

router = APIRouter(tags=["segmentation"])


def _require_tree() -> ModelRegistry:
    """Return registry or 404 if segmentation tree not loaded."""
    registry = ModelRegistry.get()
    if not registry.segmentation_tree or not registry.tree_structure:
        raise HTTPException(
            status_code=404,
            detail="Segmentation tree not trained yet. Run train_segmentation_tree.py first.",
        )
    return registry


@router.get("/segmentation/tree")
def get_tree():
    """Full tree structure JSON for visualization."""
    registry = _require_tree()
    return registry.tree_structure


@router.get("/segmentation/leaves")
def get_leaves():
    """Flat list of all leaves with summary stats."""
    registry = _require_tree()
    leaves = registry.tree_structure.get("leaves", [])
    return {"leaves": leaves, "count": len(leaves)}


@router.get("/segmentation/leaf/{leaf_id}")
def get_leaf_detail(leaf_id: int):
    """Single leaf detail including survival curve."""
    registry = _require_tree()

    # Find leaf in flat list
    leaves = registry.tree_structure.get("leaves", [])
    leaf = next((l for l in leaves if l["leaf_id"] == leaf_id), None)
    if leaf is None:
        raise HTTPException(status_code=404, detail=f"Leaf {leaf_id} not found")

    # Get survival curve for this leaf
    curve = registry.survival_curves.get(leaf_id, [])
    curve_data = [
        {"month": i + 1, "survival_prob": round(p, 6)}
        for i, p in enumerate(curve)
    ]

    return {
        **leaf,
        "survival_curve": curve_data,
    }


@router.get("/segmentation/leaf/{leaf_id}/loans")
def get_leaf_loans(
    leaf_id: int,
    source: Optional[str] = Query(None, description="Filter by source: 'fnba' or 'freddie'"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
):
    """Paginated training loans for a specific leaf. Supports source filtering."""
    registry = _require_tree()
    from app.config import settings
    from pathlib import Path

    model_dir = Path(settings.MODEL_DIR).resolve()
    leaf_path = model_dir / "segmentation" / "leaves" / f"leaf_{leaf_id}_loans.parquet"

    if not leaf_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Loan data for leaf {leaf_id} not found. Run training script first.",
        )

    try:
        import pyarrow.parquet as pq
        table = pq.read_table(str(leaf_path))
        df = table.to_pandas()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read leaf data: {e}")

    # Filter by source if requested
    if source:
        source_lower = source.lower()
        if source_lower not in ("fnba", "freddie"):
            raise HTTPException(status_code=400, detail="source must be 'fnba' or 'freddie'")
        df = df[df["source"] == source_lower]

    total = len(df)
    total_pages = max(1, (total + page_size - 1) // page_size)

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end]

    return {
        "leaf_id": leaf_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "source_filter": source,
        "loans": page_df.to_dict(orient="records"),
    }
