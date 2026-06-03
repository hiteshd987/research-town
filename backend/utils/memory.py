"""
utils/memory.py — Agent memory and shared knowledge base.

Uses the new google-genai SDK (v2+) for embeddings.
The old google-generativeai package had broken model name resolution
for embedContent — this uses the replacement SDK which fixes it.

TWO CLASSES:
  EpisodicMemory  — per-agent personal memory (Gemini embeddings + SQLite)
  KnowledgeBase   — shared peer-reviewed facts (SQLite only)

WHY EMBEDDINGS AT ALL:
  Without embeddings, agents would only get their N most recent memories.
  With embeddings, an agent asking about "serotonin synthesis" on Day 5
  retrieves the most semantically relevant memory from Day 1 — even if
  Day 2-4 outputs have nothing to do with serotonin.
  Relevance > recency.

FALLBACK:
  If the embedding API fails (quota, network, bad key), _embed() returns
  None and retrieve() falls back to returning the N most recent memories.
  The simulation always runs — embeddings just improve memory quality.
"""

import sqlite3
import json
import os
import numpy as np
from typing import Optional

from google import genai
from google.genai import types

# ── Import the shared client from llm.py ─────────────────────────────────────
# Both files use the same Client object. We import it from llm.py rather than
# creating a second one — avoids double-loading the API key and .env file.
from utils.llm import client, EMBEDDING_MODEL


# ─────────────────────────────────────────────
# EMBEDDING HELPERS
# ─────────────────────────────────────────────

def _embed(text: str) -> Optional[list[float]]:
    """
    Generate a 768-dim vector for a text string using Gemini embeddings.

    Uses text-embedding-004 with RETRIEVAL_DOCUMENT task type,
    which is optimised for storing content that will later be
    retrieved by a query vector.

    Returns None on any failure — callers handle the fallback.
    We never let an embedding failure crash the simulation.
    """
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text[:8000],           # safety trim for token limit
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        # New SDK: response.embeddings is a list of EmbeddingResult objects
        # Each has a .values attribute (list of floats)
        return response.embeddings[0].values

    except Exception as e:
        print(f"  [Embedding error: {e}]")
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Cosine similarity between two vectors. Returns float in [-1, 1].
    1e-10 prevents division by zero for zero vectors.
    """
    va = np.array(a)
    vb = np.array(b)
    return float(
        np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-10)
    )


# ─────────────────────────────────────────────
# EPISODIC MEMORY
# Per-agent personal memory.
# Stored in SQLite, retrieved by semantic similarity.
# ─────────────────────────────────────────────

class EpisodicMemory:
    """
    Stores and retrieves an agent's personal memories.

    Every time an agent acts, their response is stored here with an
    embedding vector. On their next turn, we embed their current task
    and find the most semantically similar past responses to inject
    as context — making them seem to "remember" relevant past work.
    """

    def __init__(self, agent_name: str, data_dir: str = "data"):
        self.agent_name = agent_name
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "knowledge_base.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_table()

    def _init_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name  TEXT    NOT NULL,
                day         INTEGER NOT NULL,
                phase       TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                embedding   TEXT,               -- JSON float array, NULL if embed failed
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        self.conn.commit()

    def store(self, content: str, day: int, phase: str, metadata: Optional[dict] = None):
        """
        Store a memory after an agent acts.
        Embedding is generated here — one API call per agent turn.
        If embedding fails, content is still saved (embedding column = NULL).
        """
        vec = _embed(content)
        embedding_json = json.dumps(vec) if vec is not None else None

        self.conn.execute(
            """INSERT INTO episodic_memories
               (agent_name, day, phase, content, embedding)
               VALUES (?, ?, ?, ?, ?)""",
            (self.agent_name, day, phase, content, embedding_json)
        )
        self.conn.commit()

    def retrieve(self, query: str, n_results: int = 4) -> list[str]:
        """
        Retrieve the N most relevant past memories for a given query.

        If embeddings are available: semantic search (cosine similarity).
        If embeddings failed (NULL in DB): recency fallback (last N rows).

        Args:
            query:     Current task/context — used to find relevant memories.
            n_results: How many memories to return.

        Returns:
            List of content strings, best match first.
        """
        rows = self.conn.execute(
            """SELECT content, embedding FROM episodic_memories
               WHERE agent_name = ?
               ORDER BY id DESC""",
            (self.agent_name,)
        ).fetchall()

        if not rows:
            return []

        # Check if any embeddings exist
        rows_with_embeddings = [(c, e) for c, e in rows if e is not None]

        if rows_with_embeddings:
            # Semantic search path
            query_vec = _embed(query)

            if query_vec is not None:
                scored = []
                for content, emb_json in rows_with_embeddings:
                    mem_vec = json.loads(emb_json)
                    score = _cosine_similarity(query_vec, mem_vec)
                    scored.append((score, content))
                scored.sort(key=lambda x: x[0], reverse=True)
                return [content for _, content in scored[:n_results]]

        # Fallback: return the N most recent memories (rows already ordered DESC)
        return [content for content, _ in rows[:n_results]]

    def get_all(self, day: Optional[int] = None) -> list[str]:
        """Get all memories, optionally filtered by day."""
        if day is not None:
            rows = self.conn.execute(
                "SELECT content FROM episodic_memories WHERE agent_name=? AND day=?",
                (self.agent_name, day)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT content FROM episodic_memories WHERE agent_name=?",
                (self.agent_name,)
            ).fetchall()
        return [r[0] for r in rows]


# ─────────────────────────────────────────────
# CANONICAL KNOWLEDGE BASE
# Shared peer-reviewed facts for the whole town.
# Every agent reads this. Only the orchestrator writes to it.
# ─────────────────────────────────────────────

class KnowledgeBase:
    """
    The shared, permanent knowledge base.

    Think of this as the "published literature" of your simulation.
    Only validated findings (those that survived debate) enter here.
    All agents read it at the start of each day.
    """

    def __init__(self, data_dir: str = "data"):
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "knowledge_base.db")

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_tables()


    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS findings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                day         INTEGER,
                author      TEXT,
                title       TEXT,
                content     TEXT,
                confidence  REAL,
                domain      TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS hypotheses (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                day           INTEGER,
                content       TEXT,
                status        TEXT DEFAULT 'open',
                votes_for     INTEGER DEFAULT 0,
                votes_against INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS contradictions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                day         INTEGER,
                raised_by   TEXT,
                against     TEXT,
                content     TEXT,
                resolved    INTEGER DEFAULT 0,
                resolution  TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS transcript (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                day         INTEGER,
                phase       TEXT,
                agent       TEXT,
                content     TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    # ── Write ──────────────────────────────────────────────────────────────────

    def add_finding(self, day, author, title, content, confidence, domain="general"):
        self.conn.execute(
            "INSERT INTO findings (day,author,title,content,confidence,domain) VALUES (?,?,?,?,?,?)",
            (day, author, title, content, confidence, domain)
        )
        self.conn.commit()

    def add_hypothesis(self, day, content) -> int:
        cur = self.conn.execute(
            "INSERT INTO hypotheses (day,content) VALUES (?,?)", (day, content)
        )
        self.conn.commit()
        return cur.lastrowid

    def update_hypothesis(self, hypothesis_id, status, votes_for=0, votes_against=0):
        self.conn.execute(
            "UPDATE hypotheses SET status=?,votes_for=?,votes_against=? WHERE id=?",
            (status, votes_for, votes_against, hypothesis_id)
        )
        self.conn.commit()

    def add_contradiction(self, day, raised_by, against, content):
        self.conn.execute(
            "INSERT INTO contradictions (day,raised_by,against,content) VALUES (?,?,?,?)",
            (day, raised_by, against, content)
        )
        self.conn.commit()

    def log_transcript(self, day, phase, agent, content):
        self.conn.execute(
            "INSERT INTO transcript (day,phase,agent,content) VALUES (?,?,?,?)",
            (day, phase, agent, content)
        )
        self.conn.commit()

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_recent_findings(self, n=5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT day,author,title,content,confidence FROM findings ORDER BY id DESC LIMIT ?",
            (n,)
        ).fetchall()
        return [{"day":r[0],"author":r[1],"title":r[2],"content":r[3],"confidence":r[4]} for r in rows]

    def get_open_hypotheses(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id,day,content FROM hypotheses WHERE status='open' ORDER BY day DESC"
        ).fetchall()
        return [{"id":r[0],"day":r[1],"content":r[2]} for r in rows]

    def get_all_contradictions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT day,raised_by,against,content,resolved FROM contradictions ORDER BY day DESC"
        ).fetchall()
        return [{"day":r[0],"raised_by":r[1],"against":r[2],"content":r[3],"resolved":r[4]} for r in rows]

    def format_kb_summary(self) -> str:
        """
        Compact summary of validated findings + open hypotheses.
        This is injected into every agent's prompt at the start of each day —
        their shared 'morning briefing' of what the group knows so far.
        """
        findings   = self.get_recent_findings(5)
        hypotheses = self.get_open_hypotheses()
        lines      = []

        if findings:
            lines.append("=== VALIDATED FINDINGS ===")
            for f in findings:
                lines.append(f"[Day {f['day']} | {f['author']} | conf={f['confidence']:.1f}]")
                lines.append(f"  {f['title']}: {f['content'][:300]}")
        else:
            lines.append("=== No findings yet ===")

        if hypotheses:
            lines.append("\n=== OPEN HYPOTHESES ===")
            for h in hypotheses:
                lines.append(f"[Day {h['day']}] {h['content'][:200]}")

        return "\n".join(lines)
