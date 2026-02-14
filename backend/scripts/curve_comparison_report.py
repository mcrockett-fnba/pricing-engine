#!/usr/bin/env python3
"""V1 vs V2 Survival Curve Comparison — CIO Deliverable.

Loads both full-history and lookback survival curves, routes tape loans through
the segmentation tree, and produces a focused comparison HTML showing:
  - Per-leaf KM curve overlays (V1 vs V2)
  - Life estimate delta table
  - Portfolio-level price sensitivity estimate
  - Explanation of the THR $3.8M gap

Usage:
  cd backend
  source .venv/bin/activate
  python scripts/curve_comparison_report.py
  python scripts/curve_comparison_report.py --lookback 24  # compare 24-month variant
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ml.model_loader import ModelRegistry
from app.ml.bucket_assigner import assign_bucket
from app.services.tape_parser import parse_loan_tape

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
BACKEND_DIR = Path(__file__).resolve().parent.parent


def load_curves_from_parquet(path: Path) -> dict[int, list[float]]:
    """Load survival curves from parquet → {bucket_id: [S(1)..S(360)]}."""
    import pyarrow.parquet as pq
    table = pq.read_table(str(path))
    bids = table.column("bucket_id").to_pylist()
    months = table.column("month").to_pylist()
    probs = table.column("survival_prob").to_pylist()

    raw: dict[int, list[tuple[int, float]]] = {}
    for bid, m, p in zip(bids, months, probs):
        raw.setdefault(bid, []).append((m, p))

    curves = {}
    for bid, pairs in raw.items():
        pairs.sort(key=lambda x: x[0])
        curves[bid] = [p for _, p in pairs]
    return curves


def km_50pct_life(curve: list[float]) -> int | None:
    """Month where survival drops below 50%. None if it never crosses."""
    for i, s in enumerate(curve):
        if s < 0.5:
            return i + 1
    return None


def _fmt_life(life: int | None, mean: float | None = None, suffix="mo") -> str:
    """Format a 50%-life for display."""
    if life is not None:
        return f"{life}{suffix}"
    if mean is not None:
        return f"&gt;360 ({mean:.0f} mean){suffix}"
    return f"&gt;360{suffix}"


def _life_num(life: int | None, mean: float | None = None) -> int:
    """Numeric life for calculations; falls back to mean life."""
    if life is not None:
        return life
    if mean is not None:
        return round(mean)
    return 360


def km_mean_life(curve: list[float]) -> float:
    """Expected life = integral of survival curve."""
    return sum(curve)


def estimate_price_from_life(balance: float, rate: float, life_months: int,
                              discount_rate: float = 0.07) -> float:
    """Simple NPV estimate: PV of P&I for `life_months`, discounted at annual rate.

    This is a rough approximation for showing price sensitivity to life changes,
    not a full cashflow model.
    """
    if life_months <= 0 or balance <= 0:
        return 0.0
    r = rate / 12.0
    d = discount_rate / 12.0
    # Monthly P&I (standard amortization for remaining life)
    if r > 0:
        pmt = balance * r / (1.0 - (1.0 + r) ** -life_months)
    else:
        pmt = balance / life_months
    # PV of annuity at discount rate
    total_pv = 0.0
    for m in range(1, life_months + 1):
        total_pv += pmt / (1.0 + d) ** m
    return total_pv


def _svg_curve_overlay(curve_v1: list[float], curve_v2: list[float],
                        life_v1: int | None, life_v2: int | None,
                        label_v1: str = "V1 Full History",
                        label_v2: str = "V2 12mo Lookback",
                        width: int = 480, height: int = 220,
                        max_months: int = 240) -> str:
    """SVG overlay of two survival curves with life markers."""
    pad_l, pad_r, pad_t, pad_b = 50, 20, 25, 35
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    def x(m): return pad_l + m / max_months * pw
    def y(s): return pad_t + (1.0 - s) * ph

    # Grid lines
    grid = ""
    for pct in [0.25, 0.5, 0.75, 1.0]:
        yp = y(pct)
        grid += f'<line x1="{pad_l}" y1="{yp:.1f}" x2="{width-pad_r}" y2="{yp:.1f}" stroke="#e5e7eb" stroke-width="0.5"/>'
        grid += f'<text x="{pad_l-5}" y="{yp+4:.1f}" text-anchor="end" font-size="10" fill="#9ca3af">{pct:.0%}</text>'
    for mo in [0, 60, 120, 180, 240]:
        if mo <= max_months:
            xp = x(mo)
            grid += f'<line x1="{xp:.1f}" y1="{pad_t}" x2="{xp:.1f}" y2="{height-pad_b}" stroke="#e5e7eb" stroke-width="0.5"/>'
            grid += f'<text x="{xp:.1f}" y="{height-pad_b+14}" text-anchor="middle" font-size="10" fill="#9ca3af">{mo}mo</text>'

    # 50% line
    y50 = y(0.5)
    grid += f'<line x1="{pad_l}" y1="{y50:.1f}" x2="{width-pad_r}" y2="{y50:.1f}" stroke="#9ca3af" stroke-width="1" stroke-dasharray="4,4"/>'

    # Curve paths
    def path(curve, color, dash=""):
        pts = []
        for m in range(min(len(curve), max_months)):
            pts.append(f"{x(m):.1f},{y(curve[m]):.1f}")
        style = f'stroke="{color}" stroke-width="2" fill="none"'
        if dash:
            style += f' stroke-dasharray="{dash}"'
        return f'<polyline points="{" ".join(pts)}" {style}/>'

    v1_path = path(curve_v1, "#2563eb")  # blue
    v2_path = path(curve_v2, "#dc2626")  # red

    # Life markers (only when curve actually crosses 50%)
    markers = ""
    if life_v1 is not None and life_v1 <= max_months:
        markers += f'<circle cx="{x(life_v1):.1f}" cy="{y50:.1f}" r="4" fill="#2563eb"/>'
        markers += f'<text x="{x(life_v1)+6:.1f}" y="{y50-6:.1f}" font-size="10" fill="#2563eb">{life_v1}mo</text>'
    if life_v2 is not None and life_v2 <= max_months:
        markers += f'<circle cx="{x(life_v2):.1f}" cy="{y50:.1f}" r="4" fill="#dc2626"/>'
        markers += f'<text x="{x(life_v2)+6:.1f}" y="{y50+14:.1f}" font-size="10" fill="#dc2626">{life_v2}mo</text>'

    # Legend
    legend = f"""
    <rect x="{pad_l+10}" y="{pad_t+5}" width="12" height="3" fill="#2563eb"/>
    <text x="{pad_l+26}" y="{pad_t+10}" font-size="10" fill="#2563eb">{label_v1}</text>
    <rect x="{pad_l+10}" y="{pad_t+18}" width="12" height="3" fill="#dc2626"/>
    <text x="{pad_l+26}" y="{pad_t+23}" font-size="10" fill="#dc2626">{label_v2}</text>
    """

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
        xmlns="http://www.w3.org/2000/svg" style="font-family:sans-serif">
      <rect width="{width}" height="{height}" fill="white" rx="4"/>
      {grid}{v1_path}{v2_path}{markers}{legend}
    </svg>"""


def build_comparison_html(tape_path: Path, lookback_months: int) -> str:
    """Build the full comparison HTML report."""
    now = datetime.now().strftime("%B %d, %Y %I:%M %p")

    # Load curves
    v1_path = MODEL_DIR / "survival" / "survival_curves.parquet"
    v2_path = MODEL_DIR / "survival" / f"survival_curves_{lookback_months}mo.parquet"

    if not v1_path.exists():
        logger.error("V1 curves not found: %s", v1_path)
        sys.exit(1)
    if not v2_path.exists():
        logger.error("V2 curves not found: %s. Run: python scripts/train_segmentation_tree.py --curves-only --lookback-months %d", v2_path, lookback_months)
        sys.exit(1)

    curves_v1 = load_curves_from_parquet(v1_path)
    curves_v2 = load_curves_from_parquet(v2_path)
    logger.info("Loaded V1 (%d curves) and V2 (%d curves)", len(curves_v1), len(curves_v2))

    # Load tape and assign leaves
    registry = ModelRegistry.get()
    if not registry.is_loaded:
        registry.load(str(MODEL_DIR))

    with open(tape_path, "rb") as f:
        pkg = parse_loan_tape(f, tape_path.name)
    leaf_loans: dict[int, list] = defaultdict(list)
    for loan in pkg.loans:
        ld = loan.model_dump()
        leaf_id = assign_bucket(ld)
        leaf_loans[leaf_id].append(loan)

    tape_leaves = sorted(leaf_loans.keys())
    logger.info("Tape routes to %d leaves: %s", len(tape_leaves), tape_leaves)

    # Load manifest for variant metadata
    manifest_path = MODEL_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    variant_info = manifest.get("curve_variants", {}).get(f"{lookback_months}mo_lookback", {})

    # Build per-leaf comparison
    leaf_rows = []
    leaf_charts = []
    total_balance_v1_pv = 0.0
    total_balance_v2_pv = 0.0
    total_balance = 0.0

    for leaf_id in tape_leaves:
        loans = leaf_loans[leaf_id]
        n_loans = len(loans)
        leaf_balance = sum(l.unpaid_balance for l in loans)
        avg_rate = sum(l.interest_rate * l.unpaid_balance for l in loans) / leaf_balance if leaf_balance > 0 else 0
        avg_credit = sum(l.credit_score * l.unpaid_balance for l in loans) / leaf_balance if leaf_balance > 0 else 0

        c_v1 = curves_v1.get(leaf_id, [1.0] * 360)
        c_v2 = curves_v2.get(leaf_id, [1.0] * 360)

        life_v1 = km_50pct_life(c_v1)
        life_v2 = km_50pct_life(c_v2)
        mean_v1 = km_mean_life(c_v1)
        mean_v2 = km_mean_life(c_v2)
        s60_v1 = c_v1[59] if len(c_v1) >= 60 else 1.0
        s60_v2 = c_v2[59] if len(c_v2) >= 60 else 1.0

        # Numeric life for calculations (falls back to mean when 50%-life is None)
        life_v1_num = _life_num(life_v1, mean_v1)
        life_v2_num = _life_num(life_v2, mean_v2)

        # Display strings
        life_v1_disp = _fmt_life(life_v1, mean_v1, suffix="")
        life_v2_disp = _fmt_life(life_v2, mean_v2, suffix="")

        # Simple price sensitivity: PV of P&I for each life estimate
        # This shows directional impact, not exact prices
        pv_v1 = sum(estimate_price_from_life(l.unpaid_balance, l.interest_rate, min(life_v1_num, l.remaining_term)) for l in loans)
        pv_v2 = sum(estimate_price_from_life(l.unpaid_balance, l.interest_rate, min(life_v2_num, l.remaining_term)) for l in loans)

        total_balance += leaf_balance
        total_balance_v1_pv += pv_v1
        total_balance_v2_pv += pv_v2

        life_delta = life_v2_num - life_v1_num
        pv_delta = pv_v2 - pv_v1
        delta_color = "#dc2626" if pv_delta < 0 else "#16a34a"

        leaf_rows.append(f"""
        <tr>
          <td class="num">{leaf_id}</td>
          <td class="num">{n_loans}</td>
          <td class="num">${leaf_balance:,.0f}</td>
          <td class="num">{avg_credit:.0f}</td>
          <td class="num">{life_v1_disp}</td>
          <td class="num"><strong>{life_v2_disp}</strong></td>
          <td class="num" style="color:{delta_color}">+{life_delta}</td>
          <td class="num">{mean_v1:.0f}</td>
          <td class="num">{mean_v2:.0f}</td>
          <td class="num">{s60_v1:.3f}</td>
          <td class="num">{s60_v2:.3f}</td>
          <td class="num" style="color:{delta_color}">${pv_delta:+,.0f}</td>
        </tr>""")

        # SVG chart
        chart = _svg_curve_overlay(c_v1, c_v2, life_v1, life_v2)
        leaf_charts.append(f"""
        <div class="leaf-card">
          <h3>Leaf {leaf_id} — {n_loans} loans, ${leaf_balance:,.0f} UPB</h3>
          <div style="font-size:12px;color:#6b7280;margin-bottom:8px">
            Credit {avg_credit:.0f} &bull; Rate {avg_rate*100:.2f}%
            &bull; 50%-life: <span style="color:#2563eb">{life_v1_disp}mo</span> &rarr;
            <span style="color:#dc2626">{life_v2_disp}mo</span> (+{life_delta}mo)
          </div>
          {chart}
        </div>""")

    # Portfolio summary
    pv_delta_total = total_balance_v2_pv - total_balance_v1_pv

    # Extrapolate: if KM-only pricing shows this delta from life change alone,
    # the full engine impact would be larger (stub prepay adds additional exits in V1)
    n_v2_km_loans = variant_info.get("n_loans", 0)
    n_v2_payoffs = variant_info.get("n_payoffs", 0)
    n_v2_censored = variant_info.get("n_censored", 0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>V1 vs V2 Survival Curve Comparison</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f9fafb; color: #1f2937; line-height: 1.5; }}
  .page {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  .header {{ background: linear-gradient(135deg, #003D2A 0%, #005C3F 100%); color: white; padding: 28px 36px; border-radius: 12px; margin-bottom: 24px; }}
  .header h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 4px; }}
  .header .subtitle {{ opacity: 0.85; font-size: 13px; }}
  .card {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #e5e7eb; }}
  .card h2 {{ font-size: 18px; font-weight: 600; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid #e5e7eb; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }}
  .summary-box {{ background: #f3f4f6; border-radius: 8px; padding: 16px; text-align: center; }}
  .summary-box .big {{ font-size: 22px; font-weight: 700; color: #005C3F; }}
  .summary-box .label {{ font-size: 11px; color: #6b7280; text-transform: uppercase; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f3f4f6; padding: 8px 10px; text-align: left; font-weight: 600; border-bottom: 2px solid #e5e7eb; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid #f3f4f6; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .leaf-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 16px; }}
  .leaf-card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
  .leaf-card h3 {{ font-size: 14px; font-weight: 600; margin-bottom: 4px; }}
  .callout {{ background: #fef3c7; border: 1px solid #fbbf24; border-radius: 8px; padding: 16px; margin: 16px 0; font-size: 13px; }}
  .callout-red {{ background: #fef2f2; border-color: #fca5a5; }}
  .callout strong {{ display: block; margin-bottom: 4px; }}
  .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #e5e7eb; }}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <h1>Survival Curve Comparison: V1 vs V2</h1>
    <div class="subtitle">
      Full History vs {lookback_months}-Month Lookback &bull; {len(pkg.loans)} loans, ${total_balance:,.0f} UPB &bull; Generated {now}
    </div>
  </div>

  <div class="card">
    <h2>Executive Summary</h2>
    <div class="summary-grid">
      <div class="summary-box">
        <div class="big" style="color:#2563eb">V1</div>
        <div class="label">Full History</div>
        <div style="font-size:12px">4.4M training loans</div>
      </div>
      <div class="summary-box">
        <div class="big" style="color:#dc2626">V2</div>
        <div class="label">{lookback_months}mo Lookback</div>
        <div style="font-size:12px">{n_v2_km_loans:,} training loans ({n_v2_payoffs:,} payoffs)</div>
      </div>
      <div class="summary-box">
        <div class="big">{len(tape_leaves)}</div>
        <div class="label">Tape Leaves</div>
        <div style="font-size:12px">{len(pkg.loans)} loans across tree</div>
      </div>
      <div class="summary-box">
        <div class="big" style="color:#dc2626">${pv_delta_total:+,.0f}</div>
        <div class="label">PV Delta (life-based est.)</div>
        <div style="font-size:12px">{pv_delta_total/total_balance*100:+.1f}% of UPB</div>
      </div>
    </div>

    <div class="callout">
      <strong>What is the {lookback_months}-month lookback?</strong>
      V1 (Full History) trains KM survival curves on all 4.4M loans including the 2020-2021 refi wave
      (Freddie median payoff: 21 months). V2 filters to only the last {lookback_months} months of observations,
      which strips out the fast-prepay era. In the current rate environment (4.5%+ market vs 3.2% note rate),
      recent prepayment speeds are near zero, so the {lookback_months}-month lookback dramatically extends
      effective life estimates.
    </div>

    <div class="callout callout-red">
      <strong>Why the PE pricing delta is small ($174K, not $3.8M)</strong>
      The pricing engine uses KM curves as an &ldquo;all-causes hazard&rdquo; overlay on top of a separate
      stub prepayment model. Both reduce the surviving pool independently. When 12mo-lookback flattens
      the KM curves (hazard &rarr; 0), the stub prepay model continues generating exits &mdash; so the
      price barely moves. To replicate the THR &dollar;3.8M gap, the engine needs architectural changes
      to use KM survival as the sole exit model (see TODO 1.5.7).
      <br><br>
      The <strong>life estimate delta below IS meaningful</strong> and shows what the lookback does
      directionally. The PV sensitivity column estimates the price impact if KM life were the sole
      driver of amortization speed.
    </div>
  </div>

  <div class="card">
    <h2>Per-Leaf Life Comparison</h2>
    <table>
      <thead>
        <tr>
          <th>Leaf</th>
          <th>Loans</th>
          <th>Balance</th>
          <th>Credit</th>
          <th>V1 50%-Life</th>
          <th>V2 50%-Life</th>
          <th>&Delta; Life</th>
          <th>V1 Mean</th>
          <th>V2 Mean</th>
          <th>V1 S(60)</th>
          <th>V2 S(60)</th>
          <th>PV &Delta; (est.)</th>
        </tr>
      </thead>
      <tbody>
        {"".join(leaf_rows)}
      </tbody>
      <tfoot>
        <tr style="font-weight:600;border-top:2px solid #e5e7eb">
          <td>Total</td>
          <td class="num">{len(pkg.loans)}</td>
          <td class="num">${total_balance:,.0f}</td>
          <td></td>
          <td colspan="3" style="text-align:center;color:#6b7280">weighted by balance</td>
          <td colspan="2"></td>
          <td colspan="2"></td>
          <td class="num" style="color:{'#dc2626' if pv_delta_total < 0 else '#16a34a'}">${pv_delta_total:+,.0f}</td>
        </tr>
      </tfoot>
    </table>
  </div>

  <div class="card">
    <h2>Survival Curve Overlays</h2>
    <p style="font-size:13px;color:#6b7280;margin-bottom:16px">
      <span style="color:#2563eb">&#9632;</span> V1 Full History &nbsp;
      <span style="color:#dc2626">&#9632;</span> V2 {lookback_months}mo Lookback &nbsp;
      Dots mark 50%-life crossing. Dashed line = 50% survival.
    </p>
    <div class="leaf-grid">
      {"".join(leaf_charts)}
    </div>
  </div>

  <div class="card">
    <h2>Data Summary</h2>
    <table style="max-width:600px">
      <thead><tr><th>Metric</th><th>V1 (Full History)</th><th>V2 ({lookback_months}mo Lookback)</th></tr></thead>
      <tbody>
        <tr><td>Training loans</td><td class="num">4,425,553</td><td class="num">{n_v2_km_loans:,}</td></tr>
        <tr><td>Payoffs</td><td class="num">3,134,273</td><td class="num">{n_v2_payoffs:,}</td></tr>
        <tr><td>Censored</td><td class="num">1,291,280</td><td class="num">{n_v2_censored:,}</td></tr>
        <tr><td>Payoff rate</td><td class="num">70.8%</td><td class="num">{n_v2_payoffs/max(n_v2_km_loans,1)*100:.1f}%</td></tr>
        <tr><td>Curve file</td><td>survival_curves.parquet</td><td>survival_curves_{lookback_months}mo.parquet</td></tr>
        <tr><td>Tree structure</td><td colspan="2" style="text-align:center">Same 75-leaf tree (unchanged)</td></tr>
      </tbody>
    </table>
  </div>

  <div class="footer">
    Generated by curve_comparison_report.py &bull; {now}
  </div>

</div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Compare V1 vs V2 survival curves")
    parser.add_argument("--tape", help="Path to loan tape (default: loan_tape_2_clean.xlsx)")
    parser.add_argument("--lookback", type=int, default=12, help="Lookback months for V2 (default: 12)")
    parser.add_argument("--out", help="Output filename (default: curve_comparison.html)")
    args = parser.parse_args()

    tape_path = Path(args.tape) if args.tape else BACKEND_DIR / "loan_tape_2_clean.xlsx"
    if not tape_path.exists():
        logger.error("Tape not found: %s", tape_path)
        sys.exit(1)

    t0 = time.time()
    html = build_comparison_html(tape_path, args.lookback)

    REPORTS_DIR.mkdir(exist_ok=True)
    out_name = args.out or "curve_comparison.html"
    out_path = REPORTS_DIR / out_name
    out_path.write_text(html, encoding="utf-8")
    logger.info("Wrote %s (%d KB) in %.1fs", out_path, len(html) // 1024, time.time() - t0)


if __name__ == "__main__":
    main()
