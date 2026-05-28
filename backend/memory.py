"""
memory.py — The memory system for Research Town.

WHAT THIS FILE DOES:
  Agents have no built-in memory — every Gemini call starts fresh.
  This file creates the illusion of memory by:
    1. Storing everything in SQLite (text + metadata + embedding vectors)
    2. When an agent needs context, we embed their current task and find
       the most semantically similar past entries using cosine similarity
    3. Those retrieved entries get injected into their next prompt

THREE TABLES:
  memories       — per-agent episodic memory (their personal journal)
  knowledge_base — shared canonical facts (what survived peer review)
  hypotheses     — registry of all hypotheses with their current status

DESIGN DECISION — Why SQLite and not ChromaDB/Pinecone?
  We store embeddings as JSON blobs in SQLite and do cosine similarity
  in numpy. This means zero external services — the whole simulation
  runs with one .db file. For a research town with <10k entries, numpy
  cosine similarity over 768-dim vectors is fast enough (<50ms per query).
  Swap to ChromaDB later if you scale to millions of entries.
"""

import sqlite3
import json
import numpy as np
from datetime import datetime
from typing import Optional
from config import DB_PATH, MEMORY_RETRIEVAL_K
from gemini_client import embed


# ─── Database setup ───────────────────────────────────────────────────────────

def init_db():
    """
    Create all tables if they don't exist.
    Call this once at simulation startup.
    """
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # Per-agent episodic memory
    # Each row = one thing an agent observed, said, or decided
    c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name  TEXT    NOT NULL,
            day         INTEGER NOT NULL,
            phase       TEXT    NOT NULL,   -- 'briefing', 'work', 'debate', 'consensus'
            content     TEXT    NOT NULL,   -- the actual text
            embedding   TEXT    NOT NULL,   -- JSON-encoded list of floats
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Shared knowledge base — only consensus-approved findings live here
    c.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day         INTEGER NOT NULL,
            title       TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            source      TEXT    NOT NULL,   -- which agent produced it
            embedding   TEXT    NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Hypothesis registry — track the full lifecycle of each hypothesis
    c.execute("""
        CREATE TABLE IF NOT EXISTS hypotheses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day_proposed INTEGER NOT NULL,
            proposed_by  TEXT    NOT NULL,
            hypothesis   TEXT    NOT NULL,
            status       TEXT    DEFAULT 'active',  -- 'active', 'supported', 'rejected', 'modified'
            critique     TEXT    DEFAULT '',
            embedding    TEXT    NOT NULL,
            updated_at   TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


# ─── Memory operations ────────────────────────────────────────────────────────

def save_memory(agent_name: str, day: int, phase: str, content: str):
    """
    Store an agent's observation or output.
    Automatically generates an embedding for future retrieval.

    Call this after EVERY agent turn so nothing is lost.
    """
    vector    = embed(content)
    embedding = json.dumps(vector)  # Store as JSON string in SQLite

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO memories (agent_name, day, phase, content, embedding) VALUES (?,?,?,?,?)",
        (agent_name, day, phase, content, embedding)
    )
    conn.commit()
    conn.close()


def retrieve_memories(agent_name: str, query: str, k: int = MEMORY_RETRIEVAL_K) -> list[dict]:
    """
    Find the K most relevant past memories for a given agent + query.

    HOW IT WORKS:
      1. Embed the query string
      2. Load all past memories for this agent from SQLite
      3. Compute cosine similarity between query embedding and each memory
      4. Return top-K by similarity score

    This is semantic search — "protein folding mechanism" will match
    "how proteins achieve their 3D structure" even without keyword overlap.

    Args:
        agent_name: Only retrieve memories belonging to this agent
        query:      The current task/context — used to find relevant past events
        k:          Number of memories to return

    Returns:
        List of dicts with 'content', 'day', 'phase', 'score' keys
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT content, day, phase, embedding FROM memories WHERE agent_name = ? ORDER BY day DESC",
        (agent_name,)
    ).fetchall()
    conn.close()

    if not rows:
        return []

    query_vec = np.array(embed(query))

    scored = []
    for content, day, phase, emb_json in rows:
        mem_vec = np.array(json.loads(emb_json))
        # Cosine similarity: dot product of unit vectors
        # Returns 1.0 for identical, 0.0 for orthogonal, -1.0 for opposite
        score = float(np.dot(query_vec, mem_vec) / (
            np.linalg.norm(query_vec) * np.linalg.norm(mem_vec) + 1e-10
        ))
        scored.append({"content": content, "day": day, "phase": phase, "score": score})

    # Sort by score descending, return top K
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


# ─── Knowledge base operations ────────────────────────────────────────────────

def save_to_kb(day: int, title: str, content: str, source: str):
    """
    Add a finding to the shared canonical knowledge base.
    Only call this for content that survived peer review (in the consensus phase).
    """
    vector    = embed(content)
    embedding = json.dumps(vector)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO knowledge_base (day, title, content, source, embedding) VALUES (?,?,?,?,?)",
        (day, title, content, source, embedding)
    )
    conn.commit()
    conn.close()


def get_kb_summary(query: str = "", max_entries: int = 6) -> str:
    """
    Get a text summary of the most relevant knowledge base entries.
    This gets injected into every agent's prompt so they share a common ground truth.

    If query is provided, returns semantically relevant entries.
    If no query, returns the most recent entries.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT day, title, content, source, embedding FROM knowledge_base ORDER BY day DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return "The knowledge base is empty — this is Day 1."

    if query:
        query_vec = np.array(embed(query))
        scored = []
        for day, title, content, source, emb_json in rows:
            mem_vec = np.array(json.loads(emb_json))
            score   = float(np.dot(query_vec, mem_vec) / (
                np.linalg.norm(query_vec) * np.linalg.norm(mem_vec) + 1e-10
            ))
            scored.append((score, day, title, content, source))
        scored.sort(reverse=True)
        top = scored[:max_entries]
    else:
        top = [(0, r[0], r[1], r[2], r[3]) for r in rows[:max_entries]]

    lines = []
    for _, day, title, content, source in top:
        lines.append(f"[Day {day} | {source}] {title}\n  {content[:300]}...")

    return "\n\n".join(lines)


# ─── Hypothesis operations ────────────────────────────────────────────────────

def save_hypothesis(day: int, proposed_by: str, hypothesis: str) -> int:
    """
    Register a new hypothesis. Returns its ID for future updates.
    """
    vector    = embed(hypothesis)
    embedding = json.dumps(vector)

    conn  = sqlite3.connect(DB_PATH)
    cur   = conn.execute(
        "INSERT INTO hypotheses (day_proposed, proposed_by, hypothesis, embedding) VALUES (?,?,?,?)",
        (day, proposed_by, hypothesis, embedding)
    )
    hyp_id = cur.lastrowid
    conn.commit()
    conn.close()
    return hyp_id


def update_hypothesis(hyp_id: int, status: str, critique: str = ""):
    """
    Update a hypothesis status after peer review.
    status options: 'supported', 'rejected', 'modified'
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE hypotheses SET status=?, critique=?, updated_at=datetime('now') WHERE id=?",
        (status, critique, hyp_id)
    )
    conn.commit()
    conn.close()


def get_active_hypotheses() -> list[dict]:
    """Get all hypotheses that are still under investigation."""
    conn  = sqlite3.connect(DB_PATH)
    rows  = conn.execute(
        "SELECT id, day_proposed, proposed_by, hypothesis, status FROM hypotheses WHERE status='active'"
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "day": r[1], "by": r[2], "hypothesis": r[3], "status": r[4]}
        for r in rows
    ]


def get_all_hypotheses() -> list[dict]:
    """Get all hypotheses including resolved ones — for the final paper."""
    conn  = sqlite3.connect(DB_PATH)
    rows  = conn.execute(
        "SELECT id, day_proposed, proposed_by, hypothesis, status, critique FROM hypotheses"
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "day": r[1], "by": r[2], "hypothesis": r[3], "status": r[4], "critique": r[5]}
        for r in rows
    ]
