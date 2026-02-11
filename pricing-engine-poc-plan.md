# Pricing Engine POC — Build Plan

> **Project:** pricing-engine (part of the larger profit-loop initiative)
> **Target:** Management demo in ~5 weeks
> **Builder:** Claude Code (prescriptive — generate the codebase)
> **Primary output:** ROE of expected payment stream for a loan package
> **Key constraint:** Andy T (Data Scientist) commits models to a separate repo; the app pipeline consumes them automatically-ish

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Vue 3 Frontend (Vite)                                              │
│  - Package selector / loan list                                     │
│  - Interactive parameter inputs (CoC, scenarios)                    │
│  - ROE results, distributions, per-loan drill-down                  │
│  - Visualizations (cash flows, survival curves, scenario comparison)│
└────────────────────────┬────────────────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────────────────┐
│  Python / FastAPI Backend                                           │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────────────┐ │
│  │ Package &    │ │ Segmentation │ │ Simulation Engine            │ │
│  │ Loan Loader  │→│ (Bucket      │→│ - Survival curves (real)    │ │
│  │ (SQL Server) │ │  Assignment) │ │ - DEQ/Default/Recovery (stub)│ │
│  └──────────────┘ └──────────────┘ │ - Cash flow projection      │ │
│                                     │ - Monte Carlo (scenarios +  │ │
│  ┌──────────────┐                   │   stochastic)               │ │
│  │ Model Loader │                   │ - PV & ROE calculation      │ │
│  │ (from Andy's │──────────────────→│                             │ │
│  │  model repo) │                   └─────────────────────────────┘ │
│  └──────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  MS SQL Server      │
              │  - 43M loan dataset │
              │  - Package tables   │
              │  - Model outputs    │
              │    (curves, buckets)│
              └─────────────────────┘

              ┌─────────────────────┐
              │  Andy's Model Repo  │
              │  (separate git)     │
              │  - Trained models   │
              │  - Bucket defs      │
              │  - Survival curves  │
              └─────────────────────┘
```

---

## Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | Vue 3 (Composition API) + Vite | Charts TBD (Chart.js or ECharts) — pick what works, will eventually go to PowerBI |
| Backend | Python 3.11+ / FastAPI | Async where beneficial |
| Database | MS SQL Server | Already has 43M loans loaded. Use `pyodbc` or `aioodbc` |
| Models | XGBoost survival model (Andy) | Loaded from file, tree structure = bucket definitions |
| Simulation | NumPy / SciPy | Vectorized Monte Carlo |
| Containerization | Docker + docker-compose | Backend + frontend + (SQL Server is external) |

---

## Conventions

- **Structure:** Theme → Epic → Task
- **Task IDs:** `T{theme}.E{epic}.T{task}` (e.g., `T1.E1.T1`)
- **Priority:** P1 (Critical for demo), P2 (Important), P3 (Nice to have)
- **Status markers:** `[STUB]` = placeholder with sensible defaults, build out later. `[REAL]` = production-intent logic.
- **Andy's deliverables** are called out explicitly. The pipeline should work with stub/mock models before Andy's real models land.

---

## Phase 1: Foundation

**Goal:** Project scaffolding, DB connectivity, data models, API skeleton. Everything compiles and runs, even if it does nothing useful yet.

### Theme 1: Project Setup

#### Epic 1.1: Repository & Scaffolding

**T1.E1.T1 — Initialize backend project** (P1)
```
pricing-engine/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Settings via pydantic-settings (DB conn, model paths)
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes/
│   │   │   │   ├── packages.py  # Package endpoints
│   │   │   │   ├── valuation.py # Valuation/simulation endpoints
│   │   │   │   ├── models.py    # Model info/status endpoints
│   │   │   │   └── health.py    # Health check
│   │   │   └── deps.py          # Shared dependencies
│   │   ├── models/              # Pydantic schemas (NOT ML models)
│   │   │   ├── loan.py
│   │   │   ├── package.py
│   │   │   ├── valuation.py
│   │   │   └── simulation.py
│   │   ├── services/            # Business logic
│   │   │   ├── package_service.py
│   │   │   ├── segmentation_service.py
│   │   │   ├── simulation_service.py
│   │   │   └── model_service.py
│   │   ├── ml/                  # ML model loading & inference
│   │   │   ├── model_loader.py
│   │   │   ├── bucket_assigner.py
│   │   │   └── curve_provider.py
│   │   ├── db/
│   │   │   ├── connection.py    # SQL Server connection pool
│   │   │   └── queries/         # Raw SQL or query builders
│   │   │       ├── loans.py
│   │   │       └── packages.py
│   │   └── simulation/          # Monte Carlo engine
│   │       ├── engine.py
│   │       ├── cash_flow.py
│   │       ├── scenarios.py
│   │       └── state_transitions.py
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   └── (see T1.E1.T2)
├── docker-compose.yml
└── README.md
```
- Use `pydantic-settings` for config, load from `.env`
- Set up CORS for local Vue dev server
- Health check endpoint returns DB connectivity status + loaded model info

**T1.E1.T2 — Initialize frontend project** (P1)
```
frontend/
├── src/
│   ├── App.vue
│   ├── main.js
│   ├── router/
│   │   └── index.js
│   ├── views/
│   │   ├── PackageList.vue       # Select a package
│   │   ├── PackageValuation.vue  # Main valuation view
│   │   └── ModelStatus.vue       # Which models are loaded, real vs stub
│   ├── components/
│   │   ├── LoanTable.vue
│   │   ├── ParameterPanel.vue    # Interactive inputs (CoC, scenario selection)
│   │   ├── ResultsSummary.vue    # ROE headline, key metrics
│   │   ├── CashFlowChart.vue
│   │   ├── DistributionChart.vue
│   │   └── ScenarioComparison.vue
│   ├── services/
│   │   └── api.js                # Axios wrapper for backend calls
│   ├── stores/
│   │   └── valuation.js          # Pinia store for valuation state
│   └── assets/
├── package.json
├── vite.config.js
├── Dockerfile
└── index.html
```
- Vue 3 + Composition API + Vite
- Pinia for state management
- Vue Router for navigation
- Axios for API calls
- Chart library: start with Chart.js (switch if needed)

**T1.E1.T3 — Docker Compose setup** (P1)
- Services: `backend` (FastAPI on port 8000), `frontend` (Vite dev on port 3000)
- SQL Server is external — connection string via env var
- Volume mount for model files (so Andy's models can be dropped in without rebuild)
- Volume mount: `./models:/app/models` on backend container

#### Epic 1.2: Database Connectivity & Data Models

**T1.E2.T1 — SQL Server connection** (P1)
- Use `pyodbc` with connection pooling
- Async wrapper if using `aioodbc`, otherwise sync is fine for POC
- Connection string from config: `SQLSERVER_CONN_STRING`
- Test query on startup (health check)
- Handle connection failures gracefully with retry

**T1.E2.T2 — Loan data model & query** (P1)
- Pydantic model for `Loan`:
  ```python
  class Loan(BaseModel):
      loan_id: str
      unpaid_balance: float
      interest_rate: float
      original_term: int        # months
      remaining_term: int       # months
      loan_age: int             # months since origination
      credit_score: int
      ltv: float                # loan-to-value ratio
      dti: float                # debt-to-income ratio
      property_type: str        # SFR, Condo, Multi, etc.
      occupancy_type: str       # Owner, Investment, Second Home
      state: str                # US state (for locale-specific costs)
      origination_date: date
      # Add fields as discovered in actual SQL schema
  ```
- SQL query to fetch loans by package ID
- NOTE: Actual column names will need mapping to the SQL Server schema. Include a `COLUMN_MAP` dict in `db/queries/loans.py` that can be easily updated once the real schema is confirmed.

**T1.E2.T3 — Package data model & query** (P1)
- Pydantic model for `Package`:
  ```python
  class Package(BaseModel):
      package_id: str
      name: str
      loan_count: int
      total_upb: float          # total unpaid balance
      purchase_price: Optional[float]  # if we bought it — for comparison
      purchase_date: Optional[date]
      loans: List[Loan] = []
  ```
- SQL query to list available packages
- SQL query to fetch package detail + associated loans
- NOTE: Package schema in SQL Server TBD. Start with a stub table or view. Include a `setup_package_table.sql` script that creates a minimal package table if one doesn't exist, with a few sample package IDs pointing to real loan groups.

---

## Phase 2: Model Pipeline — Andy's "Commit and Go" Workflow

**Goal:** Define the contract between Andy's model repo and the app. The app loads whatever model is present, falls back to stubs. Andy commits artifacts, the app picks them up.

### Theme 2: Model Integration

#### Epic 2.1: Model Contract & Loading

**T2.E1.T1 — Define model artifact contract** (P1)
Andy's repo should produce a directory structure like:
```
models/
├── manifest.json              # Metadata: model version, date, metrics, type
├── survival/
│   ├── model.pkl              # Trained XGBoost model (joblib or pickle)
│   ├── bucket_definitions.json # Tree structure → bucket rules
│   ├── survival_curves.parquet # bucket_id → monthly survival probabilities
│   └── metadata.json          # Training info, feature list, validation metrics
├── deq/                       # [STUB initially, same structure when real]
│   └── ...
├── default/                   # [STUB initially]
│   └── ...
└── recovery/                  # [STUB initially]
    └── ...
```

`manifest.json`:
```json
{
  "version": "0.1.0",
  "created_at": "2026-02-10T12:00:00Z",
  "models": {
    "survival": {"status": "real", "version": "0.1.0", "metrics": {"c_statistic": 0.72}},
    "deq": {"status": "stub", "version": "0.0.1"},
    "default": {"status": "stub", "version": "0.0.1"},
    "recovery": {"status": "stub", "version": "0.0.1"}
  }
}
```

`bucket_definitions.json`:
```json
{
  "n_buckets": 20,
  "features_used": ["credit_score", "ltv", "dti", "interest_rate", "loan_age", "property_type", "occupancy_type", "state"],
  "rules": [
    {
      "bucket_id": 0,
      "description": "High credit, low LTV owner-occupied",
      "conditions": [
        {"feature": "credit_score", "operator": ">=", "value": 740},
        {"feature": "ltv", "operator": "<", "value": 0.6}
      ]
    }
  ]
}
```
NOTE: The `rules` format above is illustrative. In practice, Andy may export the XGBoost tree structure directly (e.g., `model.get_booster().trees_to_dataframe()`), and the bucket assigner would use the trained model's `.predict()` to assign leaf node IDs. The rules JSON is a fallback for interpretability / documentation. Support BOTH approaches:
1. **Direct model prediction** (preferred): Load `model.pkl`, call `predict(loan_features)` → get leaf/bucket ID
2. **Rules-based fallback**: Parse `bucket_definitions.json` if model file isn't available

**T2.E1.T2 — Model loader service** (P1)
- On startup, scan `MODEL_DIR` (env var, defaults to `./models/`)
- Read `manifest.json` to understand what's available
- Load each model that's present; use stub for anything missing
- Expose model status via API endpoint (`GET /api/models/status`)
- Log clearly: `"Survival model: REAL v0.1.0 (c_stat=0.72)"` / `"DEQ model: STUB v0.0.1"`

**T2.E1.T3 — Bucket assigner** (P1)
- Takes a `Loan` → returns `bucket_id: int`
- Strategy 1 (preferred): Use loaded XGBoost model, call `model.predict()` to get leaf node ID
- Strategy 2 (fallback): Apply rules from `bucket_definitions.json`
- Must handle missing features gracefully (use defaults, log warning)

**T2.E1.T4 — Curve provider** (P1)
- Given a `bucket_id`, return the survival curve (monthly probabilities)
- Load from `survival_curves.parquet` (preloaded into memory on startup)
- Return as dict: `{month: survival_probability}` for the loan's remaining term
- If bucket_id not found, fall back to an "average" curve and log warning

#### Epic 2.2: Stub Models (Work Without Andy)

**T2.E2.T1 — Stub survival model** (P1)
- Generate reasonable survival curves for ~5 risk tiers
- Base curve: ~95% survival at month 12, ~80% at month 60, ~60% at month 120
- Better buckets survive longer, worse buckets faster prepay/default
- Bucket assignment: Simple rules on credit_score × LTV
  - Bucket 0: credit >= 740, LTV < 60% (best)
  - Bucket 1: credit >= 740, LTV >= 60%
  - Bucket 2: credit 680-739, LTV < 80%
  - Bucket 3: credit 680-739, LTV >= 80%
  - Bucket 4: credit < 680 (worst)
- Generate `manifest.json`, `bucket_definitions.json`, `survival_curves.parquet` in stub format
- Create a script: `backend/scripts/generate_stub_models.py` that produces the full model directory

**T2.E2.T2 — Stub DEQ model** (P2) `[STUB]`
- P(30+ DPD) by bucket, decreasing over time (seasoning)
- Bucket 0: 1% base rate, Bucket 4: 8% base rate
- Simple: `deq_rate = base_rate * exp(-0.02 * loan_age)`

**T2.E2.T3 — Stub default model** (P2) `[STUB]`
- P(Default | Delinquent) by severity:
  - 30 DPD: 5% chance of default
  - 60 DPD: 15%
  - 90+ DPD: 40%
- Loss severity: 30% of unpaid balance (varies slightly by state)
- Recovery timeline: 18 months average

**T2.E2.T4 — Stub recovery/liquidation model** (P2) `[STUB]`
- Recovery rate: 65% of property value (post-foreclosure)
- Foreclosure timeline by state: judicial (~18mo) vs non-judicial (~6mo)
- Simple state lookup table
- Liquidation costs: 10% of property value

**T2.E2.T5 — Stub cost of capital** (P2) `[STUB]`
- Default flat rate: configurable, default 8%
- Named scenarios override:
  - Baseline: 8%
  - Mild recession: 10%
  - Severe recession: 14%
  - Low rate: 5%
- NOTE: Eventually this becomes a curve (term structure), correlated with macro scenarios

---

## Phase 3: Simulation Engine

**Goal:** Monte Carlo engine that takes a loan + its bucket/curves → projects cash flows → calculates PV and ROE. This is the heart of the system.

### Theme 3: Simulation

#### Epic 3.1: Cash Flow Projection

**T3.E1.T1 — Single-loan cash flow projector** (P1)
- Input: `Loan` + survival curve + DEQ rates + default model + recovery model + cost of capital
- Output: Monthly cash flow array over remaining term:
  ```python
  class MonthlyCashFlow(BaseModel):
      month: int
      scheduled_payment: float    # P&I from amortization schedule
      survival_probability: float # P(still paying this month)
      expected_payment: float     # scheduled * survival_prob
      deq_probability: float      # P(delinquent)
      default_probability: float  # P(default this month)
      expected_loss: float        # default_prob * loss_severity * balance
      expected_recovery: float    # recovery from prior defaults
      servicing_cost: float       # monthly servicing expense
      net_cash_flow: float        # expected_payment - expected_loss + expected_recovery - servicing_cost
      discount_factor: float      # 1 / (1 + CoC/12)^month
      present_value: float        # net_cash_flow * discount_factor
  ```
- Amortization schedule: standard fixed-rate mortgage math
- Each month: apply survival curve, DEQ transitions, default probability
- Net cash flow = expected payments − expected losses + recoveries − servicing

**T3.E1.T2 — Loan state transition model** (P1)
- Markov-style monthly transitions:
  ```
  Current → Current (survive & pay)
  Current → Prepaid (survival model)
  Current → 30 DPD (DEQ model)
  30 DPD → Current (cure rate)
  30 DPD → 60 DPD
  60 DPD → Current (cure rate)
  60 DPD → 90 DPD
  90+ DPD → Default (default model)
  Default → Recovery → Liquidation
  ```
- Transition probabilities sourced from respective models
- Track state probabilities (not discrete states) for expected value calculation
- For Monte Carlo: sample discrete paths using the probabilities

#### Epic 3.2: Monte Carlo Engine

**T3.E2.T1 — Scenario definitions** (P1)
- Named scenarios with macro parameter sets:
  ```python
  SCENARIOS = {
      "baseline": {
          "cost_of_capital": 0.08,
          "unemployment_shock": 0.0,
          "hpi_change": 0.02,       # annual
          "rate_environment": "stable"
      },
      "mild_recession": {
          "cost_of_capital": 0.10,
          "unemployment_shock": 0.03,
          "hpi_change": -0.05,
          "rate_environment": "rising"
      },
      "severe_recession": {
          "cost_of_capital": 0.14,
          "unemployment_shock": 0.07,
          "hpi_change": -0.20,
          "rate_environment": "volatile"
      },
      "low_rate": {
          "cost_of_capital": 0.05,
          "unemployment_shock": -0.01,
          "hpi_change": 0.05,
          "rate_environment": "falling"
      }
  }
  ```
- For POC: macro variables modify model outputs via simple multipliers
  - Higher unemployment → higher DEQ rates (e.g., `deq_rate *= 1 + unemployment_shock * 2`)
  - Negative HPI → higher loss severity, lower recovery
  - Rate environment → affects prepay speeds (falling rates = more prepay)
- `[STUB]` These multiplier relationships. Document them clearly for future calibration.

**T3.E2.T2 — Monte Carlo runner** (P1)
- For a single loan:
  1. For each named scenario + N stochastic variations:
     - Apply scenario parameters to model outputs
     - Add stochastic noise (e.g., jitter CoC ±1%, DEQ rates ±20%)
     - Run cash flow projection
     - Calculate PV of net cash flows
  2. Collect distribution of PVs
- For a package:
  1. For each simulation run: macro parameters are **consistent across all loans** in the package
  2. Run each loan through its bucket-specific curves with shared macro params
  3. Sum loan PVs → package PV for that run
  4. Collect distribution of package PVs
- Vectorize with NumPy: process all months for a loan in one array operation
- Target: 50-250 loans × 100-1000 simulations × 360 months should complete in seconds
- Config:
  ```python
  class SimulationConfig(BaseModel):
      n_simulations: int = 500           # stochastic runs per scenario
      scenarios: List[str] = ["baseline", "mild_recession", "severe_recession"]
      include_stochastic: bool = True
      stochastic_seed: Optional[int] = 42  # reproducibility
  ```

**T3.E2.T3 — ROE calculation** (P1)
- **This is the primary output metric.**
- ROE = Return on Equity of the expected payment stream
- Calculation:
  ```python
  # For a package:
  purchase_price = package.purchase_price  # what we paid / would pay
  # or: purchase_price = sum of loan unpaid balances * bid_percentage (input)

  # From simulation:
  expected_npv = mean(simulated_package_pvs)  # expected PV of all cash flows

  # ROE (simplified for POC):
  total_expected_return = expected_npv - purchase_price
  # Annualized:
  weighted_avg_life = calculate_wal(expected_cash_flows)  # in years
  annual_roe = total_expected_return / purchase_price / weighted_avg_life

  # Also compute:
  # - ROE by scenario
  # - ROE distribution (from Monte Carlo)
  # - ROE percentiles (5th, 25th, 50th, 75th, 95th)
  ```
- NOTE: The ROE formula above is a starting point. The actual calculation may be more nuanced (IRR-based, equity-adjusted, etc.). Build it modular so the calc can be swapped.
- Expose as a clear, pluggable function: `calculate_roe(cash_flows, purchase_price, method="simple")`

**T3.E2.T4 — Simulation results model** (P1)
```python
class LoanValuationResult(BaseModel):
    loan_id: str
    bucket_id: int
    expected_pv: float
    pv_by_scenario: Dict[str, float]
    pv_distribution: List[float]       # all simulation PVs
    pv_percentiles: Dict[str, float]   # p5, p25, p50, p75, p95
    monthly_cash_flows: List[MonthlyCashFlow]  # expected (mean) path
    model_status: Dict[str, str]       # which models were real vs stub

class PackageValuationResult(BaseModel):
    package_id: str
    package_name: str
    loan_count: int
    total_upb: float
    purchase_price: Optional[float]
    expected_npv: float
    roe: float
    roe_annualized: float
    roe_by_scenario: Dict[str, float]
    roe_distribution: List[float]
    roe_percentiles: Dict[str, float]
    npv_by_scenario: Dict[str, float]
    npv_distribution: List[float]
    npv_percentiles: Dict[str, float]
    loan_results: List[LoanValuationResult]
    simulation_config: SimulationConfig
    model_manifest: dict               # what models were used, versions, real vs stub
    computed_at: datetime
```

---

## Phase 4: Package Valuation API

**Goal:** Wire it all together. Load a package from SQL Server, run each loan through segmentation + simulation, aggregate results.

### Theme 4: End-to-End Pipeline

#### Epic 4.1: Package Loading

**T4.E1.T1 — Package list endpoint** (P1)
- `GET /api/packages` → list available packages with summary stats
- Query SQL Server for package table/view
- Return: `[{package_id, name, loan_count, total_upb, purchase_price, purchase_date}]`

**T4.E1.T2 — Package detail endpoint** (P1)
- `GET /api/packages/{package_id}` → package info + loan list
- Fetch all loans in package from SQL Server
- Return full `Package` model with `loans` populated

#### Epic 4.2: Valuation Endpoint

**T4.E2.T1 — Run valuation endpoint** (P1)
- `POST /api/valuations/run`
- Request body:
  ```json
  {
    "package_id": "PKG-2026-001",
    "config": {
      "n_simulations": 500,
      "scenarios": ["baseline", "mild_recession", "severe_recession"],
      "cost_of_capital_override": null,
      "bid_percentage": 0.85
    }
  }
  ```
- Pipeline:
  1. Load package + loans from DB
  2. For each loan: assign bucket → get survival curve
  3. Run Monte Carlo simulation (all loans, shared macro params per run)
  4. Aggregate to package level
  5. Calculate ROE
  6. Return `PackageValuationResult`
- Should handle 50-250 loans in < 30 seconds (target < 10s)
- Return progress indicator for frontend (or use WebSocket — P3)

**T4.E2.T2 — Compare to actual purchase** (P2)
- If `package.purchase_price` is set:
  - Show model valuation vs. actual purchase price
  - Delta and percentage difference
  - "We paid $X, model says it's worth $Y" — the killer demo moment
- If pricing a new package:
  - User enters bid percentage or absolute price
  - Show ROE at that price point

**T4.E2.T3 — Sensitivity analysis endpoint** (P2)
- `POST /api/valuations/sensitivity`
- Vary one parameter (e.g., CoC from 5% to 15% in steps) while holding others fixed
- Return array of ROE values at each parameter level
- Frontend renders as a sensitivity chart

---

## Phase 5: Frontend / UI

**Goal:** Vue app that lets the user pick a package, tweak parameters, run valuation, and see results. Interactive and demo-ready.

### Theme 5: User Interface

#### Epic 5.1: Package Selection & Loading

**T5.E1.T1 — Package list view** (P1)
- Route: `/packages`
- Table of available packages: name, loan count, UPB, purchase price, date
- Click to navigate to valuation view
- Search/filter if more than a handful of packages

**T5.E1.T2 — Loan detail table** (P2)
- Within package view: expandable table of loans
- Columns: loan_id, balance, rate, credit score, LTV, bucket assignment
- Sortable, filterable
- Color-code by bucket for visual segmentation

#### Epic 5.2: Parameter Panel & Valuation Controls

**T5.E2.T1 — Interactive parameter panel** (P1)
- Sidebar or top panel with:
  - Cost of capital input (slider + number input, default 8%)
  - Bid percentage (slider, default 85% of UPB)
  - Scenario checkboxes (baseline, mild recession, severe recession, low rate)
  - Number of simulations (dropdown: 100, 500, 1000)
- "Run Valuation" button
- Parameters persist in Pinia store, URL query params for shareability (P3)

**T5.E2.T2 — Loading state & progress** (P1)
- Show spinner / progress bar while valuation runs
- Display estimated time based on loan count + simulation count
- Handle errors gracefully (DB down, model not loaded, etc.)

#### Epic 5.3: Results Display

**T5.E3.T1 — ROE headline card** (P1)
- Big, prominent display:
  - **Expected ROE: 12.3%** (annualized)
  - ROE range: 8.1% (5th percentile) to 16.7% (95th percentile)
  - Model NPV vs. Purchase Price (if available)
  - Delta: "+$245,000 (model says we overpaid)" or "model confirms fair price"
- Color-coded: green if favorable, red if unfavorable

**T5.E3.T2 — Scenario comparison view** (P1)
- Side-by-side or table:
  | Scenario | NPV | ROE | Δ vs Purchase |
  |----------|-----|-----|---------------|
  | Baseline | $X | 12% | +$200K |
  | Mild Recession | $Y | 8% | -$50K |
  | Severe Recession | $Z | 2% | -$400K |
- Chart: bar chart of ROE by scenario

**T5.E3.T3 — Distribution chart** (P1)
- Histogram of simulated ROE values
- Mark percentiles (5th, 25th, 50th, 75th, 95th)
- Mark purchase price / breakeven on the chart
- Show probability of loss (% of simulations where NPV < purchase price)

**T5.E3.T4 — Cash flow projection chart** (P2)
- Line chart: monthly expected cash flows over time
- Stacked area: payments, losses, recoveries, servicing costs
- Toggle by scenario
- Show where the "crossover" point is (cumulative cash flow > purchase price)

**T5.E3.T5 — Per-loan drill-down** (P2)
- Click a loan in the table → see its individual:
  - Bucket assignment + reasoning
  - Survival curve
  - Cash flow projection
  - Contribution to package value
- Helps explain "why is this package priced this way?"

#### Epic 5.4: Model Transparency

**T5.E4.T1 — Model status indicator** (P1)
- Persistent badge/banner showing:
  - Survival: ✅ REAL (v0.1.0, trained on 43M loans)
  - DEQ: ⚠️ STUB (sensible defaults)
  - Default: ⚠️ STUB
  - Recovery: ⚠️ STUB
- Clicking opens detail panel with model metadata
- Critical for demo credibility: "we're transparent about what's real"

---

## Phase 6: Demo Polish & Comparison

**Goal:** Get a real package loaded, compare model output to actual purchase, make it presentation-ready.

### Theme 6: Demo Readiness

#### Epic 6.1: Real Data Integration

**T6.E1.T1 — Load the recently purchased package** (P1)
- Identify the package bought ~2 months ago in SQL Server
- Ensure all loan data maps correctly to the data model
- Set `purchase_price` on the package record
- Verify bucket assignments make sense for the loans in the package

**T6.E1.T2 — Load the package currently being priced** (P1)
- If available: load the package under current pricing evaluation
- Run valuation → compare to whatever the current pricing method produces
- Side-by-side: "Current method says $X, model says $Y"

**T6.E1.T3 — Swap in Andy's real model** (P1)
- When Andy delivers: drop his model artifacts into the models directory
- Restart backend (or hit a reload endpoint — P2)
- Verify: bucket assignments change, curves are different, results update
- Compare stub vs. real model outputs for the demo package

#### Epic 6.2: Presentation Polish

**T6.E2.T1 — Demo walkthrough route** (P2)
- A guided view that walks through the pipeline step by step:
  1. "Here's our package of 127 loans"
  2. "Each loan gets assigned to a risk bucket by the ML model"
  3. "We project cash flows using survival curves + scenario assumptions"
  4. "Monte Carlo gives us a distribution of outcomes"
  5. "Result: Expected ROE of X% with Y% confidence"
- Not strictly necessary but makes for a smoother demo

**T6.E2.T2 — Export results** (P3)
- Export valuation results to JSON or CSV
- Eventually: push to PowerBI (out of scope for POC)

**T6.E2.T3 — Error handling & edge cases** (P1)
- What if a loan has missing data? (Skip + warn, don't crash)
- What if SQL Server is slow? (Timeouts, caching)
- What if model file is corrupt? (Fall back to stub, alert)
- Test with the real package data — edge cases will surface

---

## Andy T's Deliverables (Parallel Track)

Andy works in a **separate git repo** (`pricing-engine-models` or similar). His deliverables feed into the model directory consumed by the app.

### What Andy Needs to Produce

1. **Trained XGBoost survival model** (`model.pkl`)
   - Trained on the 43M loan dataset
   - Target: time-to-event (prepayment or default)
   - ~20 leaf nodes for POC (expandable to 40-50 later)

2. **Bucket definitions** (`bucket_definitions.json`)
   - Tree structure exported as interpretable rules
   - Feature list and split points

3. **Survival curves per bucket** (`survival_curves.parquet`)
   - For each bucket_id: monthly survival probabilities
   - Empirical curves from loans landing in each leaf node

4. **Model metadata** (`metadata.json`)
   - Validation metrics (C-statistic, etc.)
   - Training data summary
   - Feature importance

5. **Manifest** (`manifest.json`)
   - Version, date, model status

### Andy's Workflow

```
Andy trains model → exports artifacts → pushes to model repo
                                              ↓
App team pulls model repo → copies to models/ directory → restarts backend
                                              ↓
Backend loads real model → replaces stubs → valuation uses real curves
```

For the POC, "pulls model repo → copies" is manual. Post-POC: automate with CI/CD or a watcher.

### Backtesting (Andy's Secondary Track)

Andy is also working on backtesting methodology. This is parallel and doesn't block the POC pipeline, but results feed into demo credibility:
- "We backtested against internal loans and the model predicted within X% of actual outcomes"
- Backtesting results can be displayed in the Model Status view (T5.E4.T1)

---

## Build Order (Suggested Sequence for Claude Code)

```
Week 1:  Phase 1 (Foundation) + Phase 2 Epic 2.2 (Stub models)
         → Result: App runs, connects to DB, loads stub models, serves API

Week 2:  Phase 2 Epic 2.1 (Model loader) + Phase 3 (Simulation engine)
         → Result: Can simulate a single loan, get PV and cash flows

Week 3:  Phase 4 (Package valuation API) + Phase 5 Epics 5.1-5.2
         → Result: End-to-end: pick package → run valuation → see results

Week 4:  Phase 5 Epics 5.3-5.4 (Results display, transparency)
         → Result: Full UI with charts, distributions, model status

Week 5:  Phase 6 (Demo polish, real data, Andy's model integration)
         → Result: Demo-ready with real package comparison
```

---

## Open Questions & Assumptions

1. **SQL Server schema:** Exact table/column names for loans and packages TBD. The `COLUMN_MAP` pattern in `db/queries/loans.py` handles this — update once confirmed.
2. **ROE formula:** Starting with simple (NPV − Price) / Price / WAL. May need IRR-based or equity-adjusted calc. Built as pluggable function.
3. **Andy's model format:** Assuming joblib/pickle for XGBoost + parquet for curves. Confirm with Andy.
4. **Package definition:** Assuming a package table exists or can be created in SQL Server with loan-to-package mapping.
5. **Authentication:** None for POC. Add if needed for demo environment.
6. **Concurrency:** Single-user for POC. No need for job queuing or async simulation management.
7. **Cost of capital curve:** Flat rate for POC. Term structure is a post-POC enhancement.
8. **Macro scenario calibration:** Multiplier relationships are `[STUB]`. Calibrate with historical data post-POC.
9. **Additional ROE/valuation metrics:** Start with ROE. More metrics (IRR, duration, convexity) can be added as the team identifies needs.
