"""
main.py — Run the Research Town simulation.

Usage:
    python main.py

Before running, set your Gemini API key:
    export GEMINI_API_KEY=your_key_here

  OR create a .env file in the project root:
    GEMINI_API_KEY=your_key_here

  OR if using Vertex AI instead:
    export GOOGLE_CLOUD_PROJECT=your-project-id
    gcloud auth application-default login
    Then switch the Vertex block in utils/llm.py and utils/memory.py

What this does:
    1. Creates all 5 agents with their locked-in personas
    2. Runs N days of the simulation
    3. Each day: hypothesis → research → debate → synthesis
    4. Commits validated findings to a SQLite knowledge base
    5. Runs evaluation analysis at the end

Change RESEARCH_TOPIC to simulate different fields.
Change DAYS to run longer (more expensive) or shorter simulations.
  3 days  ≈ 20 Gemini calls  (good for testing)
  5 days  ≈ 35 Gemini calls  (good for a full run)
  10 days ≈ 70 Gemini calls  (good for a deep study)
"""

import os
import sys

# Add project root to path so imports work regardless of where you run from
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import Orchestrator
from utils.evaluator import Evaluator


# ─────────────────────────────────────────────
# CONFIGURATION — Change these to run different experiments
# ─────────────────────────────────────────────

# RESEARCH_TOPIC = """
# The role of gut microbiome diversity in treatment-resistant depression:
# investigating whether microbial metabolites can modulate serotonin precursor
# availability in a way that explains differential SSRI response rates.
# """

RESEARCH_TOPIC = """
Investigating whether fine-tuning Large Language Models with specific 
symbolic logic constraints improves their generalized reasoning capabilities, 
or if it inevitably leads to catastrophic forgetting of broader conversational patterns.
"""

DAYS     = 3          # How many simulation days (3 = good for testing)
DATA_DIR = "data"     # Where to store the SQLite DB

# ─────────────────────────────────────────────


def main():
    # ── Verify Gemini API key is set ──────────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        print()
        print("Set it with:")
        print("  export GEMINI_API_KEY=your_key_here")
        print()
        print("Or create a .env file in this directory:")
        print("  GEMINI_API_KEY=your_key_here")
        print()
        print("Get a free key at: https://aistudio.google.com/app/apikey")
        sys.exit(1)

    # ── Create data directory ─────────────────────────────────────────────────
    os.makedirs(DATA_DIR, exist_ok=True)

    # ── Run the simulation ────────────────────────────────────────────────────
    orch = Orchestrator(
        research_topic=RESEARCH_TOPIC.strip(),
        data_dir=DATA_DIR
    )
    orch.run(days=DAYS)

    # ── Analyze what happened ─────────────────────────────────────────────────
    print("\n\nRunning post-simulation analysis...")
    evaluator = Evaluator(data_dir=DATA_DIR)
    evaluator.run_all()


if __name__ == "__main__":
    main()
