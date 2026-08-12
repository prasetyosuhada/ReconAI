# ReconAI — Agentic AI Platform for Accounting Automation

ReconAI is an agentic AI platform that automates core bookkeeping workflows — from document extraction to ledger posting and bank reconciliation — using a multi-agent architecture with deterministic accounting guardrails and first-class human-in-the-loop oversight.

---

## 🌟 Key Features

- **Document Intake Agent:** Extracts structured financial data (vendor, date, line items, amounts, tax) from uploaded receipts and invoices (PDF / Images).
- **Bookkeeping Agent:** Maps transactions to Chart of Accounts (COA), drafts balanced double-entry journal entries, and provides natural-language reasoning.
- **Reconciliation Agent:** Performs intelligent matching (exact and fuzzy) between bank statement transactions and posted ledger entries.
- **Deterministic Guardrails:** Hardcoded rule-based validation ensures math correctness (Debits == Credits) and enforces sensitive account checks before posting.
- **Human-in-the-Loop Review Queue:** Routes low-confidence extractions, ambiguous classifications, or high-risk entries to a human review UI for Approval/Edit/Rejection.
- **Audit & Traceability:** Logs every agent decision, confidence score, rationale, and human action for total audit transparency.

---

## 🏗 System Architecture

```text
┌─────────────────────┐
│   Supervisor /      │
│   Orchestrator      │ (LangGraph)
└─────────┬───────────┘
          │
  ┌───────┼────────────────────┐
  │       │                    │
  ▼       ▼                    ▼
┌───────────┐   ┌───────────┐   ┌──────────────────┐
│ Document  │ → │ Bookkeeping│ → │ Reconciliation   │
│ Intake    │   │ Agent     │   │ Agent            │
└───────────┘   └───────────┘   └──────────────────┘
      │               │                  │
      ▼               ▼                  ▼
  ┌──────────────────────────────────────────┐
  │    Human Review Queue / Approval UI      │
  └──────────────────────────────────────────┘
                      │
                      ▼
             ┌──────────────────┐
             │    Audit Log     │
             └──────────────────┘
```

---

## 🛠 Tech Stack

- **Backend:** FastAPI, Python, SQLAlchemy, Alembic, PostgreSQL
- **Orchestration:** LangGraph, LangChain
- **LLM Providers:** Gemini / OpenAI (Structured Outputs)
- **Frontend:** TypeScript, React, Vite, TailwindCSS
- **Infrastructure:** Docker Compose

---

## 🚀 Quick Start (Local Setup)

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (Fast Python package & environment manager)
- Node.js 18+

### 1. Clone & Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Configure your API keys in .env
# OPENAI_API_KEY=your_key_here
# GEMINI_API_KEY=your_key_here
```

### 2. Run Database with Docker

```bash
docker compose up -d
```

### 3. Backend Setup

```bash
cd backend

# Install dependencies & create virtualenv automatically
uv sync

# Run migrations & seed data
uv run alembic upgrade head
uv run python seed.py

# Start FastAPI server
uv run uvicorn main:app --reload --port 8000
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 📚 Documentation

Detailed specification documents are available in the `docs/` directory:

- [docs/01-PRD.md](docs/01-PRD.md) — Product Requirements Document
- [docs/02-System-Architecture.md](docs/02-System-Architecture.md) — Technical Architecture Design
- [docs/03-Data-Model.md](docs/03-Data-Model.md) — Database Schema & Data Models
- [docs/04-Agent-Design.md](docs/04-Agent-Design.md) — Agent Roles, Prompts & State Machine
- [docs/05-API-Spec.md](docs/05-API-Spec.md) — REST API Endpoints Contract
- [docs/06-UX-Flow.md](docs/06-UX-Flow.md) — Frontend User Flows & UI Specifications
- [docs/07-Demo-Plan.md](docs/07-Demo-Plan.md) — 5-Minute Portfolio Demo Guide
- [docs/08-Test-Plan.md](docs/08-Test-Plan.md) — Testing & AI Agent Evaluation Strategy
- [docs/09-Setup-Guide.md](docs/09-Setup-Guide.md) — Local Setup & Execution Manual

---

## 📄 License

This project is licensed under the MIT License.
