# Research Town — Multi-Agent Research Simulation

A multi-agent simulation where 5 AI scientists propose hypotheses, debate findings, and build a canonical knowledge base powered entirely by the Google Gemini API. Includes a real-time Next.js dashboard and a headless CLI mode. Fully containerized with Docker for one-command deployment.

---

## What this actually does

The LLM is stateless. It remembers nothing between calls. The orchestrator, SQLite database, and embedding vectors create the illusion of persistent, evolving agents.

```
What it looks like:   5 scientists collaborating and learning over time
What it actually is:  A loop calling the Gemini API with carefully injected context
```

---

## Project structure

```
research_town/
│
├── docker-compose.yml              ← 1-click stack orchestration
│
├── backend/                        ← Python AI logic + FastAPI server
│   ├── api.py                      ← FastAPI: connects SQLite to the Next.js frontend
│   ├── main.py                     ← CLI entry point (headless mode, no UI needed)
│   ├── orchestrator.py             ← The daily loop — runs all 4 phases each day
│   ├── agent.py                    ← Agent class: persona + memory + LLM call
│   ├── Dockerfile                  ← Backend container config
│   ├── .env                        ← Your API key (never committed)
│   ├── .env.example                ← Template — copy to .env and fill in
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
│   └── data/                       ← Auto-generated SQLite database (bind mounted)
│       ├── knowledge_base.db       ← Active simulation data
│       └── demo_seed.db            ← Fallback data for the UI when no simulation has run
│
└── frontend/                       ← Next.js real-time dashboard
    ├── src/app/page.tsx            ← Main UI: live debate + knowledge base viewer
    ├── next.config.js              ← API proxy config (required for Docker networking)
    ├── Dockerfile                  ← Frontend container config
    └── package.json
```

---

## How the simulation works

Each "day" runs 4 phases in sequence. Agents are stateless LLM calls — the orchestrator builds their context from the database before each call.

**Phase 1 — Hypothesis**
The Lead Scientist reads the Knowledge Base and proposes today's hypothesis, then assigns specific tasks to each team member.

**Phase 2 — Research**
The Researcher receives their assigned task, investigates, and writes a structured findings report. Findings are injected into Phase 3.

**Phase 3 — Debate** *(information asymmetry is intentional)*
The Critic reads the researcher's findings and attacks the **method**. The Devil's Advocate reads only the hypothesis and attacks the **premise**. Neither sees the other's challenge — this keeps critiques structurally independent.

**Phase 4 — Synthesis**
The Archivist reads everything from today and writes an objective summary. The orchestrator parses the archivist's output and commits approved findings to the SQLite knowledge base.

**Day N+1**
All agents start with the KB summary injected into their prompt. Agents remember via Gemini embedding retrieval (personal episodic memory — semantic search) and the SQLite KB summary (shared validated findings that everyone reads).

---

## Setup

### Prerequisites

- **Docker Desktop** — recommended, handles everything
- **Python 3.10+ and Node.js 18+** — only needed if running natively without Docker
- **Gemini API key** — get one free at https://aistudio.google.com/app/apikey

### Step 1 — Environment variables

Create a `.env` file inside the `backend/` directory:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and add your key exactly like this — no quotes, no `export`:

```
GEMINI_API_KEY=AIzaSyYourActualKeyGoesHere
```

---

## Running the simulation

### Option A — Docker Compose (recommended)

Runs the entire stack (frontend + backend + database) with one command. No Python or Node installation required.

```bash
docker compose up --build
```

Open http://localhost:3000 — enter a research topic, set the number of days, click **Run**.

To stop:

```bash
docker compose down
```

---

### Option B — Native web dashboard

Run the servers directly on your machine without Docker.

**Terminal 1 — backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

**Terminal 2 — frontend:**

Create `frontend/.env.local` containing:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Then:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

---

### Option C — Headless CLI

Run a full simulation in the terminal with no UI. Useful for bulk testing or overnight experiments.

```bash
cd backend
source venv/bin/activate
python main.py
```

Change `RESEARCH_TOPIC` and `DAYS` at the top of `main.py` before running. The full debate prints to the terminal. `evaluator.py` runs automatically when done.

---

## The database and seed fallback

Everything is stored in a single SQLite file at `backend/data/knowledge_base.db`. In Docker, this is bind-mounted to your host machine so you can inspect it at any time.

**Fallback logic:** if `knowledge_base.db` does not exist, the API automatically serves data from `demo_seed.db` so the dashboard is never empty. Once you click Run, a fresh `knowledge_base.db` is created and the API seamlessly switches to your live simulation data.

### Inspecting the database

```bash
cd backend
sqlite3 data/knowledge_base.db
```

```sql
-- All validated findings
SELECT day, author, title, confidence FROM findings;

-- Full conversation transcript
SELECT day, phase, agent, substr(content, 1, 100) FROM transcript;

-- All hypotheses and their outcomes
SELECT day, status, substr(content, 1, 120) FROM hypotheses;
```

---

## Tuning behaviour

### Change the research topic

**Web dashboard:** type it into the input field before clicking Run.

**CLI mode:** edit `RESEARCH_TOPIC` in `backend/main.py`.

### Change agent personalities

Edit system prompts in `backend/agents/personas.py`. The personality paragraph is the main lever — it controls tone, confidence, aggressiveness, and epistemic style. Try making the Devil's Advocate more aggressive and observe the impact on Knowledge Base quality.

### Switch models

In `backend/.env`:

```
GEMINI_MODEL=gemini-2.5-flash        # default — fast and cheap
GEMINI_EMBED_MODEL=text-embedding-004
```

---

## Common issues

**`Error: ports are not available: listen tcp 0.0.0.0:3000`**

Another process is using port 3000. Kill it:

```bash
npx kill-port 3000
# or find and kill manually
lsof -i :3000
kill -9 <PID>
```

**`ERROR: Your default credentials were not found` (inside Docker)**

Docker failed to read your `.env` file, so the Gemini SDK fell back to looking for Google Cloud credentials. Fix:

1. Ensure the file is named exactly `.env` inside the `backend/` folder.
2. Ensure there are no quotes around the API key value.
3. Force Docker to recreate the container:

```bash
docker compose up -d --force-recreate backend
```

**`JSON parse failed`**

Gemini occasionally returns non-JSON for a structured call. The code handles this gracefully, logs a warning, and continues. Not a crash — safe to ignore.

**`ResourceExhausted` / rate limit**

The LLM wrapper retries automatically after 30 seconds. If it happens often, switch to `gemini-2.0-flash` in your `.env`.

---

## Evaluation metrics (CLI mode)

After the simulation ends, `evaluator.py` runs automatically and reports:

| Metric | What it shows |
|--------|---------------|
| Hypothesis survival rate | Percentage of proposals that survived peer review |
| Belief drift | How agent confidence scores changed across days |
| Citation graph | Which agents cited whose work (epistemic authority) |
| Debate intensity | Challenge signal frequency per day |
