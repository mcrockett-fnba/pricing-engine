#!/usr/bin/env python3
"""Generate a self-contained HTML segmentation report.

Usage:
    python scripts/segmentation_report.py                         # training only
    python scripts/segmentation_report.py --tape loan_tape.xlsx   # training + tape overlay
    python scripts/segmentation_report.py --out custom_name.html

Output lands in ``reports/`` at the project root.
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
MODEL_DIR = PROJECT_DIR / "models"
REPORTS_DIR = PROJECT_DIR / "reports"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_tree_artifacts():
    """Return (tree, tree_structure, survival_df, metadata)."""
    import joblib

    seg_dir = MODEL_DIR / "segmentation"
    tree = joblib.load(seg_dir / "segmentation_tree.pkl")
    with open(seg_dir / "tree_structure.json") as f:
        structure = json.load(f)
    with open(seg_dir / "segmentation_metadata.json") as f:
        metadata = json.load(f)
    surv_df = pd.read_parquet(MODEL_DIR / "survival" / "survival_curves.parquet")
    return tree, structure, surv_df, metadata


def load_tape(tape_path: str):
    """Parse a loan tape and return (Package, list[dict])."""
    sys.path.insert(0, str(BACKEND_DIR))
    from app.services.tape_parser import parse_loan_tape

    with open(tape_path, "rb") as f:
        pkg = parse_loan_tape(f, Path(tape_path).name)
    return pkg


def assign_tape_to_leaves(pkg, tree, structure):
    """Return dict[leaf_id] -> list[loan_dict]."""
    state_map = structure.get("state_group_mapping", {})
    node_to_leaf = {int(k): v for k, v in structure["node_to_leaf"].items()}

    leaf_loans: dict[int, list[dict]] = defaultdict(list)
    for loan in pkg.loans:
        d = loan.model_dump()
        state = d.get("state", "") or ""
        sg = state_map.get(state, 3)
        features = np.array([[
            2020,
            d.get("credit_score") or 700,
            d.get("dti") or 36.0,
            (d.get("ltv") or 0.80) * 100,
            (d.get("interest_rate") or 0.07) * 100,
            d.get("unpaid_balance", 200000),
            sg,
            d.get("ITIN", 0),
            d.get("original_term") or 360,
        ]])
        node_id = int(tree.apply(features)[0])
        leaf_id = node_to_leaf.get(node_id, node_id)
        leaf_loans[leaf_id].append(d)
    return dict(leaf_loans)


# ---------------------------------------------------------------------------
# SVG survival curve (inline, no JS dependency)
# ---------------------------------------------------------------------------
def svg_survival_curve(surv_df: pd.DataFrame, leaf_id: int,
                       width: int = 420, height: int = 180) -> str:
    """Return an SVG string for a single leaf's survival curve."""
    lc = surv_df[surv_df["bucket_id"] == leaf_id].sort_values("month")
    if lc.empty:
        return '<span class="muted">No curve data</span>'

    months = lc["month"].values
    probs = lc["survival_prob"].values
    max_month = int(months.max())

    pad_l, pad_r, pad_t, pad_b = 45, 15, 10, 30
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    def tx(m):
        return pad_l + (m / max_month) * pw

    def ty(s):
        return pad_t + (1 - s) * ph

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    lines.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="4"/>')

    # Grid lines
    for pct in (0.25, 0.50, 0.75):
        y = ty(pct)
        lines.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
                      f'stroke="#e0e0e0" stroke-dasharray="3,3"/>')
        lines.append(f'<text x="{pad_l-5}" y="{y+4:.1f}" text-anchor="end" '
                      f'font-size="10" fill="#888">{pct:.0%}</text>')
    # 100% and 0%
    lines.append(f'<text x="{pad_l-5}" y="{ty(1)+4:.1f}" text-anchor="end" font-size="10" fill="#888">100%</text>')
    lines.append(f'<text x="{pad_l-5}" y="{ty(0)+4:.1f}" text-anchor="end" font-size="10" fill="#888">0%</text>')

    # X-axis labels
    for yr in range(5, max_month // 12 + 1, 5):
        m = yr * 12
        if m <= max_month:
            x = tx(m)
            lines.append(f'<text x="{x:.1f}" y="{height-5}" text-anchor="middle" '
                          f'font-size="10" fill="#888">{yr}yr</text>')

    # Curve path
    points = " ".join(f"{tx(m):.1f},{ty(s):.1f}" for m, s in zip(months, probs))
    lines.append(f'<polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="2"/>')

    # 50% life marker
    half_idx = np.where(probs <= 0.5)[0]
    if len(half_idx):
        hm = int(months[half_idx[0]])
        hx, hy = tx(hm), ty(0.5)
        lines.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="4" fill="#ef4444"/>')
        lines.append(f'<text x="{hx+6:.1f}" y="{hy-6:.1f}" font-size="10" fill="#ef4444" '
                      f'font-weight="600">{hm}mo</text>')

    # Axes
    lines.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height-pad_b}" stroke="#666"/>')
    lines.append(f'<line x1="{pad_l}" y1="{height-pad_b}" x2="{width-pad_r}" y2="{height-pad_b}" stroke="#666"/>')

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------
FEATURE_NAMES = {
    "noteDateYear": "Year",
    "interestRate": "Rate",
    "creditScore": "Credit",
    "ltv": "LTV",
    "loanSize": "Balance",
    "stateGroup": "State Group",
    "ITIN": "ITIN",
    "origCustAmortMonth": "Orig Term",
    "dti": "DTI",
}


def format_rule(rule: dict) -> str:
    feat = FEATURE_NAMES.get(rule["feature"], rule["feature"])
    op = rule["operator"]
    t = rule["threshold"]
    if feat == "Rate":
        return f"{feat} {op} {t:.1f}%"
    if feat == "LTV":
        return f"{feat} {op} {t:.1f}%"
    if feat == "Balance":
        return f"{feat} {op} ${t:,.0f}"
    if feat == "Year":
        return f"{feat} {op} {t:.0f}"
    if feat == "Orig Term":
        return f"{feat} {op} {t:.0f}"
    return f"{feat} {op} {t:.1f}"


def stat_row(label: str, value: str) -> str:
    return f'<tr><td class="stat-label">{label}</td><td class="stat-value">{value}</td></tr>'


def build_html(structure, surv_df, metadata, tape_pkg=None, tape_leaf_loans=None) -> str:
    leaves = sorted(structure["leaves"], key=lambda x: x["samples"], reverse=True)
    leaf_lookup = {l["leaf_id"]: l for l in leaves}
    total_training = sum(l["samples"] for l in leaves)
    total_fnba = sum(l["n_fnba"] for l in leaves)
    total_freddie = sum(l["n_freddie"] for l in leaves)

    has_tape = tape_pkg is not None and tape_leaf_loans is not None
    tape_total = tape_pkg.loan_count if has_tape else 0
    tape_upb = tape_pkg.total_upb if has_tape else 0

    now = datetime.now().strftime("%B %d, %Y %I:%M %p")
    created = metadata.get("created_at", "")[:10]

    # -- Header section --
    header_cards = f"""
    <div class="summary-grid">
      <div class="summary-card">
        <div class="card-number">{len(leaves)}</div>
        <div class="card-label">Leaves</div>
      </div>
      <div class="summary-card">
        <div class="card-number">{total_training:,}</div>
        <div class="card-label">Training Loans</div>
        <div class="card-sub">{total_fnba:,} FNBA &bull; {total_freddie:,} Freddie</div>
      </div>
      <div class="summary-card">
        <div class="card-number">{metadata['results']['tree_depth']}</div>
        <div class="card-label">Tree Depth</div>
      </div>
      <div class="summary-card">
        <div class="card-number">9</div>
        <div class="card-label">Features</div>
      </div>
    </div>
    """

    if has_tape:
        tape_leaves_hit = len(tape_leaf_loans)
        header_cards += f"""
    <div class="tape-banner">
      <strong>Tape Overlay:</strong> {tape_pkg.name} &mdash;
      {tape_total:,} loans &bull; ${tape_upb:,.0f} UPB &bull;
      {tape_leaves_hit} of {len(leaves)} leaves populated
    </div>
    """

    # -- Training overview table --
    overview_rows = []
    for rank, leaf in enumerate(leaves, 1):
        lid = leaf["leaf_id"]
        pct = leaf["samples"] / total_training * 100
        bar_w = max(1, pct * 2.5)
        fnba_pct = leaf["n_fnba"] / leaf["samples"] * 100 if leaf["samples"] else 0
        payoff_pct = leaf["n_payoffs"] / leaf["samples"] * 100 if leaf["samples"] else 0

        tape_n = len(tape_leaf_loans.get(lid, [])) if has_tape else 0
        tape_upb_leaf = sum(l["unpaid_balance"] for l in tape_leaf_loans.get(lid, [])) if has_tape else 0
        tape_cell = (f'<td class="num">{tape_n}</td>'
                     f'<td class="num">${tape_upb_leaf:,.0f}</td>') if has_tape else ""

        label = html_mod.escape(leaf.get("label", f"Leaf {lid}"))
        overview_rows.append(f"""
        <tr class="{'tape-hit' if tape_n > 0 else ''}">
          <td class="num">{lid}</td>
          <td class="num">{leaf['samples']:,}</td>
          <td><div class="bar-bg"><div class="bar" style="width:{bar_w:.1f}%"></div></div></td>
          <td class="num">{pct:.1f}%</td>
          <td class="num">{leaf['n_fnba']:,}</td>
          <td class="num">{leaf['n_freddie']:,}</td>
          <td class="num">{leaf['median_time']:.0f}</td>
          <td class="num">{payoff_pct:.0f}%</td>
          {tape_cell}
          <td class="rule-cell">{label}</td>
        </tr>""")

    tape_cols = ('<th>Tape Loans</th><th>Tape UPB</th>' if has_tape else "")
    overview_table = f"""
    <table class="data-table" id="overviewTable">
      <thead><tr>
        <th>Leaf</th><th>Training</th><th></th><th>%</th>
        <th>FNBA</th><th>Freddie</th><th>Median&nbsp;Mo</th><th>Payoff%</th>
        {tape_cols}
        <th>Top Split Path</th>
      </tr></thead>
      <tbody>{"".join(overview_rows)}</tbody>
    </table>
    """

    # -- Detail cards for leaves that have tape loans (or all if no tape) --
    detail_cards = []
    display_leaves = leaves if not has_tape else [
        l for l in leaves if l["leaf_id"] in tape_leaf_loans
    ]
    # Sort display leaves by tape count desc (if tape), else by training size
    if has_tape:
        display_leaves = sorted(
            display_leaves,
            key=lambda l: len(tape_leaf_loans.get(l["leaf_id"], [])),
            reverse=True,
        )

    for leaf in display_leaves:
        lid = leaf["leaf_id"]
        rules_html = " &rarr; ".join(
            f'<span class="rule-chip">{html_mod.escape(format_rule(r))}</span>'
            for r in leaf.get("rules", [])
        )

        # Training stats
        train_stats = f"""
        <table class="mini-stats">
          {stat_row("Training loans", f"{leaf['samples']:,}")}
          {stat_row("FNBA / Freddie", f"{leaf['n_fnba']:,} / {leaf['n_freddie']:,}")}
          {stat_row("Payoffs / Censored", f"{leaf['n_payoffs']:,} / {leaf['n_censored']:,}")}
          {stat_row("Mean time", f"{leaf['mean_time']:.1f} mo")}
          {stat_row("Median time", f"{leaf['median_time']:.0f} mo")}
        </table>
        """

        # Tape stats (if applicable)
        tape_stats_html = ""
        if has_tape and lid in tape_leaf_loans:
            tl = tape_leaf_loans[lid]
            n = len(tl)
            credits = [l.get("credit_score") or 700 for l in tl]
            rates = [(l["interest_rate"]) * 100 for l in tl]
            ltvs = [(l.get("ltv") or 0.80) * 100 for l in tl]
            bals = [l["unpaid_balance"] for l in tl]
            ages = [l["loan_age"] for l in tl]
            states: Counter = Counter(l.get("state", "?") for l in tl)
            top_st = ", ".join(f"{s} ({c})" for s, c in states.most_common(5))
            tape_upb_l = sum(bals)

            tape_stats_html = f"""
            <div class="tape-section">
              <h4>Tape Loans ({n})</h4>
              <table class="mini-stats">
                {stat_row("Loans / UPB", f"{n} / ${tape_upb_l:,.0f}")}
                {stat_row("Credit", f"{min(credits)} &ndash; {max(credits)}  (avg {np.mean(credits):.0f})")}
                {stat_row("Rate", f"{min(rates):.2f}% &ndash; {max(rates):.2f}%  (avg {np.mean(rates):.2f}%)")}
                {stat_row("LTV", f"{min(ltvs):.1f}% &ndash; {max(ltvs):.1f}%  (avg {np.mean(ltvs):.1f}%)")}
                {stat_row("Balance", f"${min(bals):,.0f} &ndash; ${max(bals):,.0f}  (avg ${np.mean(bals):,.0f})")}
                {stat_row("Age", f"{min(ages)} &ndash; {max(ages)} mo  (avg {np.mean(ages):.0f})")}
                {stat_row("States", top_st)}
              </table>
            </div>
            """

        svg = svg_survival_curve(surv_df, lid)

        detail_cards.append(f"""
        <div class="leaf-card" id="leaf-{lid}">
          <div class="leaf-header">
            <span class="leaf-id">Leaf {lid}</span>
            <span class="leaf-train-count">{leaf['samples']:,} training loans</span>
          </div>
          <div class="rules-path">{rules_html}</div>
          <div class="leaf-body">
            <div class="leaf-col">
              <h4>Training Population</h4>
              {train_stats}
              {tape_stats_html}
            </div>
            <div class="leaf-col">
              <h4>Survival Curve</h4>
              {svg}
            </div>
          </div>
        </div>
        """)

    # -- Assemble full page --
    details_heading = "Leaf Details (Tape Matches)" if has_tape else "Leaf Details (All 75 Leaves)"

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Segmentation Tree Report</title>
<style>
  :root {{
    --blue: #2563eb;
    --blue-light: #dbeafe;
    --green: #16a34a;
    --green-light: #dcfce7;
    --red: #ef4444;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-400: #9ca3af;
    --gray-600: #4b5563;
    --gray-800: #1f2937;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--gray-50);
    color: var(--gray-800);
    line-height: 1.5;
    padding: 0;
  }}
  .page {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
  .page-header {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
    color: white;
    padding: 32px 40px;
    border-radius: 12px;
    margin-bottom: 24px;
  }}
  .page-header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 4px; }}
  .page-header .subtitle {{ opacity: 0.85; font-size: 14px; }}

  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 20px;
  }}
  .summary-card {{
    background: white;
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid var(--gray-200);
  }}
  .card-number {{ font-size: 32px; font-weight: 700; color: var(--blue); }}
  .card-label {{ font-size: 13px; color: var(--gray-600); text-transform: uppercase; letter-spacing: 0.5px; }}
  .card-sub {{ font-size: 12px; color: var(--gray-400); margin-top: 4px; }}

  .tape-banner {{
    background: var(--green-light);
    border: 1px solid #86efac;
    border-radius: 8px;
    padding: 12px 20px;
    margin-bottom: 20px;
    font-size: 14px;
  }}

  .section-title {{
    font-size: 20px;
    font-weight: 600;
    margin: 32px 0 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--gray-200);
  }}

  /* Overview table */
  .table-wrap {{
    overflow-x: auto;
    margin-bottom: 32px;
  }}
  .data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    background: white;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .data-table thead {{
    background: var(--gray-100);
  }}
  .data-table th {{
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    color: var(--gray-600);
    white-space: nowrap;
    position: sticky;
    top: 0;
    cursor: pointer;
    user-select: none;
  }}
  .data-table th:hover {{ background: var(--gray-200); }}
  .data-table td {{
    padding: 8px 12px;
    border-top: 1px solid var(--gray-100);
    white-space: nowrap;
  }}
  .data-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .data-table tr:hover {{ background: var(--blue-light); }}
  .data-table tr.tape-hit {{ background: #f0fdf4; }}
  .data-table tr.tape-hit:hover {{ background: #dcfce7; }}
  .rule-cell {{ white-space: normal; max-width: 320px; font-size: 12px; color: var(--gray-600); }}

  .bar-bg {{
    width: 80px;
    height: 8px;
    background: var(--gray-200);
    border-radius: 4px;
    overflow: hidden;
  }}
  .bar {{
    height: 100%;
    background: var(--blue);
    border-radius: 4px;
  }}

  /* Leaf detail cards */
  .leaf-card {{
    background: white;
    border-radius: 10px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid var(--gray-200);
  }}
  .leaf-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
  }}
  .leaf-id {{
    font-size: 18px;
    font-weight: 700;
    color: var(--blue);
  }}
  .leaf-train-count {{
    font-size: 13px;
    color: var(--gray-400);
  }}
  .rules-path {{
    margin-bottom: 16px;
    line-height: 2;
  }}
  .rule-chip {{
    display: inline-block;
    background: var(--gray-100);
    border: 1px solid var(--gray-200);
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-family: "SF Mono", "Fira Code", monospace;
    color: var(--gray-600);
  }}
  .leaf-body {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
  }}
  .leaf-col h4 {{
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--gray-400);
    margin-bottom: 8px;
  }}
  .mini-stats {{
    font-size: 13px;
    border-collapse: collapse;
    width: 100%;
  }}
  .mini-stats td {{
    padding: 4px 0;
    border-bottom: 1px solid var(--gray-100);
  }}
  .stat-label {{ color: var(--gray-600); width: 45%; }}
  .stat-value {{ font-weight: 500; font-variant-numeric: tabular-nums; }}

  .tape-section {{
    margin-top: 16px;
    padding-top: 12px;
    border-top: 2px solid var(--green-light);
  }}
  .tape-section h4 {{
    color: var(--green) !important;
    margin-bottom: 8px;
  }}

  .muted {{ color: var(--gray-400); font-style: italic; }}

  .footer {{
    text-align: center;
    color: var(--gray-400);
    font-size: 12px;
    margin-top: 40px;
    padding: 20px;
  }}

  @media print {{
    body {{ background: white; }}
    .page {{ max-width: none; padding: 0; }}
    .page-header {{ break-after: avoid; }}
    .leaf-card {{ break-inside: avoid; }}
    .data-table th {{ position: static; }}
  }}
</style>
</head>
<body>
<div class="page">
  <div class="page-header">
    <h1>Segmentation Tree Report</h1>
    <div class="subtitle">
      {len(leaves)} leaves &bull; depth {metadata['results']['tree_depth']}
      &bull; trained {created} &bull; report generated {now}
    </div>
  </div>

  {header_cards}

  <h2 class="section-title">Training Population &mdash; All {len(leaves)} Leaves</h2>
  <div class="table-wrap">
    {overview_table}
  </div>

  <h2 class="section-title">{details_heading}</h2>
  {"".join(detail_cards)}

  <div class="footer">
    Generated by segmentation_report.py &bull; {now}
  </div>
</div>

<script>
// Sortable table headers
document.querySelectorAll('.data-table thead th').forEach((th, colIdx) => {{
  let asc = true;
  th.addEventListener('click', () => {{
    const tbody = th.closest('table').querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort((a, b) => {{
      const av = a.children[colIdx]?.textContent.replace(/[$,%,]/g, '').trim() || '';
      const bv = b.children[colIdx]?.textContent.replace(/[$,%,]/g, '').trim() || '';
      const an = parseFloat(av.replace(/,/g, ''));
      const bn = parseFloat(bv.replace(/,/g, ''));
      if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
      return asc ? av.localeCompare(bv) : bv.localeCompare(av);
    }});
    asc = !asc;
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>
</body>
</html>"""

    return page


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate segmentation HTML report")
    parser.add_argument("--tape", help="Path to Excel loan tape (optional)")
    parser.add_argument("--out", help="Output filename (default: segmentation_report.html)")
    args = parser.parse_args()

    logger.info("Loading segmentation artifacts...")
    tree, structure, surv_df, metadata = load_tree_artifacts()
    logger.info("  %d leaves, %d survival curves",
                len(structure["leaves"]),
                surv_df["bucket_id"].nunique())

    tape_pkg = None
    tape_leaf_loans = None
    if args.tape:
        logger.info("Loading tape: %s", args.tape)
        tape_pkg = load_tape(args.tape)
        logger.info("  %d loans, $%.0f UPB", tape_pkg.loan_count, tape_pkg.total_upb)
        tape_leaf_loans = assign_tape_to_leaves(tape_pkg, tree, structure)
        logger.info("  Assigned to %d leaves", len(tape_leaf_loans))

    logger.info("Generating HTML...")
    html = build_html(structure, surv_df, metadata, tape_pkg, tape_leaf_loans)

    REPORTS_DIR.mkdir(exist_ok=True)
    out_name = args.out or "segmentation_report.html"
    out_path = REPORTS_DIR / out_name
    out_path.write_text(html, encoding="utf-8")
    logger.info("Wrote %s (%d KB)", out_path, len(html) // 1024)


if __name__ == "__main__":
    main()
