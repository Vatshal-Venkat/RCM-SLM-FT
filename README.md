# RCM AI Platform (RCM-SLM-FT)

A domain-specific Revenue Cycle Management (RCM) AI platform powered by a fine-tuned Small Language Model (SLM / Qwen-3 GGUF), Hybrid RAG (Dense + BM25 Lexical + Cross-Encoder Reranking), FastAPI backend, and Next.js React frontend dashboard.

---

## Architecture Overview

- **Frontend**: Next.js (App Router, Tailwind CSS, Lucide icons, Recharts) running at `http://localhost:3000`
- **Backend**: FastAPI (Python 3.11+, Uvicorn, SQLite/PostgreSQL, Llama.cpp) running at `http://127.0.0.1:8000`
- **SLM / AI Model**: Quantized GGUF model (`rcm_qwen3_1.7b_q4_k_m.gguf`) loaded locally via `llama-cpp-python`
- **RAG Engine**: Hybrid retriever with BGE embeddings (`BAAI/bge-small-en-v1.5`), BM25 lexical search, and Cross-Encoder reranking (`ms-marco-MiniLM-L-6-v2`)

---

## Quick Start / Running the Project

### 1. Prerequisites
- **Python**: Version 3.10 or 3.11 installed
- **Node.js**: Version 18+ or 20+ and `npm` installed
- **Model File**: GGUF weights placed in `backend/models/rcm_qwen3_1.7b_q4_k_m.gguf`

---

### 2. Backend Setup & Run

All backend commands run from the `backend/` directory with the virtual environment activated.
Open a terminal in the project root:

```powershell
cd backend

# Create the virtual environment (first time only)
python -m venv venv

# Activate it (every new terminal)
venv/Scripts/activate

# Install dependencies (first time only)
pip install -r requirements.txt

# Create .env from example (if not present)
Copy-Item .env.example .env
```

#### Ingest Knowledge (Build RAG Vector Index)
```powershell
# (Optional) regenerate knowledge/curated_qa.md from training/datasets first
python ../scripts/build_curated_qa.py
python ../scripts/ingest_knowledge.py
```

#### Seed Synthetic Claims Database
```powershell
python ../scripts/seed_database.py --reset
```

#### Start FastAPI Server
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- **Backend API**: `http://127.0.0.1:8000`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/api/health`

---

### 3. Frontend Setup & Run

Open a second terminal window:

```powershell
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Next.js development server
npm run dev
```

- **Frontend App**: `http://localhost:3000`

---

### 4. Running Scripts & CLI Testing

#### Ask questions via CLI (Query running backend):
```powershell
# From backend/ with venv/Scripts/activate run, while the server is up
python ../scripts/ask.py "What is an ERA?"
python ../scripts/ask.py "Explain CO 16 denial code"
python ../scripts/ask.py "What are the key KPIs for AR management?" --no-rag
```

#### Run Unit Tests:
```powershell
# From backend/ with venv/Scripts/activate run
pytest -m "not model"

# Run all tests including model inference (requires GGUF weights):
pytest
```

---

## Directory Structure

```text
├── backend/
│   ├── app/
│   │   ├── ai/            # Model inference & Llama.cpp provider factory
│   │   ├── analytics/     # RCM analytics & KPI metrics calculation
│   │   ├── api/           # FastAPI routers (chat, claims, analytics, health, rag)
│   │   ├── core/          # Application settings & logging
│   │   ├── db/            # Database engine, models, and synthetic generator
│   │   ├── rag/           # Chunking, indexing, lexical BM25, dense embeddings & retriever
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   └── services/      # Business logic, validation, chat & claim analysis services
│   ├── data/              # SQLite DB and RAG vector store index
│   ├── models/            # GGUF fine-tuned LLM model weights
│   ├── tests/             # Pytest test suite
│   ├── .env.example       # Example environment variables
│   └── requirements.txt   # Python backend dependencies
├── frontend/
│   ├── app/               # Next.js App Router (pages & layout)
│   ├── components/        # React components (Dashboard, Chat, Claims, Visualizations)
│   ├── hooks/             # Custom React hooks (useApi)
│   ├── lib/               # API clients and utilities
│   ├── types/             # TypeScript interfaces
│   └── package.json       # Frontend dependencies & scripts
├── knowledge/             # Domain knowledge markdown files for RAG
├── scripts/
│   ├── ask.py             # CLI client for asking questions to backend
│   ├── build_curated_qa.py# Publishes training knowledge Q&A to knowledge/curated_qa.md
│   ├── ingest_knowledge.py# Script to build RAG vector index
│   └── seed_database.py   # Script to populate synthetic RCM data
├── training/
│   ├── datasets/          # Fine-tuning JSONL (v2_1 current, v2 superseded, terminology anchor)
│   └── adapters/          # LoRA adapters (git-ignored; see training/README.md)
└── README.md
```
