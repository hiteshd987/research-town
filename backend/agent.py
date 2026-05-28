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
        # The query is the current context — so we get memories relevant to
        # TODAY'S topic, not just the most recent memories
        query = f"{phase} {task} {context[:200]}"
        past_memories = self.memory.retrieve(query, n_results=3)

        # Step 2: Build the full user message
        # This is what the LLM sees as the "situation" today
        user_message = self._build_user_message(
            day=day,
            phase=phase,
            kb_summary=kb_summary,
            context=context,
            task=task,
            past_memories=past_memories
        )

        # Step 3: Call the LLM
        # The model sees: system_prompt (who am I) + user_message (what's happening)
        print(f"    → {self.name} thinking...")
        response = call_llm(self.system_prompt, user_message)

        # Step 4: Store this response in episodic memory
        # Next time this agent is called, this response may be retrieved
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
