# CLAUDE.md — Pricing Engine POC

## Project Purpose
Loan pricing engine POC: ingest loan packages from SQL Server, run Monte Carlo simulations with ML-driven transition probabilities, and present interactive valuations via a web UI.

## Architecture
- **Backend**: FastAPI (Python 3.12) at port 8000, all routes under `/api/`
- **Frontend**: Vue 3 + Vite at port 3000, proxies `/api` to backend
- **Database**: External SQL Server via pyodbc (sync)
- **ML Models**: Stored in `models/` directory (`.pkl`/`.joblib`)

## Project Structure
```
backend/
  app/
    api/routes/      # FastAPI route modules
    api/deps.py      # Dependency injection (DB connections)
    db/connection.py  # DatabasePool (pyodbc)
    db/queries/       # Raw SQL query functions
    models/           # Pydantic schemas
    services/         # Business logic
    ml/               # Model loading, bucket assignment, curves
    simulation/       # Monte Carlo engine, cash flows, scenarios
    config.py         # pydantic-settings configuration
    main.py           # FastAPI app entry point
  tests/              # pytest tests
frontend/
  src/
    views/            # Page-level Vue components
    components/       # Reusable UI components
    stores/           # Pinia state stores
    services/api.js   # Axios API wrapper
    router/index.js   # Vue Router config
models/               # ML model artifacts (git-ignored)
```

## Running Locally
```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # then edit with your SQL Server credentials
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Docker
docker compose up --build
```

## Testing
```bash
cd backend
pytest tests/ -v
```

## Key Conventions
- All API routes prefixed with `/api/`
- Pydantic models in `app/models/`, DB queries in `app/db/queries/`
- Services coordinate between DB queries and API responses
- Stub files exist for future phases — imports work across the project from day one
