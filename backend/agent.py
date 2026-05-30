"""
agent.py — The Agent class.

An agent is three things glued together:
  1. A PERSONA  — who they are (system prompt, personality, output format)
  2. A MEMORY   — what they've done and seen (EpisodicMemory)
  3. An ACT method — takes context, returns structured response

The LLM is stateless. The Agent class is what makes it stateful.
Every time act() is called, it:
  - Retrieves relevant memories
  - Builds a full context prompt
  - Calls the LLM
  - Stores the response in memory
  - Returns the parsed response
"""

from utils.llm import call_llm
from utils.memory import EpisodicMemory
from agents.personas import get_persona


class Agent:
    """
    A single research agent in the simulation.

    Usage:
        agent = Agent("lead_scientist", data_dir="data")
        response = agent.act(
            day=1,
            phase="hypothesis",
            kb_summary="...today's knowledge base...",
            context="...what happened so far today..."
        )
        print(response)
    """

    def __init__(self, persona_key: str, data_dir: str = "data"):
        self.persona = get_persona(persona_key)
        self.name = self.persona["name"]
        self.role = self.persona["role"]
        self.system_prompt = self.persona["system_prompt"]
        self.memory = EpisodicMemory(self.name, data_dir)

        print(f"  ✓ Agent initialized: {self.name} ({self.role})")

    def act(self, day: int, phase: str, kb_summary: str,
            context: str, task: str = "") -> str:
        """
        The core method. Called once per agent per phase per day.

        Args:
            day:        Which simulation day this is (1, 2, 3...)
            phase:      Which phase ("hypothesis", "research", "critique", etc.)
            kb_summary: Formatted summary of the shared knowledge base
            context:    What's happened today so far (other agents' outputs)
            task:       Specific task assigned to this agent (optional)

        Returns:
            The agent's response as a plain string.
        """

        # Step 1: Retrieve relevant episodic memories
        query = f"{phase} {task} {context[:200]}"
        past_memories = self.memory.retrieve(query, n_results=3)

        # ── CONTEXT VISIBILITY LOG ───────────────────────────────────
        # Prints everything this agent is about to receive so you can
        # confirm what information they are actually working with.
        print(f"\n  ┌─ {self.name} | Day {day} | Phase: {phase}")

        # KB summary — shared validated knowledge
        if kb_summary.strip() and kb_summary.strip() != "(Empty — first day of research)":
            kb_lines = kb_summary.strip().splitlines()
            print(f"  │  KB Summary ({len(kb_lines)} lines):")
            for line in kb_lines[:4]:   # show first 4 lines
                print(f"  │    {line[:90]}")
            if len(kb_lines) > 4:
                print(f"  │    ... ({len(kb_lines) - 4} more lines)")
        else:
            print(f"  │  KB Summary: empty (Day 1)")

        # Previous debate passed as context (only lead scientist gets this)
        if context.strip():
            ctx_lines = context.strip().splitlines()
            print(f"  │  Context ({len(ctx_lines)} lines, first 3):")
            for line in ctx_lines[:3]:
                print(f"  │    {line[:90]}")
            if len(ctx_lines) > 3:
                print(f"  │    ... ({len(ctx_lines) - 3} more lines)")
        else:
            print(f"  │  Context: none")

        # Episodic memories retrieved from vector search
        # Format: rank | Day X | phase | first 70 chars of content
        # "Day X / phase:" prefix is stored by memory.store() so we
        # split on it to show metadata and content separately.
        if past_memories:
            print(f"  │  Memories retrieved ({len(past_memories)}) — ranked by relevance:")
            for i, mem in enumerate(past_memories, 1):
                # Memory is stored as "Day N / phase: <content>"
                # Split into label and body for clean display
                if ": " in mem[:30]:
                    label_part, body = mem.split(": ", 1)
                    label_part = label_part.strip()   # e.g. "Day 2 / research"
                    body = body.strip()[:70]
                else:
                    label_part = f"Memory {i}"
                    body = mem.strip()[:70]
                rank_label = ["1st (most relevant)", "2nd", "3rd", "4th"][min(i-1, 3)]
                print(f"  │    {rank_label:<20} | {label_part:<20} | {body}...")
        else:
            print(f"  │  Memories retrieved: none (first turn for this agent)")

        print(f"  └─ calling Gemini...")
        # ─────────────────────────────────────────────────────────────

        # Step 2: Build the full user message
        user_message = self._build_user_message(
            day=day,
            phase=phase,
            kb_summary=kb_summary,
            context=context,
            task=task,
            past_memories=past_memories
        )

        # Step 3: Call the LLM
        response = call_llm(self.system_prompt, user_message)

        # Step 4: Store response in episodic memory
        memory_content = f"Day {day} / {phase}: {response}"
        self.memory.store(memory_content, day=day, phase=phase)

        return response

    def _build_user_message(self, day: int, phase: str, kb_summary: str,
                             context: str, task: str, past_memories: list[str]) -> str:
        """
        Build the full context prompt for this agent's turn.

        The structure matters — most important info goes LAST
        because LLMs pay more attention to the end of their context.
        """
        parts = []

        # Who I am and the current situation
        parts.append(f"=== DAY {day} | PHASE: {phase.upper()} ===\n")

        # Shared knowledge base — what everyone knows
        parts.append("--- SHARED KNOWLEDGE BASE ---")
        parts.append(kb_summary if kb_summary.strip() else "(Empty — first day of research)")
        parts.append("")

        # Your personal memories — what YOU specifically remember
        if past_memories:
            parts.append("--- YOUR RELEVANT MEMORIES ---")
            for i, mem in enumerate(past_memories, 1):
                # Truncate long memories to keep prompt manageable
                parts.append(f"[{i}] {mem[:400]}")
            parts.append("")

        # What happened today so far — other agents' outputs
        if context.strip():
            parts.append("--- TODAY'S CONTEXT (what's happened so far today) ---")
            parts.append(context[:2000])  # Cap at 2000 chars to control cost
            parts.append("")

        # Your specific task for this phase
        if task.strip():
            parts.append("--- YOUR TASK ---")
            parts.append(task)
            parts.append("")

        # Reminder of output format (gentle nudge to follow the persona format)
        parts.append("--- YOUR RESPONSE ---")
        parts.append(f"Respond as {self.name}. Follow your output format exactly.")

        return "\n".join(parts)

    def __repr__(self):
        return f"Agent(name={self.name!r}, role={self.role!r})"