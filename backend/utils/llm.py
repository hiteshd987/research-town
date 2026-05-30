"""
utils/llm.py — The only file that calls the Gemini API.

Uses the current google-genai SDK (v2+).
The old google-generativeai package is deprecated and has broken
embedding model support — this uses the replacement SDK.

Two public functions:
  call_llm()       → plain text response  (used by every agent turn)
  call_llm_json()  → parsed dict response (used by orchestrator KB commit)

VERTEX AI:
  See the commented block at the bottom. Swap by setting USE_VERTEX=true
  in your .env. No other files change.
"""

import json
import time
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.api_core import exceptions as google_exceptions

# ── Load .env BEFORE reading any env vars ─────────────────────────────────────
# Must be here — this module is imported before main.py runs its own setup.
# override=False: real shell env vars take priority over .env values.
load_dotenv(override=False)

# ── Build the client once at module level ─────────────────────────────────────
# The new SDK uses a Client object instead of module-level configuration.
# One client handles both generation and embeddings.
# Check if we are using Vertex AI
use_vertex = os.environ.get("USE_VERTEX", "false").lower() == "true"

if use_vertex:
    project_id = os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if not project_id:
        raise ValueError("GCP_PROJECT_ID is missing from .env, but USE_VERTEX is true.")
        
    print(f"[INFO] Initializing Vertex AI Client (Project: {project_id}, Region: {location})")
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=location
    )
else:
    # Fallback to standard API key
    _api_key = os.environ.get("GEMINI_API_KEY", "")
    if not _api_key:
        print("[WARNING] GEMINI_API_KEY not found. Ensure USE_VERTEX is true or provide a key.")
    
    print("[INFO] Initializing standard Gemini API Client")
    client = genai.Client(api_key=_api_key)

# ── Model selection ───────────────────────────────────────────────────────────
# gemini-2.0-flash  → fast, cheap, good for most agent work
# gemini-1.5-flash  → slightly older but widely available
# gemini-1.5-pro    → smarter, slower, use for final runs
REASONING_MODEL  = os.environ.get("GEMINI_MODEL",     "gemini-2.5-flash")
EMBEDDING_MODEL  = os.environ.get("GEMINI_EMBED_MODEL","text-embedding-004")


def call_llm(system_prompt: str, user_message: str, max_tokens: int = 4000) -> str:
    """
    Single Gemini call. Returns the text response as a plain string.

    HOW IT WORKS IN THE NEW SDK:
      client.models.generate_content() takes:
        - model:    the model string
        - contents: the user message (just a string)
        - config:   GenerateContentConfig holds system_instruction, temperature, etc.

      system_instruction now lives inside GenerateContentConfig,
      not as a constructor argument on a model object.

    Args:
        system_prompt: The agent's full persona. Sets who the model thinks it is.
        user_message:  Today's context — KB summary, memories, task, phase.
        max_tokens:    Max response length.

    Returns:
        Model response as a plain string. Returns an error string on failure
        so the simulation can continue rather than crash on one bad call.
    """
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.8,
        max_output_tokens=max_tokens,
    )

    try:
        response = client.models.generate_content(
            model=REASONING_MODEL,
            contents=user_message,
            config=config,
        )
        return response.text.strip()

    except google_exceptions.ResourceExhausted:
        # Quota hit — either per-minute or per-day limit
        print("  [Rate limited — waiting 30s before retry]")
        time.sleep(30)
        return call_llm(system_prompt, user_message, max_tokens)

    except google_exceptions.InvalidArgument as e:
        print(f"  [Invalid argument: {e}]")
        return f"ERROR: {str(e)}"

    except Exception as e:
        print(f"  [LLM error: {e}]")
        return f"ERROR: {str(e)}"


def call_llm_json(system_prompt: str, user_message: str) -> dict:
    """
    Same as call_llm but parses the response as JSON.

    Used by the orchestrator to extract structured KB decisions
    from the archivist's freeform synthesis text.

    Gemini sometimes wraps JSON in markdown fences despite explicit
    instructions — we strip those before parsing.
    """
    json_system = (
        system_prompt
        + "\n\nCRITICAL: Respond with ONLY valid JSON. "
          "No markdown fences, no backticks, no explanation. "
          "Start with { and end with }."
    )

    raw = call_llm(json_system, user_message, max_tokens=1000)

    try:
        cleaned = raw.strip()
        # Strip ```json ... ``` or ``` ... ``` if present
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            # parts[1] is the content between the first pair of fences
            cleaned = parts[1].lstrip("json").strip()
        return json.loads(cleaned)

    except json.JSONDecodeError:
        print(f"  [JSON parse failed. Preview: {raw[:200]}]")
        return {}
