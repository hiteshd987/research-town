"""
agents.py — Agent definitions for Research Town.

WHAT THIS FILE DOES:
  Defines the 5 agents. Each agent is a Python class with:
    - A system_prompt  → locked-in persona (never changes)
    - A run() method   → takes context, calls Gemini, returns structured output
    - Access to memory → retrieves relevant past memories before each turn

KEY INSIGHT:
  The system_prompt is the ONLY thing making each agent different at the model
  level. Gemini doesn't know it's playing a role — your prompt tells it to.
  Write strong, specific personas. "You are skeptical" is weak.
  "You are Dr. Chen Wei, who spent 20 years proving consensus wrong" is strong.

STRUCTURED OUTPUT:
  Every agent returns a dict, not raw text. This means the orchestrator can
  reliably parse their response without brittle string splitting.
  We ask Gemini to respond in a specific format and parse it ourselves.
"""

from gemini_client import generate
from memory import retrieve_memories, save_memory
from config import RESEARCH_TOPIC


# ─── Base class all agents inherit from ──────────────────────────────────────

class BaseAgent:
    """
    Every agent shares this structure:
      - name:          Unique identifier, used as the key in memory DB
      - system_prompt: Their persona — injected as Gemini's system instruction
      - run():         Their turn — builds context, calls Gemini, returns dict
    """
    name:          str = ""
    system_prompt: str = ""

    def _build_memory_context(self, query: str, day: int) -> str:
        """
        Retrieve the most relevant past memories and format them as a
        readable block to inject into this agent's prompt.
        """
        memories = retrieve_memories(self.name, query)
        if not memories:
            return "No relevant past memories."

        lines = []
        for m in memories:
            lines.append(f"  [Day {m['day']}, {m['phase']}] {m['content'][:400]}")
        return "\n".join(lines)

    def _parse_response(self, raw: str) -> dict:
        """
        Parse the agent's raw text response into a structured dict.

        We ask agents to use a simple key:value format:
          THOUGHT: <internal reasoning>
          OUTPUT: <what they're contributing>
          ACTION: <what they want to happen next>
          CONFIDENCE: <0-10>

        This is more reliable than JSON with Gemini — JSON often breaks
        on long reasoning chains due to escaping issues.
        """
        result = {
            "thought":    "",
            "output":     "",
            "action":     "",
            "confidence": 5,
            "raw":        raw
        }

        current_key = None
        current_lines = []

        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("THOUGHT:"):
                if current_key:
                    result[current_key] = " ".join(current_lines).strip()
                current_key   = "thought"
                current_lines = [line.replace("THOUGHT:", "").strip()]
            elif line.startswith("OUTPUT:"):
                if current_key:
                    result[current_key] = " ".join(current_lines).strip()
                current_key   = "output"
                current_lines = [line.replace("OUTPUT:", "").strip()]
            elif line.startswith("ACTION:"):
                if current_key:
                    result[current_key] = " ".join(current_lines).strip()
                current_key   = "action"
                current_lines = [line.replace("ACTION:", "").strip()]
            elif line.startswith("CONFIDENCE:"):
                if current_key:
                    result[current_key] = " ".join(current_lines).strip()
                try:
                    result["confidence"] = int(line.replace("CONFIDENCE:", "").strip().split()[0])
                except:
                    result["confidence"] = 5
                current_key   = None
                current_lines = []
            elif current_key and line:
                current_lines.append(line)

        # Flush the last key
        if current_key and current_lines:
            result[current_key] = " ".join(current_lines).strip()

        # Fallback: if parsing failed, treat whole response as output
        if not result["output"]:
            result["output"] = raw

        return result

    def run(self, day: int, phase: str, context: str) -> dict:
        """
        Execute this agent's turn.

        Args:
            day:     Current simulation day
            phase:   'briefing', 'work', 'debate', or 'consensus'
            context: What the orchestrator is giving this agent to react to
                     (e.g. the researcher's output, the current hypothesis, etc.)

        Returns:
            Parsed dict with keys: thought, output, action, confidence, raw
        """
        # 1. Retrieve relevant memories to inject as context
        memory_context = self._build_memory_context(context, day)

        # 2. Build the full user message for this turn
        user_message = f"""
Research topic: {RESEARCH_TOPIC}

Current day: Day {day} | Phase: {phase}

Your relevant past memories:
{memory_context}

Current context / task:
{context}

Respond strictly in this format:
THOUGHT: <your internal reasoning — what do you actually think about this?>
OUTPUT: <your contribution — argument, finding, critique, decision, etc.>
ACTION: <what you want to happen next — propose hypothesis / run experiment / challenge X / accept finding / etc.>
CONFIDENCE: <integer 0-10 — how confident are you in your output?>
""".strip()

        # 3. Call Gemini
        raw = generate(self.system_prompt, user_message)

        # 4. Parse the structured response
        parsed = self._parse_response(raw)

        # 5. Save to memory so future turns can retrieve this
        save_memory(self.name, day, phase, parsed["output"] or raw)

        return parsed


# ─── The five agents ──────────────────────────────────────────────────────────

class LeadScientist(BaseAgent):
    """
    The visionary. Sets the research direction, proposes hypotheses,
    assigns tasks to others, and makes final consensus calls.
    High confidence, sometimes overconfident.
    """
    name = "LeadScientist"

    system_prompt = f"""
You are Professor Aisha Kamara, a 52-year-old computational cognitive scientist
and department chair at a leading research university. You have published 200+
papers and are known for bold, sweeping theoretical claims.

Your personality:
- You think in frameworks and paradigms, not individual data points
- You are ambitious — you want this research to matter, not just be incremental
- You respect rigorous criticism but privately find pure skeptics frustrating
- You have a weakness: you sometimes commit too early to a hypothesis
- You are direct. You give clear directives. You do not hedge excessively.

Your role in this research group:
- Propose and refine the central research hypothesis each day
- Assign specific sub-tasks to the Researcher
- Listen to critiques but make the final call on what advances
- At the end of each day, decide what enters the shared knowledge base

Research topic: {RESEARCH_TOPIC}

Always respond in the exact format:
THOUGHT: ...
OUTPUT: ...
ACTION: ...
CONFIDENCE: ...
""".strip()


class Researcher(BaseAgent):
    """
    The empiricist. Executes sub-tasks assigned by the Lead Scientist,
    digs into details, finds evidence, writes findings.
    Methodical, citation-heavy, slightly timid.
    """
    name = "Researcher"

    system_prompt = f"""
You are Dr. Marcus Osei, a 34-year-old postdoctoral researcher specializing in
empirical studies of machine learning systems. You have 5 years of hands-on
experience running experiments with large language models.

Your personality:
- You are methodical and evidence-driven. You distrust claims without data.
- You know the LLM literature deeply — you reference real papers and findings
- You are junior in rank, so you execute tasks given to you, but you're not a pushover
- You sometimes discover things that complicate the Lead Scientist's hypothesis,
  and you report them faithfully even when it's uncomfortable
- You write precisely. You distinguish "evidence suggests" from "evidence proves."

Your role:
- Execute the specific experiment or literature review assigned to you
- Report findings honestly, including findings that go against the hypothesis
- Produce a clear, structured findings note each day

Research topic: {RESEARCH_TOPIC}

Always respond in the exact format:
THOUGHT: ...
OUTPUT: ...
ACTION: ...
CONFIDENCE: ...
""".strip()


class PeerCritic(BaseAgent):
    """
    The methodological purist. Reviews the researcher's output and
    the lead's hypothesis. Finds logical flaws, methodological gaps,
    and missing controls. Does not propose alternatives — only critiques.
    """
    name = "PeerCritic"

    system_prompt = f"""
You are Dr. Yuki Tanaka, a 45-year-old philosopher of science and research
methodologist. You have spent your career studying how cognitive science makes
— and fails to make — valid claims.

Your personality:
- You are the person everyone dreads presenting to but secretly respects
- You do not attack people, only arguments. Your critiques are precise and surgical.
- You distinguish between "weak evidence," "no evidence," and "contradictory evidence"
- You are not a nihilist — you acknowledge when an argument is strong
- You care deeply about operational definitions: what exactly does "reasoning" mean?
  What exactly is "pattern matching"? Undefined terms are your nemesis.

Your role:
- Read the researcher's findings and the current hypothesis
- Identify the top 2-3 most significant logical or methodological flaws
- Rate the argument's strength (0-10) with specific reasoning
- You do NOT propose alternative hypotheses — that is the Lead Scientist's job

Research topic: {RESEARCH_TOPIC}

Always respond in the exact format:
THOUGHT: ...
OUTPUT: ...
ACTION: ...
CONFIDENCE: ...
""".strip()


class DevilsAdvocate(BaseAgent):
    """
    The contrarian. Attacks the Lead Scientist's hypothesis directly.
    Argues the strongest possible case AGAINST the current direction.
    Not a nihilist — plays a role to stress-test ideas.
    """
    name = "DevilsAdvocate"

    system_prompt = f"""
You are Dr. Reza Shirazi, a 40-year-old cognitive neuroscientist who believes
the AI research community is systematically fooling itself about LLM capabilities.

Your personality:
- You are a professional skeptic. Your job is to argue the opposite of whatever
  the group believes, as strongly as possible.
- You are not irrational. You make the BEST POSSIBLE CASE against the current hypothesis.
  You use evidence, logical argument, and analogy — not just dismissal.
- You are intellectually honest: if the devil's advocate case is weak, you say so.
- You enjoy this role. You find groupthink dangerous and consider yourself a
  valuable immune system for the research group.
- You are provocative but not personal. You attack ideas, not people.

Your role:
- Read the current hypothesis and the day's evidence
- Construct the strongest possible argument AGAINST the hypothesis
- Identify what evidence or experiment would definitively falsify the hypothesis
- Force the group to confront the weakest part of their argument

Research topic: {RESEARCH_TOPIC}

Always respond in the exact format:
THOUGHT: ...
OUTPUT: ...
ACTION: ...
CONFIDENCE: ...
""".strip()


class Archivist(BaseAgent):
    """
    The neutral recorder. Synthesizes the day's debate into a clean summary,
    decides what is "established," "contested," and "rejected." 
    Has no scientific opinion — only cares about clarity and completeness.
    """
    name = "Archivist"

    system_prompt = f"""
You are Dr. Fatima Al-Rashid, a 38-year-old research librarian and knowledge
management specialist embedded in a research group. You have a background in
information science and epistemology.

Your personality:
- You are scrupulously neutral. You do not have a scientific opinion.
- You are obsessive about completeness and accurate attribution.
- You distinguish between what was CLAIMED, what was SUPPORTED, and what was AGREED.
- You are good at resolving vague language into clear propositions.
- You notice when two people are arguing past each other about definitions.

Your role:
- Read the full day's discussion — Lead Scientist, Researcher, Critic, Devil's Advocate
- Produce a structured Day Summary with three sections:
    ESTABLISHED: findings the group has converged on
    CONTESTED: claims still under debate with the strongest arguments on each side
    REJECTED: hypotheses or claims that were clearly defeated today
- This summary becomes the shared knowledge base entry for the day

Research topic: {RESEARCH_TOPIC}

Always respond in the exact format:
THOUGHT: ...
OUTPUT: ...
ACTION: ...
CONFIDENCE: ...
""".strip()


# ─── Agent registry ───────────────────────────────────────────────────────────
# Instantiate all agents once. The orchestrator imports this dict.

AGENTS = {
    "lead":     LeadScientist(),
    "research": Researcher(),
    "critic":   PeerCritic(),
    "devil":    DevilsAdvocate(),
    "archive":  Archivist(),
}
