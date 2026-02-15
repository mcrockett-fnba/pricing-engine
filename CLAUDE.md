# CLAUDE.md — Pricing Engine POC

## Project Purpose

Loan pricing engine POC for FNBA: ingest loan packages (from SQL Server or Excel upload), run Monte Carlo simulations with ML-driven transition probabilities, compute APEX2 prepayment analysis, and present interactive valuations via a web UI.

The engine prices "scratch and dent" (non-QM) mortgage packages — loans that are conventional quality (avg credit 762, LTV 57%) but have documentation defects (income verification gaps, title issues). Prepayment behavior for these loans differs from both conforming (Freddie Mac) and traditional non-prime populations.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + Vite)  :3000                        │
│  Proxies /api → :8000                                   │
├─────────────────────────────────────────────────────────┤
│  Backend (FastAPI)  :8000                                │
│  ├─ Routes: health, packages, valuation, models,        │
│  │          prepayment                                   │
│  ├─ Services: simulation_service, prepayment_analysis,  │
│  │            tape_parser, model_service                 │
│  ├─ ML: ModelRegistry (singleton), bucket_assigner,     │
│  │       curve_provider                                  │
│  └─ Simulation: engine, cash_flow, scenarios,           │
│                  state_transitions                       │
├─────────────────────────────────────────────────────────┤
│  Models Directory (../models from backend)               │
│  manifest.json + per-model subdirectories                │
│  (survival, deq, default, recovery, prepayment, apex2)  │
├─────────────────────────────────────────────────────────┤
│  SQL Server (external, via pyodbc)                       │
│  Package/loan data for DB-sourced workflows              │
└─────────────────────────────────────────────────────────┘
```

- **Backend**: FastAPI (Python 3.12) at port 8000, all routes under `/api/`
- **Frontend**: Vue 3 + Vite at port 3000, proxies `/api` → backend via `vite.config.js`
- **Database**: External SQL Server via pyodbc (sync). Optional — the UI works without it using uploaded tapes or the built-in 10-loan sample package.
- **ML Models**: Stored in `models/` directory at project root (not inside backend). `MODEL_DIR` defaults to `../models` (relative to backend CWD).

## Project Structure

```
pricingEngine/
├── CLAUDE.md                    # This file
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, lifespan (DB init + model load), CORS
│   │   ├── config.py            # pydantic-settings: SQLSERVER_CONN_STRING, MODEL_DIR, CORS_ORIGINS
│   │   ├── api/
│   │   │   ├── deps.py          # get_db() dependency injection
│   │   │   └── routes/
│   │   │       ├── health.py    # GET /api/health
│   │   │       ├── packages.py  # GET /api/packages, POST /api/packages/upload, GET /api/packages/{id}
│   │   │       ├── valuation.py # POST /api/valuations/run
│   │   │       ├── models.py    # GET /api/models/status
│   │   │       ├── prepayment.py# POST /api/prepayment/analyze
│   │   │       └── segmentation.py # GET /api/segmentation/* (tree, leaves, leaf detail, loans)
│   │   ├── db/
│   │   │   ├── connection.py    # DatabasePool (pyodbc connection pooling)
│   │   │   └── queries/
│   │   │       └── packages.py  # SQL queries: list_packages, get_package_by_id
│   │   ├── models/              # Pydantic schemas (NOT ML models)
│   │   │   ├── loan.py          # Loan, LoanSummary
│   │   │   ├── package.py       # Package, PackageSummary
│   │   │   ├── simulation.py    # SimulationConfig
│   │   │   ├── valuation.py     # LoanValuationResult, PackageValuationResult, MonthlyCashFlow
│   │   │   └── prepayment.py    # PrepaymentConfig, PrepaymentAnalysisResult, ScenarioResult, etc.
│   │   ├── ml/                  # ML model loading and inference
│   │   │   ├── model_loader.py  # ModelRegistry singleton — loads manifest, curves, APEX2 tables
│   │   │   ├── bucket_assigner.py # 3-tier: XGBoost → JSON rules → hardcoded fallback
│   │   │   └── curve_provider.py  # Provides survival/prepayment curves by bucket_id
│   │   ├── simulation/          # Monte Carlo engine
│   │   │   ├── engine.py        # simulate_loan(): deterministic + stochastic per scenario
│   │   │   ├── cash_flow.py     # project_cash_flows(): monthly amort with state transitions
│   │   │   ├── scenarios.py     # 3 scenarios: baseline, mild_recession, severe_recession
│   │   │   └── state_transitions.py # Loan state machine (current→delinquent→default→recovered)
│   │   └── services/
│   │       ├── model_service.py     # initialize_models(), facade for ML
│   │       ├── simulation_service.py# run_valuation() orchestrator
│   │       ├── prepayment_analysis.py # APEX2 multiplier computation + effective life projection
│   │       ├── tape_parser.py       # Excel upload: parse_loan_tape() with flexible column matching
│   │       └── segmentation_service.py # Stub for future segmentation tree
│   ├── tests/                   # pytest test suite
│   │   ├── conftest.py          # Mocks pyodbc (not available in WSL)
│   │   ├── test_tape_parser.py  # 8 tests for tape upload parsing
│   │   ├── test_upload_route.py # 3 tests for upload endpoint
│   │   └── ... (13 test files total, ~113 tests)
│   ├── scripts/
│   │   ├── train_segmentation_tree.py # Train 75-leaf tree on blended FNBA+Freddie
│   │   ├── generate_stub_models.py    # Produces all model artifacts in models/
│   │   ├── generate_apex2_summary.py  # Generates Word doc summary of APEX2 review
│   │   ├── apex2_comparison.py        # Compares engine APEX2 vs production APEX2 spreadsheet
│   │   ├── train_freddie_prepayment.py# XGBoost training on Freddie Mac data
│   │   └── strip_pii.py              # Removes PII from loan tapes
│   ├── requirements.txt
│   └── .venv/                   # Python 3.12 virtual environment
├── frontend/
│   ├── src/
│   │   ├── App.vue              # Shell with nav bar (Packages, Valuation, Prepayment, Models)
│   │   │   ├── router/index.js      # Routes: /, /packages, /packages/:id, /valuations, /models, /prepayment, /segmentation
│   │   ├── views/
│   │   │   ├── PackageList.vue      # Lists DB packages
│   │   │   ├── PackageValuation.vue # DB package detail + valuation
│   │   │   ├── RunValuation.vue     # Main valuation page (sample/uploaded package)
│   │   │   ├── ModelStatus.vue      # Shows all models with status badges (stub/real)
│   │   │   ├── PrepaymentAnalysis.vue # APEX2 analysis UI
│   │   │   └── SegmentationView.vue # Tree diagram + leaf table + detail panel + loan drill-through
│   │   ├── components/
│   │   │   ├── ParameterPanel.vue   # Loan editor + upload tape button + reset button
│   │   │   ├── ValuationResults.vue # Results display
│   │   │   └── ...
│   │   ├── stores/
│   │   │   └── valuation.js     # Pinia store: package, config, result, loadPackage(), resetToSample()
│   │   └── services/
│   │       └── api.js           # Axios client: all API calls with timeouts
│   ├── vite.config.js           # Proxy /api → localhost:8000
│   ├── package.json
│   └── node_modules/
├── models/                      # ML model artifacts (git-ignored except manifest.json)
│   ├── manifest.json            # Registry of all models with status (stub/real)
│   ├── apex2/                   # APEX2 lookup tables (status: real)
│   │   ├── credit_rates.json
│   │   ├── rate_delta_rates.json
│   │   ├── ltv_rates.json
│   │   ├── loan_size_rates.json
│   │   └── metadata.json
│   ├── segmentation/            # Decision tree + structure + per-leaf loan parquets (status: real)
│   │   ├── segmentation_tree.pkl
│   │   ├── tree_structure.json
│   │   ├── segmentation_metadata.json
│   │   └── leaves/              # 75 parquet files (leaf_1_loans.parquet, ...)
│   ├── survival/                # KM survival curves keyed by leaf_id (status: real)
│   ├── prepayment/              # Prepayment curves + trained models (status: stub)
│   │   ├── freddie_payoff_model.pkl      # XGBoost trained on Freddie Mac payoff data
│   │   ├── freddie_payoff_metadata.json
│   │   ├── fnba_payoff_model.pkl         # XGBoost trained on internal FNBA data
│   │   └── fnba_payoff_metadata.json
│   ├── deq/                     # Delinquency model (status: stub)
│   ├── default/                 # Default/LGD model (status: stub)
│   └── recovery/                # Recovery model (status: stub)
└── inprogress/                  # Working data files (git-ignored)
    └── Pricing/
        ├── fnbaYear.xlsx        # Internal FNBA portfolio: 42K loans, ITIN flag
        ├── loan_tape_2_clean.xlsx # Sample non-QM tape: 305 loans
        └── freddieMacWithCollateralAndState.csv  # ~31M Freddie Mac loans
```

## Running Locally

```bash
# Backend
cd backend
source .venv/bin/activate    # venv already created with dependencies
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm run dev

# Generate/regenerate model stubs (run from backend/ with venv active)
python scripts/generate_stub_models.py

# Run tests
cd backend
pytest tests/ -v
```

**Note**: pyodbc requires `libodbc.so.2` (unixodbc). This is NOT available in the current WSL environment. Tests use a `conftest.py` mock that stubs out pyodbc. The DB-dependent package list endpoint (`GET /api/packages`) will fail without SQL Server — use the upload or sample package workflow instead.

## API Surface

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/packages` | List packages from SQL Server (requires DB) |
| `GET` | `/api/packages/{id}` | Get single package from DB |
| `POST` | `/api/packages/upload` | Upload Excel loan tape → returns `Package` |
| `POST` | `/api/valuations/run` | Run Monte Carlo valuation on inline package |
| `GET` | `/api/models/status` | Model registry status (all models + badges) |
| `POST` | `/api/prepayment/analyze` | APEX2 prepayment analysis on inline package |
| `GET` | `/api/segmentation/tree` | Full tree structure JSON for visualization |
| `GET` | `/api/segmentation/leaves` | Flat leaf summary list |
| `GET` | `/api/segmentation/leaf/{id}` | Leaf detail + survival curve |
| `GET` | `/api/segmentation/leaf/{id}/loans` | Paginated training loans (filter by source) |

### Key Request/Response Shapes

**Loan** (decimal conventions — this matters):
- `interest_rate`: decimal (0.072 = 7.2%)
- `ltv`: decimal (0.80 = 80%)
- `credit_score`: integer (300-850)
- `unpaid_balance`: dollars
- `original_term`, `remaining_term`, `loan_age`: months

**Upload endpoint** accepts `.xlsx`/`.xls` with flexible column matching. Columns are matched by partial case-insensitive name (e.g., "Current Balance" matches "balance", "FICO" matches "credit"). Rates and LTVs >1 are auto-divided by 100.

## Model System

The `ModelRegistry` singleton loads artifacts from `models/` at startup. Each model has a status in `manifest.json`:
- **stub**: Formula-based placeholder (yellow badge in UI)
- **real**: Trained on actual data (green badge in UI)

Current model statuses:
- `segmentation`: **real** — 75-leaf decision tree on 4.4M blended loans (FNBA + Freddie)
- `survival`: **real** — per-leaf Kaplan-Meier survival curves (360 months, censoring-aware)
- `apex2`: **real** — production APEX2 dimensional lookup tables
- `deq`, `default`, `recovery`, `prepayment`: **stub** — formula-based placeholders

### APEX2 Prepayment Model

The production prepayment model. Four dimensional lookup tables produce a prepayment speed multiplier per loan:
1. **Credit score** (9 bands: <576 through >=751)
2. **Rate delta** (note rate − 10Y Treasury, 7 bands)
3. **LTV** (5 bands: <75% through >=90%)
4. **Loan size** (8 bands: <$50K through $1M+)

Multiplier = average of 4 dimensions. Applied as extra principal payment in monthly projection. A 30-month seasoning ramp phases in the prepayment gradually for newly originated loans.

### Segmentation Tree (NEW — implemented)

Interpretable decision tree trained on blended data: 41,897 FNBA internal + 4.38M Freddie Mac (10% sample of 43.8M). Uses ALL loans including censored observations.

- **75 leaves**, max depth 11
- Features: `noteDateYear, creditScore, dti, ltv, interestRate, loanSize, stateGroup, ITIN, origCustAmortMonth`
- Per-leaf Kaplan-Meier survival curves (months 1-360, EMA smoothed, tail extrapolated)
- Training loan membership stored per leaf in parquet for management drill-through
- States pre-binned into 6 groups by median payoff time

**To retrain**: `cd backend && python scripts/train_segmentation_tree.py` (~100s)

**API endpoints**:
- `GET /api/segmentation/tree` — full tree structure for visualization
- `GET /api/segmentation/leaves` — flat leaf summary list
- `GET /api/segmentation/leaf/{id}` — leaf detail + survival curve
- `GET /api/segmentation/leaf/{id}/loans?source=fnba&page=1` — paginated training loans

### Bucket Assigner (4-tier fallback)

Used by the Monte Carlo engine to assign loans to buckets:
0. **Segmentation tree** `.apply()` if `models/segmentation/segmentation_tree.pkl` exists → returns leaf_id (1-75)
1. XGBoost `.predict()` if `models/survival/model.pkl` exists
2. JSON rule definitions from `models/survival/bucket_definitions.json`
3. Hardcoded 5-bucket rules (credit score + LTV thresholds)

## Key Gotchas

1. **Unit conversions between Loan model and APEX2/training data**:
   - Loan model stores rates as decimals (0.072), APEX2 uses percents (7.2) → multiply by 100
   - Same for LTV: decimal (0.80) → percent (80) → multiply by 100
   - `prepayment_analysis.py` already does this conversion at lines 250-251

2. **pyodbc mock**: `backend/tests/conftest.py` mocks pyodbc so tests run without ODBC drivers. All 113 tests pass in this WSL environment.

3. **Model directory location**: `models/` is at project root, NOT inside `backend/`. `MODEL_DIR` defaults to `../models` (relative to backend CWD). If running from a different directory, set `MODEL_DIR` in `.env`.

4. **Valuation timeout**: Monte Carlo simulations (500 sims × N loans × 3 scenarios) can take minutes. `api.js` has a 5-minute timeout for `runValuation` and `runPrepaymentAnalysis`.

5. **FICO column matching**: The tape parser uses partial matching for credit score columns ("credit score", "fico", "blended credit", "credit"). Some tapes may use column names that don't match — check `tape_parser.py:_COLUMN_PATTERNS` and add patterns if needed. Default is 700 if no credit column is found.

6. **Server restarts**: After code changes, kill the backend with `fuser -k 8000/tcp` if the port is held, then restart with `uvicorn app.main:app --reload`.

## ML Research Findings (Context for Next Phase)

Two XGBoost models have been trained and stored in `models/prepayment/`:

1. **Freddie Mac model** (`freddie_payoff_model.pkl`): Trained on 10% sample (~3.1M loans) of Freddie Mac conforming data. RMSE=36.7mo. Predicts total life from origination, NOT remaining life.

2. **FNBA internal model** (`fnba_payoff_model.pkl`): Trained on 42K internal loans from `fnbaYear.xlsx`. RMSE=38.7mo. Has ITIN flag as feature.

**Critical finding**: Both models were trained on `event==1` only (loans that paid off), creating survival bias. When applied to `loan_tape_2_clean.xlsx` (305 loans, avg 55 months old), all 305 are "survivors" — they've already outlived the model's predicted total life. This is a fundamental survival analysis issue, not a code bug.

**Population differences**:
- Freddie conforming: 21-month median payoff (people refi/sell fast at 3% rates)
- Internal Non-ITIN: 58.3% payoff rate, avg rate 8.5%
- Internal ITIN: 22.9% payoff rate, avg rate 8.3%
- Tape (loan_tape_2_clean): credit 762, rate 3.2%, LTV 57% — conventional quality with doc defects

**Rate environment dominance**: `noteDateYear` captures 33-48% of feature importance. A 3% loan in a 4.5% market has zero refi incentive regardless of credit quality.

## Remaining Work: Segmentation Tree

The full plan is at `~/.claude/plans/merry-marinating-zephyr.md`.

**Completed**:
1. Training script (`backend/scripts/train_segmentation_tree.py`) — 75 leaves, 4.4M loans, KM curves, loan traceability
2. Backend integration — ModelRegistry loading, 4-tier bucket assigner, 4 API endpoints with loan drill-through
3. Frontend — Segmentation nav link, SVG tree diagram, leaf summary table, leaf detail panel with survival curve canvas, paginated loan viewer with source filtering and CSV export

**Remaining**:
- **Granular scenario framework** — rate-shift and segment-specific stress overlays per leaf, replacing flat 3-scenario system
- **Verification** — compare effective life estimates against APEX2 amort plug on loan_tape_2_clean

### Feature Scale Conversions (for segmentation tree inference)

| Feature | Training Scale | Loan Model Scale | At Inference |
|---------|---------------|-----------------|--------------|
| `creditScore` | 300-850 | `credit_score` 300-850 | none |
| `interestRate` | percent (4.875) | `interest_rate` decimal (0.04875) | × 100 |
| `ltv` | percent (80) | `ltv` decimal (0.80) | × 100 |
| `loanSize` | dollars | `unpaid_balance` dollars | none |
| `noteDateYear` | year (2021) | `origination_date.year` | none |
| `dti` | ratio | `dti` (nullable) | default 36 |
| `ITIN` | 0/1 | n/a | default 0 |

### Open Questions

1. Should FNBA loans be upweighted so the tree pays more attention to our population?
2. Replace `noteDateYear` with `interestRate - currentTreasury` (rate delta) for forward-looking segmentation?
3. Start with 3 original scenarios + 2 rate-shift, or go straight to 12-scenario matrix?

### TODO: MC Engine ← APEX2 Prepay Integration

Feed the calibrated APEX2 time-varying prepay speed into the Monte Carlo engine so that bid analysis / ROE distributions reflect APEX2 assumptions instead of stub CPR.

**Files to modify:**

1. **`backend/app/models/simulation.py`** — Add `treasury_curve` (list of TreasuryPoint) and `prepay_source` enum (`"stub"` | `"apex2"`) to `SimulationConfig`. Default to `"stub"` for backward compatibility.

2. **`backend/app/simulation/cash_flow.py`** (`project_cash_flows`) — When `prepay_source == "apex2"`:
   - Import `interpolate_treasury`, `get_rate_delta_band`, `_get_apex2_tables` from `prepayment_analysis`
   - Each month: interpolate treasury → compute rate delta dim → average 4 dims → derive extra principal (replaces stub `marginal_prepay`)
   - The loan's 3 fixed APEX2 dims (credit, LTV, loan size) are computed once at the start of `project_cash_flows` and stored

3. **`backend/app/simulation/engine.py`** (`simulate_loan`) — Pass `treasury_curve` and `prepay_source` through to `project_cash_flows`. For MC scenarios, the treasury curve could be shifted (e.g., +100bp for recession scenario).

4. **`backend/app/services/simulation_service.py`** (`run_valuation`) — Accept treasury scenarios in the valuation request. When `prepay_source == "apex2"`, skip the stub prepay model entirely.

5. **`frontend/src/views/RunValuation.vue`** — Add a toggle for "APEX2 prepay" vs "Stub prepay" and treasury curve inputs (can reuse the scenario table pattern from PrepayMultiplierPanel).

**Key design decisions:**
- The APEX2 multiplier produces a **dollar amount** of extra principal per month (`pandi * (mult - 1)`), not a CPR. This replaces the `prepay_rate` and `prepay_amount` in the cash flow, NOT the state transition probabilities.
- The existing state machine (current → delinquent → default → recovered) remains unchanged. APEX2 prepay is additive on top of scheduled amortization for loans in "current" state.
- Scenario stress can be applied via treasury curve shifts: baseline = president's rate forecast, mild recession = +100bp, severe = +200bp. This replaces the current flat scenario multipliers for prepay.

**Test plan:**
- `test_apex2_prepay_in_cash_flow`: verify that `project_cash_flows` with `prepay_source="apex2"` uses APEX2-derived prepay amounts
- `test_apex2_vs_stub_differ`: confirm MC results with APEX2 prepay differ from stub
- `test_backward_compat`: default `prepay_source="stub"` produces identical results to current behavior
- `test_treasury_shift_stress`: recession treasury curve produces lower valuations

## Scripts Reference

| Script | Purpose | Run From |
|--------|---------|----------|
| `train_segmentation_tree.py` | **Primary**: Train 75-leaf tree on blended data (~100s) | `backend/` |
| `generate_stub_models.py` | Regenerate stub model artifacts in `models/` | `backend/` |
| `generate_apex2_summary.py` | Word doc: APEX2 review for management | `backend/` |
| `apex2_comparison.py` | Compare engine vs production APEX2 spreadsheet | `backend/` |
| `train_freddie_prepayment.py` | Train XGBoost on Freddie Mac data (research) | `backend/` |
| `strip_pii.py` | Remove PII from loan tapes | `backend/` |

All scripts assume `source .venv/bin/activate` has been run first.

## Testing

```bash
cd backend
pytest tests/ -v          # All ~113 tests
pytest tests/ -k tape     # Just tape parser tests
pytest tests/ -k upload   # Just upload route tests
```

Tests mock pyodbc via `conftest.py`. No external dependencies needed.

## Git & Collaboration

- Branch: `main` (primary)
- `.gitignore` excludes: `*.xlsx`, `*.csv`, `*.parquet`, `.venv*/`, `node_modules/`, `models/*` (except `.gitkeep`), `inprogress/`, `reports/`, `.idea/`
- Data files (`inprogress/Pricing/`) are local-only. Share via Teams/OneDrive, not git.
- `models/manifest.json` IS tracked. Model artifacts (`.pkl`, `.parquet`, `.json` inside model subdirs) are generated by scripts.
