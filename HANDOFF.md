# 🤖 Project SAMARTH — Phase 2 Handoff Document
## For Claude Code or New Chat Continuation
## Current status: Step 15 (React Frontend) — IN PROGRESS
## Tailwind installed. Need to configure + build all components.

---

## CRITICAL FIRST INSTRUCTION
Read this entire document before writing a single line of code.
Follow the same approach as Phase 1: build one step, test it,
commit, update HANDOFF.md, then move to the next.

---

## WHAT IS PROJECT SAMARTH

**Full name:** Agentic Multi-Agent Suite for Inclusive Education
**Goal:** Automate IEP creation for students with special needs in India.
**Reduces teacher workload by 80%.**
**Legal framework:** RPwD Act 2016 + NCTE/NCERT Guidelines.
**IEP Format:** NASET standard — 11 sections, 14 TypedDict keys.

---

## PHASE 1 — 100% COMPLETE ✅

All 11 steps built, tested, pushed to GitHub.

**Proven pipeline (real Gemini API):**
```
Dyslexia  (Arjun, 10)  → COMPLETED 62.7s  22.9KB ✅
ASD       (Priya, 8)   → COMPLETED 72.1s  19.8KB ✅
Visual    (Rahul, 14)  → COMPLETED 81.9s  23.8KB ✅
```

**Running the backend:**
```powershell
cd D:\SAMARTH
venv\Scripts\activate
uvicorn app.main:app --port 8000
```

**API endpoints:**
```
POST http://localhost:8000/iep/generate     → generate IEP
GET  http://localhost:8000/iep/{id}/download → download PDF
GET  http://localhost:8000/docs              → Swagger UI
```

---

## TECH STACK

| Layer | Technology |
|---|---|
| Agent Framework | LangGraph 1.0.9 |
| LLM | Google Gemini 2.5 Flash |
| RAG | Simple JSON retriever (rag/simple_retriever.py) |
| Legal Docs | RPwD Act 2016 PDF + NCERT Guidelines PDF |
| PDF | ReportLab 4.4 — NASET 11-section format |
| Backend | FastAPI 0.133 on port 8000 |
| Frontend | React 19 + Vite 8 + TailwindCSS (Step 15) |
| Language | Python 3.13 + Node 24.7.0 |
| OS | Windows 11 |

---

## DEVELOPMENT ENVIRONMENT

```
Project root : D:\SAMARTH\
Backend venv : D:\SAMARTH\venv\
Frontend     : D:\SAMARTH\frontend\
Python       : 3.13.7
Node         : 24.7.0
npm          : 11.5.1
LLM model    : gemini-2.5-flash  ← ALWAYS this exact name
GitHub       : https://github.com/SudhanvaJ-bit/project-samarth
Branch       : main
```

**Activate backend:**
```powershell
cd D:\SAMARTH
venv\Scripts\activate
```

**Run backend:**
```powershell
uvicorn app.main:app --port 8000
```

**Run frontend (separate terminal, no venv):**
```powershell
cd D:\SAMARTH\frontend
npm run dev
```

---

## COMPLETE FILE STRUCTURE

```
D:\SAMARTH\
│
├── agents\                      ✅ ALL COMPLETE
│   ├── state.py                 ← IEPState + NASET 14-key DraftedIEP
│   ├── scraper_agent.py         ← gemini-2.5-flash, temp=0.2
│   ├── compliance_agent.py      ← 4 RAG queries + Gemini legal audit
│   ├── drafting_agent.py        ← NASET 14-section prompt
│   ├── supervisor_agent.py      ← Pure Python QA + NASET validation
│   └── graph.py                 ← LangGraph StateGraph
│
├── rag\                         ✅ ALL COMPLETE
│   ├── simple_retriever.py      ← TF-IDF JSON retriever
│   ├── retriever.py             ← One-line swap interface
│   ├── chunks_cache.json        ← Auto-generated from PDFs
│   └── documents\
│       ├── rpwd_act_2016.pdf
│       └── ncte_guidelines.pdf
│
├── pdf_generator\               ✅ COMPLETE
│   └── iep_pdf.py               ← ReportLab NASET format
│
├── app\                         ✅ COMPLETE
│   ├── main.py                  ← FastAPI + lifespan warmup
│   └── routers\iep.py           ← POST/GET endpoints
│
├── models\                      ✅ COMPLETE
│   └── student.py               ← Pydantic schemas
│
├── tests\                       ✅ ALL 35+ TESTS PASSING
│   ├── test_state.py
│   ├── test_rag.py
│   ├── test_scraper.py
│   ├── test_compliance.py
│   ├── test_drafting.py
│   ├── test_supervisor.py
│   ├── test_graph.py
│   ├── test_pdf.py
│   ├── test_api.py
│   └── test_integration.py
│
├── frontend\                    ⏳ IN PROGRESS ← CONTINUE HERE
│   ├── package.json             ✅ created
│   ├── vite.config.js           ⚠️ NEEDS TAILWIND CONFIG
│   ├── src\
│   │   ├── main.jsx             ✅ exists (default)
│   │   ├── App.jsx              ❌ NEEDS REWRITE
│   │   ├── index.css            ⚠️ NEEDS TAILWIND DIRECTIVES
│   │   └── components\          ❌ ALL TO BE CREATED
│   │       ├── Layout.jsx
│   │       ├── StudentForm.jsx
│   │       ├── PipelineTracker.jsx
│   │       ├── IEPViewer.jsx
│   │       └── IEPHistory.jsx
│   └── src\api\
│       └── samarth.js           ❌ TO BE CREATED
│
├── outputs\                     ✅ 7 PDFs generated
├── .env                         ✅ GOOGLE_API_KEY set
├── .gitignore                   ✅
├── requirements.txt             ✅
└── README.md                    ✅
```

---

## STEP 15 — WHERE WE ARE RIGHT NOW

### Done so far:
```powershell
cd D:\SAMARTH
npm create vite@latest frontend -- --template react  ✅
cd frontend
npm install                                           ✅
npm install axios react-router-dom                   ✅
npm install -D tailwindcss @tailwindcss/vite         ✅
```

### What needs to happen next:

**15.3 — Configure Tailwind in vite.config.js:**
```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
})
```

**15.4 — Add Tailwind to src/index.css:**
```css
@import "tailwindcss";
```

**15.5 — Configure proxy in vite.config.js (add to defineConfig):**
```javascript
server: {
  proxy: {
    '/iep': 'http://localhost:8000',
    '/docs': 'http://localhost:8000',
  }
}
```

**15.6 — Build all components (full list below)**

---

## FRONTEND COMPONENTS TO BUILD

### `src/api/samarth.js`
```javascript
import axios from 'axios'
const api = axios.create({ baseURL: 'http://localhost:8000' })

export const generateIEP = (studentData) =>
  api.post('/iep/generate', studentData)

export const downloadIEP = (iepId) =>
  api.get(`/iep/${iepId}/download`, { responseType: 'blob' })

export const checkHealth = () =>
  api.get('/iep/health')
```

### `src/App.jsx`
- React Router with routes:
  - `/` → GeneratePage (main form)
  - `/history` → HistoryPage (past IEPs)
- Persistent sidebar navigation
- SAMARTH branding

### `src/components/Layout.jsx`
- Sidebar with nav links
- Main content area
- Logo: "🎓 SAMARTH" + "IEP Generator"
- Nav items: Generate IEP, My IEPs, Health Check

### `src/components/StudentForm.jsx`
Form fields (all required unless noted):
- student_name (text)
- age (number, 3-25)
- grade (text)
- school_name (text)
- disability_category (select — all 12 from DisabilityCategory enum)
- disability_severity (select — mild/moderate/severe)
- raw_notes (textarea, min 50 chars)
- academic_history (textarea, optional)
- teacher_observations (textarea, optional)
- parent_concerns (textarea, optional)
- Submit button → calls generateIEP API
- Loading state while pipeline runs (~90 seconds)

### `src/components/PipelineTracker.jsx`
Live status display showing 4 stages:
- ✅ Scraper Agent — [N] strengths extracted
- ✅ Compliance Agent — [status] | [N] mandatory items
- ✅ Drafting Agent — 14 sections written
- ✅ PDF Generated — [size]KB

Polling: every 3 seconds check if completed.
Show spinner while running, checkmark when done.

### `src/components/IEPViewer.jsx`
After generation completes:
- Show compliance status badge (green/amber/red)
- Show IEP ID
- Preview first 4 sections as cards
- Download PDF button
- Mandatory accommodations list

### `src/components/IEPHistory.jsx`
List of previously generated IEPs stored in
localStorage (since no DB yet in Phase 2 Step 15):
- Student name, disability, date, status
- Download button for each
- Clear history button

---

## DISABILITY CATEGORIES (for select dropdown)
```javascript
const DISABILITIES = [
  "Dyslexia", "Dysgraphia", "Dyscalculia",
  "Autism Spectrum Disorder", "ADHD",
  "Visual Impairment", "Hearing Impairment",
  "Intellectual Disability", "Cerebral Palsy",
  "Speech and Language Disability",
  "Multiple Disabilities", "Other"
]
```

---

## CRITICAL TECHNICAL NOTES (backend — don't change)

### Model name
```python
model = "gemini-2.5-flash"  # Always this exact name
```

### NASET 14 DraftedIEP keys
```
background_info, academic_performance, social_development,
physical_development, management_needs, long_term_outcomes,
annual_goals, special_education_services,
general_education_participation, participating_agencies,
coordinated_activities, graduation_info,
recommendations_summary, progress_reporting
```

### Graph edge (never change)
```python
graph.add_edge("pdf_generator", "end_success")  # NOT supervisor!
```

### Supervisor validates NASET 14 keys
`_check_drafting_output` in supervisor_agent.py checks all 14.

### JSON cleaning (all agents)
```python
def clean_json(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
        raw = "\n".join(lines)
    return raw.strip()
```

---

## WHAT TO SAY TO START THE NEW CHAT

Paste this entire document and say:

> "Read this handoff document carefully. Project SAMARTH Phase 1
> is 100% complete. I am building Phase 2 Step 15 — React Frontend.
> The frontend is already scaffolded at D:\SAMARTH\frontend\ with
> Vite + React + Tailwind + axios + react-router-dom all installed.
> Start from Step 15.3 — configure Tailwind in vite.config.js,
> then build all the components listed in this document one by one.
> The backend runs on port 8000. Use the same approach: build,
> test in browser, commit, update HANDOFF.md."

---

## PROGRESS TRACKER

### Phase 1 — Complete ✅
| Step | Component | Status |
|---|---|---|
| 0-11 | Full backend pipeline | ✅ All complete |

### Phase 2 — In Progress
| Step | Component | Status |
|---|---|---|
| Step 15 | React Frontend | 🔄 In Progress |
| Step 15.3 | Configure Tailwind | ⏳ Next |
| Step 15.4 | src/api/samarth.js | ⬜ |
| Step 15.5 | App.jsx + Router | ⬜ |
| Step 15.6 | Layout.jsx | ⬜ |
| Step 15.7 | StudentForm.jsx | ⬜ |
| Step 15.8 | PipelineTracker.jsx | ⬜ |
| Step 15.9 | IEPViewer.jsx | ⬜ |
| Step 15.10 | IEPHistory.jsx | ⬜ |
| Step 16 | Railway Deployment | ⬜ |

---

## GITHUB
```
Repo   : https://github.com/SudhanvaJ-bit/project-samarth
Branch : main
State  : Phase 1 complete, Phase 2 Step 15 frontend scaffolded
```
