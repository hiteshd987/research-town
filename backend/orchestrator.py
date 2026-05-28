"""
orchestrator.py — The daily loop. The director of the simulation.

This is the most important file for emergent behavior.
The orchestrator decides:
  - What order agents act in
  - What information each agent gets (information asymmetry!)
  - Who gets to respond to whom
  - What survives into the canonical KB

The simulation runs in 4 phases each day:

  PHASE 1 — HYPOTHESIS
    Lead scientist reads the KB and proposes today's hypothesis.
    Also assigns tasks to each team member.

  PHASE 2 — RESEARCH
    Researcher executes their assigned task.
    Produces a findings report.

  PHASE 3 — DEBATE
    Critic reviews the researcher's findings.
    Devil's advocate challenges the lead scientist's hypothesis.
    These happen in parallel (but we run them sequentially for simplicity).

  PHASE 4 — SYNTHESIS
    Archivist reads everything from today.
    Writes an objective summary.
    Recommends what goes into the KB.
    Orchestrator commits recommendations to the KB.

KEY DESIGN CHOICE — Information asymmetry:
  The devil's advocate does NOT see the researcher's findings before challenging.
  They only see the hypothesis. This prevents them from just critiquing the method
  and forces them to challenge the fundamental premise.
"""

import json
import re
from agent import Agent
from utils.memory import KnowledgeBase
from utils.llm import call_llm_json


class Orchestrator:
    """
    Runs the multi-agent research simulation.

    Usage:
        orch = Orchestrator(research_topic="CRISPR off-target effects in gene therapy")
        orch.run(days=5)
    """

    def __init__(self, research_topic: str, data_dir: str = "data"):
        self.research_topic = research_topic
        self.data_dir = data_dir
        self.current_day = 0
        self.kb = KnowledgeBase(data_dir)

        print(f"\n{'='*60}")
        print(f"RESEARCH TOWN — Initializing")
        print(f"Topic: {research_topic}")
        print(f"{'='*60}\n")

        # Initialize all agents
        print("Initializing agents...")
        self.agents = {
            "lead":       Agent("lead_scientist",  data_dir),
            "researcher": Agent("researcher",       data_dir),
            "critic":     Agent("critic",           data_dir),
            "devil":      Agent("devils_advocate",  data_dir),
            "archivist":  Agent("archivist",        data_dir),
        }
        print()

    def run(self, days: int = 3):
        """Run the simulation for N days."""
        print(f"Starting {days}-day simulation...\n")

        for day in range(1, days + 1):
            print(f"\n{'='*60}")
            print(f"  DAY {day}")
            print(f"{'='*60}")
            self._run_day(day)

        print(f"\n{'='*60}")
        print("SIMULATION COMPLETE")
        print(f"{'='*60}")
        self._print_final_summary()

    # ─────────────────────────────────────────────
    # DAILY LOOP
    # ─────────────────────────────────────────────

    def _run_day(self, day: int):
        """Run one full day of the simulation."""
        self.current_day = day

        # Get the current state of the knowledge base
        # This is what every agent reads at the start of the day
        kb_summary = self.kb.format_kb_summary()

        # ── Phase 1: Hypothesis ──────────────────
        print(f"\n[Phase 1: Hypothesis]")
        hypothesis_response = self._phase_hypothesis(day, kb_summary)

        # ── Phase 2: Research ────────────────────
        print(f"\n[Phase 2: Research]")
        research_response = self._phase_research(day, kb_summary, hypothesis_response)

        # ── Phase 3: Debate ──────────────────────
        print(f"\n[Phase 3: Debate]")
        critique_response, devils_response = self._phase_debate(
            day, kb_summary, hypothesis_response, research_response
        )

        # ── Phase 4: Synthesis ───────────────────
        print(f"\n[Phase 4: Synthesis]")
        self._phase_synthesis(
            day, kb_summary,
            hypothesis_response, research_response,
            critique_response, devils_response
        )

    # ─────────────────────────────────────────────
    # PHASES
    # ─────────────────────────────────────────────

    def _phase_hypothesis(self, day: int, kb_summary: str) -> str:
        """
        Lead scientist proposes today's hypothesis and assigns tasks.

        Context: Just the KB + the research topic.
        No other agents have acted yet — clean slate each day.
        """
        task = f"""
We are researching: {self.research_topic}

Day {day} of the investigation.

Your job today:
1. Propose ONE clear, testable hypothesis based on the knowledge base state
2. Assign specific tasks to Dr. Watanabe (researcher), Dr. Al-Rashid (critic), and Prof. Holt (devil's advocate)
3. Be specific — vague tasks produce vague results

Remember: bold hypotheses are better than safe ones. We're here to advance knowledge, not confirm what we already know.
        """

        response = self.agents["lead"].act(
            day=day, phase="hypothesis",
            kb_summary=kb_summary, context="", task=task
        )

        self.kb.log_transcript(day, "hypothesis", self.agents["lead"].name, response)
        self._print_agent_output("Lead Scientist", response)
        
        # ---> UPDATE THIS LINE: Capture the ID <---
        self.current_hypothesis_id = self.kb.add_hypothesis(day=day, content=response[:200])

        return response

    def _phase_research(self, day: int, kb_summary: str, hypothesis_response: str) -> str:
        """
        Researcher investigates the assigned task.

        Context: Includes the lead scientist's hypothesis and task assignment.
        The researcher must build on the KB and report honestly.
        """
        task = f"""
Review Dr. Osei's hypothesis and your assigned task above.
Conduct a thorough investigation. Be honest about uncertainty.
If the evidence is weak, say so — a confident wrong answer is worse than an uncertain right one.

Research topic context: {self.research_topic}
        """

        response = self.agents["researcher"].act(
            day=day, phase="research",
            kb_summary=kb_summary,
            context=f"LEAD SCIENTIST'S HYPOTHESIS AND TASK:\n{hypothesis_response}",
            task=task
        )

        self.kb.log_transcript(day, "research", self.agents["researcher"].name, response)
        self._print_agent_output("Researcher", response)
        return response

    def _phase_debate(self, day: int, kb_summary: str,
                      hypothesis_response: str, research_response: str) -> tuple[str, str]:
        """
        Critic and devil's advocate challenge the work.

        KEY ASYMMETRY:
          - Critic sees: researcher's findings (they critique the METHOD)
          - Devil's advocate sees: lead scientist's hypothesis (they attack the PREMISE)
          They don't see each other's challenges until the synthesis phase.
          This produces independent, non-redundant challenges.
        """

        # Critic reviews the researcher's findings
        critic_task = f"""
Review Dr. Watanabe's findings report above with your sharpest eye.
Find the single most important flaw. Don't pile on — one focused objection
is more useful than five minor ones. Be specific about what would fix it.
        """

        critique_response = self.agents["critic"].act(
            day=day, phase="critique",
            kb_summary=kb_summary,
            context=f"RESEARCHER'S FINDINGS TO REVIEW:\n{research_response}",
            task=critic_task
        )
        self.kb.log_transcript(day, "critique", self.agents["critic"].name, critique_response)
        self._print_agent_output("Peer Critic", critique_response)

        # Devil's advocate attacks the hypothesis (NOT the research method)
        # Note: they only see the hypothesis, not the research findings
        devils_task = f"""
Attack Dr. Osei's hypothesis at its foundations.
Don't critique the methodology — that's Dr. Al-Rashid's job.
Your job is to challenge whether the hypothesis is even asking the right question.
Bring in examples from outside this field if relevant.

Research topic context: {self.research_topic}
        """

        devils_response = self.agents["devil"].act(
            day=day, phase="devils_advocate",
            kb_summary=kb_summary,
            context=f"HYPOTHESIS TO CHALLENGE:\n{hypothesis_response}",
            task=devils_task
        )
        self.kb.log_transcript(day, "devils_advocate", self.agents["devil"].name, devils_response)
        self._print_agent_output("Devil's Advocate", devils_response)

        # Store challenges as contradictions in the KB
        self.kb.add_contradiction(
            day=day,
            raised_by=self.agents["critic"].name,
            against="researcher_findings",
            content=critique_response[:500]
        )
        self.kb.add_contradiction(
            day=day,
            raised_by=self.agents["devil"].name,
            against="lead_hypothesis",
            content=devils_response[:500]
        )

        # ---> NEW VERDICT TALLY LOGIC <---
        
        # 1. Search the Critic's output for their exact VERDICT word
        verdict_match = re.search(r'VERDICT:\s*\[?(accept|revise|reject)\]?', critique_response, re.IGNORECASE)
        critic_verdict = verdict_match.group(1).lower() if verdict_match else "revise"
        
        # 2. Tally the votes (Devil's Advocate is always an automatic 'against')
        votes_for = 0
        votes_against = 1  
        
        if critic_verdict == "accept":
            votes_for += 1
            status = "supported"
        elif critic_verdict == "reject":
            votes_against += 1
            status = "rejected"
        else:
            status = "open"
            
        # 3. Update the database using the ID we captured in Phase 1
        if hasattr(self, 'current_hypothesis_id'):
            self.kb.update_hypothesis(
                hypothesis_id=self.current_hypothesis_id,
                status=status,
                votes_for=votes_for,
                votes_against=votes_against
            )

        return critique_response, devils_response

    def _phase_synthesis(self, day: int, kb_summary: str,
                         hypothesis_response: str, research_response: str,
                         critique_response: str, devils_response: str):
        """
        Archivist synthesizes everything. Orchestrator commits to KB.

        The archivist sees EVERYTHING — all four outputs.
        They're the only agent with full information.
        Their recommendation decides what enters the canonical KB.
        """
        full_days_context = f"""
=== LEAD SCIENTIST (Dr. Osei) ===
{hypothesis_response}

=== RESEARCHER (Dr. Watanabe) ===
{research_response}

=== PEER CRITIC (Dr. Al-Rashid) ===
{critique_response}

=== DEVIL'S ADVOCATE (Prof. Holt) ===
{devils_response}
        """

        synthesis_task = f"""
You have the complete record of Day {day}'s work.
Write your objective summary and make your KB recommendations.
Be conservative: only recommend findings for the KB if they survived meaningful criticism.
A finding with a fatal flaw should NOT be recommended, even if it's interesting.
        """

        synthesis_response = self.agents["archivist"].act(
            day=day, phase="synthesis",
            kb_summary=kb_summary,
            context=full_days_context,
            task=synthesis_task
        )

        self.kb.log_transcript(day, "synthesis", self.agents["archivist"].name, synthesis_response)
        self._print_agent_output("Archivist", synthesis_response)

        # Parse archivist's recommendations and commit to KB
        self._commit_to_kb(day, synthesis_response, research_response)

    # ─────────────────────────────────────────────
    # KB COMMIT LOGIC
    # ─────────────────────────────────────────────

    def _commit_to_kb(self, day: int, synthesis_response: str, research_response: str):
        """
        Parse the archivist's synthesis and commit approved findings to the KB.

        This uses a second LLM call to extract structured data from the
        archivist's freeform text. The archivist writes naturally;
        this parser extracts the machine-readable decision.
        """

        parse_prompt = """You are a data extraction system. Extract structured data from research summaries."""

        parse_request = f"""
Extract the key information from this research archivist's synthesis report.

SYNTHESIS REPORT:
{synthesis_response}

RESEARCHER'S FINDINGS (for reference):
{research_response[:500]}

Return a JSON object with this exact structure:
{{
  "recommended_findings": [
    {{
      "title": "short title for the finding",
      "content": "the finding itself in 1-2 sentences",
      "confidence": 0.0 to 10.0,
      "approved": true or false
    }}
  ],
  "open_questions": ["question 1", "question 2"],
  "day_verdict": "productive / mixed / stalled"
}}

Only include findings the archivist explicitly recommended for the KB.
If nothing was approved, return an empty list.
        """

        parsed = call_llm_json(parse_prompt, parse_request)

        if not parsed:
            print("    [Archivist parsing failed — nothing committed to KB]")
            return

        # Commit approved findings
        committed = 0
        for finding in parsed.get("recommended_findings", []):
            if finding.get("approved"):
                self.kb.add_finding(
                    day=day,
                    author=self.agents["researcher"].name,
                    title=finding.get("title", "Untitled finding"),
                    content=finding.get("content", ""),
                    confidence=float(finding.get("confidence", 5.0)),
                    domain=self.research_topic[:50]
                )
                committed += 1
                print(f"    ✓ KB ← \"{finding.get('title', 'finding')}\" (conf={finding.get('confidence', '?')})")

        verdict = parsed.get("day_verdict", "unknown")
        questions = parsed.get("open_questions", [])

        if committed == 0:
            print(f"    ○ Nothing committed to KB today (verdict: {verdict})")

        if questions:
            print(f"    Open questions for tomorrow: {len(questions)}")
            for q in questions[:2]:
                print(f"      → {q[:80]}")

    # ─────────────────────────────────────────────
    # DISPLAY HELPERS
    # ─────────────────────────────────────────────

    def _print_agent_output(self, label: str, response: str):
        """Print agent output with clear formatting."""
        print(f"\n  ┌─ {label} {'─'*(40-len(label))}")
        # Print first 600 chars to keep terminal manageable
        preview = response[:600]
        for line in preview.split("\n"):
            print(f"  │ {line}")
        if len(response) > 600:
            print(f"  │ ... [{len(response)-600} more chars]")
        print(f"  └{'─'*42}")

    def _print_final_summary(self):
        """Print a summary of what the simulation produced."""
        findings = self.kb.get_recent_findings(20)
        contradictions = self.kb.get_all_contradictions()

        print(f"\nFindings committed to KB: {len(findings)}")
        for f in findings:
            print(f"  Day {f['day']} | {f['author']} | conf={f['confidence']:.1f} | {f['title']}")

        print(f"\nContradictions raised: {len(contradictions)}")
        unresolved = sum(1 for c in contradictions if not c['resolved'])
        print(f"  Unresolved: {unresolved}")

        print(f"\nFull transcript saved to: {self.data_dir}/knowledge_base.db")
        print("Open with: sqlite3 data/knowledge_base.db")
        print("  .mode column")
        print("  SELECT day, agent, substr(content,1,100) FROM transcript;")
