# Research Town — Multi-Agent Research Simulation

A from-scratch multi-agent simulation where 5 AI scientists propose hypotheses,
debate findings, and build a canonical knowledge base powered entirely by the
Google Gemini API. Includes a real-time Next.js dashboard and a headless CLI mode.

---

## What this actually does

The LLM is stateless. It remembers nothing between calls.
Code the orchestrator, the SQLite database, and the embedding vectors that creates the illusion of persistent, evolving agents.

```
What it looks like:   5 scientists collaborating and learning over time
What it actually is:  A loop calling the Gemini API with carefully injected context
```

---

## Project structure

```
research_town/
│
├── backend/                        ← Python AI logic + FastAPI server
│   ├── api.py                      ← FastAPI: connects SQLite to the Next.js frontend
│   ├── main.py                     ← CLI entry point (headless mode, no UI needed)
│   ├── orchestrator.py             ← The daily loop — runs all 4 phases each day
│   ├── agent.py                    ← Agent class: persona + memory + LLM call
│   ├── .env                        ← Your API key (never committed)
│   ├── requirements.txt
│   │
│   ├── agents/
│   │   └── personas.py             ← System prompts for all 5 agents
│   │
│   ├── utils/
│   │   ├── llm.py                  ← Only file that calls the Gemini API
│   │   ├── memory.py               ← Gemini embeddings + SQLite (agent memory + KB)
│   │   └── evaluator.py            ← Post-simulation analysis metrics
│   │
│   └── data/                       ← Auto-generated SQLite database (gitignored)
│       └── knowledge_base.db
│
└── frontend/                       ← Next.js real-time dashboard
    ├── src/app/page.tsx             ← Main UI: live chat + knowledge base viewer
    └── package.json
```

---

## How the simulation works

Each "day" runs 4 phases in sequence. Agents are stateless LLM calls — the
orchestrator builds their context from the database before each call.

```
Phase 1 — Hypothesis
  Lead Scientist reads the Knowledge Base → proposes today's hypothesis
  → assigns specific tasks to each team member

Phase 2 — Research
  Researcher receives their assigned task → investigates → writes findings report
  Findings are injected into Phase 3

Phase 3 — Debate  (information asymmetry is intentional)
  Critic          reads the researcher's FINDINGS  → attacks the METHOD
  Devil's Advocate reads the HYPOTHESIS only       → attacks the PREMISE
  ↑ Neither sees the other's challenge — keeps critiques structurally independent

Phase 4 — Synthesis
  Archivist reads everything from today → writes objective summary
  Orchestrator parses archivist output → commits approved findings to SQLite KB

Day N+1
  All agents start with the KB summary injected into their prompt.
  Agents "remember" via:
    • Gemini embedding retrieval (personal episodic memory — semantic search)
    • SQLite KB summary (shared validated findings — everyone reads this)
```

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- A Gemini API key — get one free at https://aistudio.google.com/app/apikey

---

### Backend setup

```bash
cd backend
pip install -r requirements.txt
```

Create your `.env` file:

```bash
cp .env
```

Open `.env` and set your key:

```
GEMINI_API_KEY=your_key_here
```

---

### Frontend setup

```bash
cd frontend
npm install
```

---

## Running the simulation

### Option A — Web dashboard (recommended)

Gives you a real-time UI to enter topics, watch debates live, and browse the KB.

**Terminal 1 — start the backend API:**

```bash
cd backend
uvicorn api:app --reload --port 8000
```

**Terminal 2 — start the frontend:**

```bash
cd frontend
npm run dev
```

Open http://localhost:3000 — enter a research topic, set the number of days, click Run.

---

### Option B — Headless CLI

Run a full simulation in the terminal with no UI. Useful for bulk testing or
running overnight experiments.

```bash
cd backend
python main.py
```

Change `RESEARCH_TOPIC` and `DAYS` at the top of `main.py` before running.
The full debate prints to the terminal. `evaluator.py` runs automatically when done.

---

## Inspecting the data

Everything is stored in a single SQLite file at `backend/data/knowledge_base.db`.
To test use `backend/data/demo_seed.db`

```bash
cd backend
sqlite3 data/knowledge_base.db
```

Useful queries:

```sql
-- All validated findings
SELECT day, author, title, confidence FROM findings;

-- Full conversation transcript
SELECT day, phase, agent, substr(content, 1, 100) FROM transcript;

-- All hypotheses and their outcomes
SELECT day, status, substr(content, 1, 120) FROM hypotheses;

-- Every contradiction raised (including unresolved ones)
SELECT day, raised_by, substr(content, 1, 100) FROM contradictions;

-- Agent episodic memories
SELECT agent_name, day, phase, substr(content, 1, 80) FROM episodic_memories;
```

Episodic memories are stored as Gemini embedding vectors (768-dim JSON arrays)
inside the same database. Memory retrieval uses numpy cosine similarity —
no external vector database required.

---

## Tuning behaviour

### Change the research topic

**Web dashboard:** type it into the UI before clicking Run.

**CLI mode:** edit `RESEARCH_TOPIC` in `backend/main.py`. Works with any domain:

```python
RESEARCH_TOPIC = "The economic causes of medieval famines"
RESEARCH_TOPIC = "Whether transformer attention is biologically plausible"
RESEARCH_TOPIC = "Antibiotic resistance mechanisms in hospital-acquired infections"
```

### Change agent personalities

Edit system prompts in `backend/agents/personas.py`.
The personality paragraph is the main lever — it controls tone, confidence,
aggressiveness, and epistemic style. Try making the Devil's Advocate more
confrontational and observe the downstream impact on KB quality.

### Change information asymmetry

In `backend/orchestrator.py`, `_phase_debate()` controls what each agent sees.
Currently the Devil's Advocate does NOT see the researcher's findings.
Give them the findings and watch the debate become less structurally independent.

### Switch models

In `backend/.env`:

```
GEMINI_MODEL=gemini-1.5-pro         # smarter, slower, higher cost
GEMINI_EMBED_MODEL=text-embedding-004
```

---

## Evaluation metrics (CLI mode)

After the simulation ends, `evaluator.py` runs automatically and reports:

| Metric | What it shows |
|--------|---------------|
| Hypothesis survival rate | % of proposals that survive peer review |
| Belief drift | How much agent confidence changes across days |
| Citation graph | Which agents cited whose work (epistemic authority) |
| Debate intensity | Challenge signal frequency per day (flaw, disagree, contradicts) |

---

## Using Vertex AI instead of the direct Gemini API

Add to `backend/.env`:

```
USE_VERTEX=true
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

Then authenticate:

```bash
gcloud auth application-default login
```

Uncomment the Vertex AI block in `backend/utils/llm.py`. No other files change.

---

## Common issues

**`ModuleNotFoundError`**
Make sure you are running commands from the correct directory.
Python commands from inside `backend/`. npm commands from inside `frontend/`.

**`[Embedding error: 404 ... not found for API version v1beta]`**
The old `google-generativeai` package is still installed alongside the new one.
Fix:
```bash
pip uninstall google-generativeai -y
pip install google-genai --upgrade
```

**`JSON parse failed`**
Gemini occasionally returns non-JSON for a structured call. The code handles this
gracefully, logs a warning, and continues. Not a crash — safe to ignore.

**`ResourceExhausted` / rate limit**
The LLM wrapper retries automatically after 30 seconds. If it happens often,
switch to `gemini-2.0-flash` (faster quota recovery than pro models).

**Nothing committed to KB on Day 1**
Normal. The archivist is conservative on Day 1 — findings lack supporting evidence.
Entries accumulate from Day 2 onwards as claims get corroborated.

**Frontend shows stale data**
The Next.js page polls the FastAPI backend. Make sure `uvicorn` is still running
in the backend terminal (`uvicorn api:app --reload --port 8000`).