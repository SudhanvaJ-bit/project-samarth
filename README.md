# 🎓 Project SAMARTH

### Agentic Multi-Agent Suite for Inclusive Education

![Python](https://img.shields.io/badge/Python-3.13-blue?style=for-the-badge&logo=python)
![LangGraph](https://img.shields.io/badge/LangGraph-1.0.9-green?style=for-the-badge)
![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-orange?style=for-the-badge&logo=google)
![FastAPI](https://img.shields.io/badge/FastAPI-0.133-009688?style=for-the-badge&logo=fastapi)
![Status](https://img.shields.io/badge/Status-In_Development-yellow?style=for-the-badge)
![Compliance](https://img.shields.io/badge/Law-RPwD_Act_2016-red?style=for-the-badge)

> Automates the creation of **Individualized Education Programs (IEPs)**
> for students with special needs — reducing teacher workload by **80%**.
> Legally compliant with **RPwD Act 2016** and **NCTE Guidelines**.

---

## 📌 The Problem

| Issue | Impact |
|---|---|
| 4.9 crore children with disabilities in India | Most never get a proper IEP |
| Teachers spend 4+ hours per IEP manually | Unsustainable workload |
| Most IEPs are not legally compliant | Violates RPwD Act 2016 |
| 1 teacher handles 30+ students | No time for quality IEPs |

---

## ✅ The Solution

SAMARTH uses a **4-agent AI pipeline** to generate a complete, legally
compliant IEP in under 30 seconds — from raw teacher notes to a
professional PDF document.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Student Input                      │
│     (name, disability, teacher notes, history)       │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│              Supervisor Agent                        │
│     Orchestrates flow · QA checks · Retry logic      │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
       ▼              ▼              ▼
┌──────────┐   ┌────────────┐  ┌──────────────┐
│ Scraper  │   │ Compliance │  │   Drafting   │
│  Agent   │   │   Agent    │  │    Agent     │
│          │   │            │  │              │
│ Extracts │   │ RAG Query  │  │ Writes all   │
│ insights │   │ RPwD Act   │  │ 10 IEP       │
│ & goals  │   │ + NCTE     │  │ sections     │
└──────────┘   └────────────┘  └──────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│                 PDF Generator                        │
│     Professional · Printable · Legally cited         │
└─────────────────────────────────────────────────────┘
```

---

## 🤖 The 4 Agents

| Agent | Role | Technology |
|---|---|---|
| **Scraper Agent** | Extracts strengths, challenges, SMART goals from raw notes | Gemini 2.5 Flash |
| **Compliance Agent** | Legal gatekeeper — verifies RPwD Act + NCTE requirements | Gemini 2.5 Flash + RAG |
| **Drafting Agent** | Writes all 10 professional IEP sections | Gemini 2.5 Flash |
| **Supervisor Agent** | Orchestrates flow, QA checks every output, handles retries | Pure Python |

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Agent Framework | LangGraph 1.0.9 | Stateful multi-agent workflow |
| LLM | Google Gemini 2.5 Flash | All agent reasoning |
| Vector Search | Simple JSON RAG | Legal document retrieval |
| Legal Sources | RPwD Act 2016 + NCERT Guidelines | Compliance verification |
| API Backend | FastAPI 0.133 | REST API |
| PDF Generation | ReportLab 4.4 | IEP document rendering |
| Language | Python 3.13 | Runtime |

> **Note:** ChromaDB vector database will replace Simple JSON RAG in Phase 2 deployment.

---

## ⚖️ Legal Compliance

SAMARTH is built specifically for the Indian education system:

- ✅ **RPwD Act 2016** — Rights of Persons with Disabilities Act (Act No. 49 of 2016)
- ✅ **NCERT Guidelines** — National Guidelines on Equitable and Inclusive Education
- ✅ Covers all **21 disability categories** recognized under RPwD Act Schedule
- ✅ Mandatory IEP components per **Section 16 & 17** of RPwD Act
- ✅ Assessment accommodations per **Section 17(i)**

### Disabilities Supported

| Category | Examples |
|---|---|
| Specific Learning Disabilities | Dyslexia, Dysgraphia, Dyscalculia |
| Neurodevelopmental | Autism Spectrum Disorder, ADHD |
| Sensory | Visual Impairment, Hearing Impairment |
| Physical | Cerebral Palsy, Locomotor Disability |
| Intellectual | Intellectual Disability |
| Multiple | Deaf-Blindness, Multiple Disabilities |

---

## 📁 Project Structure

```
samarth/
│
├── agents/
│   ├── __init__.py
│   ├── state.py                 # IEPState TypedDict — shared pipeline memory
│   ├── scraper_agent.py         # Extracts insights from raw student data
│   ├── compliance_agent.py      # RAG-powered legal compliance checker
│   ├── drafting_agent.py        # Writes 10-section IEP document
│   ├── supervisor_agent.py      # Orchestrates flow + QA
│   └── graph.py                 # LangGraph workflow assembly
│
├── rag/
│   ├── __init__.py
│   ├── simple_retriever.py      # Keyword-based legal document search
│   ├── retriever.py             # Backend switch (simple ↔ ChromaDB)
│   ├── chunks_cache.json        # Pre-extracted PDF chunks (auto-generated)
│   └── documents/
│       ├── rpwd_act_2016.pdf    # Official RPwD Act 2016
│       └── ncte_guidelines.pdf  # NCERT Inclusive Education Guidelines
│
├── pdf_generator/
│   ├── __init__.py
│   └── iep_pdf.py               # ReportLab PDF renderer
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entrypoint
│   └── routers/
│       ├── __init__.py
│       └── iep.py               # IEP generation endpoints
│
├── models/
│   ├── __init__.py
│   └── student.py               # Pydantic request/response schemas
│
├── tests/
│   ├── test_state.py            # State layer tests ✅
│   ├── test_rag.py              # RAG retrieval tests ✅
│   ├── test_scraper.py          # Scraper agent tests ✅
│   ├── test_compliance.py       # Compliance agent tests
│   ├── test_drafting.py         # Drafting agent tests
│   └── test_integration.py      # Full pipeline end-to-end test
│
├── outputs/                     # Generated IEP PDFs (git-ignored)
├── .env                         # API keys (git-ignored)
├── .env.example                 # Environment variables template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🚀 Setup & Installation

### Prerequisites

- Python 3.10 or higher
- Google Gemini API key — [Get one free at AI Studio](https://aistudio.google.com/apikey)

### Step 1 — Clone the repository

```bash
git clone https://github.com/SudhanvaJ-bit/project-samarth.git
cd project-samarth
```

### Step 2 — Create virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac / Linux
python -m venv venv
source venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Configure environment

```bash
cp .env.example .env
# Add your GOOGLE_API_KEY to .env
```

### Step 5 — Build RAG cache (run once)

```bash
python tests/test_rag.py
```

### Step 6 — Run all tests

```bash
python tests/test_state.py
python tests/test_rag.py
python tests/test_scraper.py
```

### Step 7 — Start the API server

```bash
uvicorn app.main:app --reload --port 8000
```

### Step 8 — Generate an IEP

```bash
curl -X POST http://localhost:8000/iep/generate \
  -H "Content-Type: application/json" \
  -d '{
    "student_name": "Arjun Sharma",
    "age": 10,
    "grade": "Grade 4",
    "school_name": "Delhi Public School, Bengaluru",
    "disability_category": "Dyslexia",
    "disability_severity": "moderate",
    "raw_notes": "Struggles with reading but excels in math and oral discussions."
  }'
```

### Step 9 — View API documentation

```
http://localhost:8000/docs
```

---

## 🧪 Test Suite

```bash
python tests/test_state.py        # State layer
python tests/test_rag.py          # RAG retrieval
python tests/test_scraper.py      # Scraper Agent
python tests/test_compliance.py   # Compliance Agent
python tests/test_drafting.py     # Drafting Agent
python tests/test_integration.py  # Full pipeline
```

---

## 📊 Build Progress

| Step | Component | Status |
|---|---|---|
| Step 0 | Environment Setup | ✅ Complete |
| Step 1 | Project Scaffold | ✅ Complete |
| Step 2 | State Layer — IEPState TypedDict | ✅ Complete |
| Step 3 | RAG Layer — Legal Document Search | ✅ Complete |
| Step 4 | Scraper Agent + Tests | ✅ Complete |
| Step 5 | Compliance Agent + Tests | ✅ Complete |
| Step 6 | Drafting Agent + Tests | 🔄 In Progress |
| Step 7 | Supervisor Agent + Tests | ⬜ Pending |
| Step 8 | LangGraph Pipeline Assembly | ⬜ Pending |
| Step 9 | PDF Generator | ⬜ Pending |
| Step 10 | FastAPI Backend | ⬜ Pending |
| Step 11 | Full Integration Test | ⬜ Pending |

---

## 🗺️ Roadmap

### Phase 1 — Prototype *(Current)*

- [x] Project scaffold and environment
- [x] IEPState TypedDict — shared pipeline state
- [x] RAG layer with official legal documents
- [x] Scraper Agent — insight extraction
- [ ] Compliance Agent — legal verification
- [ ] Drafting Agent — IEP section writing
- [ ] Supervisor Agent — orchestration
- [ ] LangGraph pipeline wiring
- [ ] PDF generation
- [ ] FastAPI REST API

### Phase 2 — Production Ready

- [ ] ChromaDB vector database (replace JSON RAG)
- [ ] PostgreSQL — store generated IEPs
- [ ] JWT authentication and API keys
- [ ] React frontend dashboard for teachers
- [ ] Cloud deployment — Railway / AWS

### Phase 3 — Scale

- [ ] Mobile application
- [ ] Multi-school support
- [ ] Analytics dashboard
- [ ] School ERP system integration
- [ ] Multilingual support (Hindi + regional languages)

---

## 💡 Key Design Decisions

### Why LangGraph?
LangGraph provides stateful workflows — all agents share a single `IEPState` object. Any agent can be swapped, upgraded, or retried without touching the others.

### Why RAG for Compliance?
The Compliance Agent retrieves actual clauses from the official RPwD Act 2016 PDF before asking Gemini to cross-reference them — ensuring legally accurate output with no hallucination.

### Why Simple JSON RAG for now?
ChromaDB requires 400MB+ RAM for ONNX embeddings. The Simple JSON retriever gives the same interface with near-zero memory usage for local development. One line change in `rag/retriever.py` swaps to ChromaDB on deployment.

### Why Supervisor Agent with no LLM?
The Supervisor Agent is pure Python logic — no Gemini calls. This keeps orchestration fast, deterministic, and testable without API costs.

---

## 📄 Sample IEP Output

A generated IEP contains 10 sections:

| Section | Content |
|---|---|
| 1 | Student Profile Summary |
| 2 | Present Levels of Performance |
| 3 | Annual Goals (SMART) |
| 4 | Short-Term Objectives |
| 5 | Special Education Services |
| 6 | Classroom Accommodations |
| 7 | Assessment Modifications |
| 8 | Transition Planning (age 14+) |
| 9 | Parental Involvement Plan |
| 10 | Review Schedule |

Each PDF includes legal compliance citations, signature block, and compliance status badge.

---

## 👨‍💻 Author

**Sudhanva Joshi**
GitHub: [@SudhanvaJ-bit](https://github.com/SudhanvaJ-bit)

---

## 📃 Legal References

- RPwD Act 2016 — Ministry of Social Justice and Empowerment, Government of India
- NCERT National Guidelines on Equitable and Inclusive Education — Ministry of Education, Government of India

---

> *"Every child deserves an education plan as unique as they are."*