"""
gemini_client.py — Single wrapper around the Google Generative AI SDK.

WHY THIS EXISTS:
  All 5 agents call the LLM. If we scattered `genai.GenerativeModel(...)` calls
  across every file, switching models or adding retry logic would mean editing
  5 different places. Instead, everything goes through two functions here:
    - generate()   → get a text response from Gemini
    - embed()      → turn text into a vector (for memory retrieval)

USAGE:
  from gemini_client import generate, embed
  response = generate(system_prompt="You are...", user_message="What do you think about X?")
  vector   = embed("some text to embed")
"""

import google.generativeai as genai
from config import (
    GEMINI_API_KEY,
    REASONING_MODEL,
    EMBEDDING_MODEL,
    AGENT_TEMPERATURE,
    MAX_TOKENS,
)

# ─── Initialise the SDK once at import time ───────────────────────────────────
# This call configures the global SDK state. You only need to do this once.
genai.configure(api_key=GEMINI_API_KEY)


def generate(system_prompt: str, user_message: str, temperature: float = None) -> str:
    """
    Send a prompt to Gemini and return the text response.

    Args:
        system_prompt:  The agent's persona + instructions. This is what makes
                        each agent different from the others.
        user_message:   The specific task or context for this turn.
        temperature:    Overrides AGENT_TEMPERATURE if provided.

    Returns:
        The model's response as a plain string.

    HOW GEMINI SYSTEM PROMPTS WORK:
        Unlike OpenAI where system is a separate message role, Gemini takes
        system_instruction as a constructor argument on the model object.
        We build a fresh model instance per call — this is cheap, no connection
        overhead, and lets us vary temperature per call if needed.
    """
    temp = temperature if temperature is not None else AGENT_TEMPERATURE

    model = genai.GenerativeModel(
        model_name=REASONING_MODEL,
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            temperature=temp,
            max_output_tokens=MAX_TOKENS,
            # top_p and top_k left at defaults — safe starting point
        ),
    )

    try:
        response = model.generate_content(user_message)
        # response.text is the string content of the first candidate
        return response.text.strip()

    except Exception as e:
        # Rather than crashing the whole simulation on a single failed call,
        # we return an error string the orchestrator can log and continue.
        print(f"[GeminiClient] Generation error: {e}")
        return f"[ERROR: {str(e)}]"


def embed(text: str) -> list[float]:
    """
    Convert text into a vector using Gemini's embedding model.

    This is used by the memory system to store and retrieve relevant memories.
    When an agent needs context, we embed their current task and find the
    most semantically similar past memories — not just keyword matches.

    Args:
        text: Any string — an agent response, a hypothesis, a paper summary.

    Returns:
        A list of floats (the embedding vector). Gemini text-embedding-004
        produces 768-dimensional vectors.
    """
    try:
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_document",  # optimised for storage + retrieval
        )
        return result["embedding"]

    except Exception as e:
        print(f"[GeminiClient] Embedding error: {e}")
        # Return a zero vector as fallback — memory retrieval will score it low
        return [0.0] * 768


# ─── Vertex AI alternative ────────────────────────────────────────────────────
# If you prefer Vertex over the direct Gemini API, replace the functions above
# with the block below. Everything else in the project stays identical.
#
# import vertexai
# from vertexai.generative_models import GenerativeModel, GenerationConfig
# from vertexai.language_models import TextEmbeddingModel
# from config import VERTEX_PROJECT, VERTEX_LOCATION
#
# vertexai.init(project=VERTEX_PROJECT, location=VERTEX_LOCATION)
#
# def generate(system_prompt, user_message, temperature=None):
#     temp = temperature or AGENT_TEMPERATURE
#     model = GenerativeModel(REASONING_MODEL, system_instruction=system_prompt)
#     resp  = model.generate_content(
#         user_message,
#         generation_config=GenerationConfig(temperature=temp, max_output_tokens=MAX_TOKENS)
#     )
#     return resp.text.strip()
#
# def embed(text):
#     model  = TextEmbeddingModel.from_pretrained("text-embedding-004")
#     result = model.get_embeddings([text])
#     return result[0].values
