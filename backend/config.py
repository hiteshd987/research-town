"""
config.py — Central settings for Research Town.
Change values here to tune the simulation without touching any other file.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Reads .env file in the project root

# ─── Google / Gemini ──────────────────────────────────────────────────────────
# Option A: Gemini API key (simplest, works immediately)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Option B: Vertex AI (uncomment if using Vertex instead)
# VERTEX_PROJECT   = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")
# VERTEX_LOCATION  = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# Model to use for agent reasoning
# Options: "gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"
# REASONING_MODEL = "gemini-1.5-flash"   # flash = faster + cheaper for dev
# REASONING_MODEL = "gemini-1.5-pro"   # pro = smarter, use for final runs
raw_reason_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
REASONING_MODEL = raw_reason_model.replace("models/", "")

# Model to use for creating embeddings (memory retrieval)
EMBEDDING_MODEL = "text-embedding-004"

# ─── Simulation settings ─────────────────────────────────────────────────────
SIMULATION_DAYS    = 5        # How many "days" to run
RESEARCH_TOPIC     = "Can large language models develop genuine reasoning, or are they sophisticated pattern matchers?"

# Memory: how many past memories to retrieve and inject into each agent's prompt
MEMORY_RETRIEVAL_K = 4        # Top-K most relevant memories to fetch

# Temperature controls randomness. Higher = more creative / less predictable.
AGENT_TEMPERATURE  = 0.8

# Max tokens per agent response
MAX_TOKENS         = 4000

# ─── File paths ───────────────────────────────────────────────────────────────
DB_PATH            = "outputs/research_town.db"    # SQLite database
TRANSCRIPT_DIR     = "outputs/transcripts"         # Daily transcripts saved here
PAPER_OUTPUT       = "outputs/final_paper.md"      # The final synthesized paper
