# ReconAI — Local Setup & Execution Guide

Document Version: 1.0  
Last Updated: 2026-08-12  

This guide provides step-by-step instructions for installing, configuring, running, and testing the **ReconAI Agentic Platform for Accounting Automation** on your local workstation.

---

## 📋 Prerequisites

Before starting, ensure you have installed:

- **Docker & Docker Compose**: (v20.10+) for running PostgreSQL database container.
- **Python**: 3.11 or 3.12.
- **`uv` / `pip`**: Package manager (`uv` recommended for fast dependency resolution).
- **Node.js & `npm`**: Node.js 18+ for running React Vite frontend.
- **Git**: For version control.

---

## ⚙️ Environment Configuration (`.env`)

Clone the repository and prepare your `.env` configuration:

```bash
# Navigate to workspace root
cd recon-ai

# Copy template environment file
cp .env.example .env
```

### `.env` File Parameters:

```env
# Database Settings
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=recon_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/recon_db

# LLM API Provider Keys (Required for live AI agent processing)
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# App Settings
BACKEND_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
ENVIRONMENT=development
```

> 💡 **Note**: If `GEMINI_API_KEY` or `OPENAI_API_KEY` is not provided, the platform will fallback to deterministic guardrails and pre-packaged demo dataset extractions.

---

## 🗄️ 1. Start PostgreSQL Database

Start local PostgreSQL container using Docker Compose:

```bash
# From workspace root
docker compose up -d
```

Verify PostgreSQL container status:
```bash
docker compose ps
```

---

## 🐍 2. Backend Setup & Run (FastAPI)

```bash
cd backend

# Option A: Using `uv` (Recommended)
uv sync
uv run alembic upgrade head
uv run python app/db/seed.py

# Start FastAPI development server
uv run uvicorn app.main:app --reload --port 8000
```

```bash
# Option B: Using standard Python venv & pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run migrations & seed data
alembic upgrade head
python app/db/seed.py

# Start FastAPI dev server
uvicorn app.main:app --reload --port 8000
```

FastAPI Interactive API Documentation:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## ⚛️ 3. Frontend Setup & Run (React + Vite)

Open a new terminal window:

```bash
cd frontend

# Install Node.js dependencies
npm install

# Start Vite development server
npm run dev
```

Application User Interface:
- **Web App**: [http://localhost:5173](http://localhost:5173)

The frontend uses browser-based routing. Its primary routes are `/documents`, `/review`,
`/ledger`, `/reconciliation`, and `/audit`; entity detail routes can be bookmarked and opened
directly. The Vite development server handles these deep links automatically.

### Production SPA fallback

When deploying the production build, configure the frontend web server to serve
`frontend/dist/index.html` for every non-file, non-API route. For example, an Nginx frontend
location should use `try_files $uri $uri/ /index.html;`, while `/api/` must continue to proxy to
FastAPI. Without this fallback, refreshing a deep link such as `/review/<id>` or
`/audit/document/<id>` will return a web-server 404 before React can load.

---

## 📁 4. Generating Demo Sample Dataset

To seed or regenerate realistic mock invoices, receipts, and CSV bank statements:

```bash
# Run demo dataset generator script
python3 demo-data/create_demo_dataset.py
```

Generated sample files located in `demo-data/`:
- `demo-data/invoices/invoice_01_aws_cloud.pdf`
- `demo-data/invoices/invoice_02_google_workspace.pdf`
- `demo-data/invoices/invoice_06_blurry_low_confidence.pdf`
- `demo-data/bank_statements/mock_bank_statement_august_2026.csv`

---

## 🧪 5. Automated Test Suite Execution

Run automated unit and integration tests across the backend engine:

```bash
cd backend

# Run all pytest test suites (In-Memory SQLite DB)
DATABASE_URL="sqlite:///:memory:" .venv/bin/pytest

# Run specific E2E test suites:
# 1. Happy Path Workflow
DATABASE_URL="sqlite:///:memory:" .venv/bin/pytest tests/test_e2e_happy_path.py

# 2. Low Confidence Human Review Queue Semiautomatic Flow
DATABASE_URL="sqlite:///:memory:" .venv/bin/pytest tests/test_e2e_low_confidence.py

# 3. Double-Entry Validation Failure & Sensitive Guardrails
DATABASE_URL="sqlite:///:memory:" .venv/bin/pytest tests/test_e2e_validation_failure.py
```

Frontend Production Build Validation:
```bash
cd frontend
npm run build
```

---

## 🎥 6. Executing 5-Minute Portfolio Demo

Refer to [`docs/07-Demo-Plan.md`](07-Demo-Plan.md) for step-by-step walkthrough script for portfolio demo presentations:
1. **Scene 1 (0:00 - 1:00)**: Intake & OCR Upload (`invoice_01_aws_cloud.pdf`).
2. **Scene 2 (1:00 - 2:30)**: Human Review Queue for Low-Confidence / Blurry Receipt.
3. **Scene 3 (2:30 - 3:30)**: General Ledger Double-Entry Guardrail & Trial Balance.
4. **Scene 4 (3:30 - 4:30)**: Bank Statement Reconciliation Engine (`mock_bank_statement_august_2026.csv`).
5. **Scene 5 (4:30 - 5:00)**: End-to-End Audit Trail & AI Rationale Traceability.
