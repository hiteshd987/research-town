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
from utils.llm import call_llm_json, call_llm


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
        # Stores the previous day's full debate so the lead scientist
        # can read exactly what was challenged and why before proposing
        # the next hypothesis. Empty on Day 1.
        self.previous_debate = ""



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

    def run(self, total_days: int = 3):
        """Run the simulation for N days."""
        print(f"Starting {total_days}-day simulation...\n")

        for day in range(1, total_days + 1):
            print(f"\n{'='*60}")
            print(f"  DAY {day}")
            print(f"{'='*60}")
            # Pass both the current 'day' and the 'days' (total days)
            self._run_day(day, total_days)

        print(f"\n{'='*60}")
        print("SIMULATION COMPLETE")
        print(f"{'='*60}")
        self._print_final_summary()

    # ─────────────────────────────────────────────
    # DAILY LOOP
    # ─────────────────────────────────────────────

    def _run_day(self, day: int, total_days: int):
        """Run one full day of the simulation."""
        self.current_day = day

        # Get the current state of the knowledge base
        # This is what every agent reads at the start of the day
        kb_summary = self.kb.format_kb_summary()

        # ── Phase 1: Hypothesis ──────────────────
        print(f"\n[Phase 1: Hypothesis]")
        hypothesis_response = self._phase_hypothesis(day, total_days, kb_summary)

        # ── Phase 2: Research ────────────────────
        print(f"\n[Phase 2: Research]")
        research_response = self._phase_research(day, total_days, kb_summary, hypothesis_response)

        # ── Phase 3: Debate ──────────────────────
        print(f"\n[Phase 3: Debate]")
        # Capture the status here
        critique_response, devils_response, day_status = self._phase_debate(
            day, total_days, kb_summary, hypothesis_response, research_response
        )

        # ── Phase 4: Synthesis ───────────────────
        print(f"\n[Phase 4: Synthesis]")
        # Pass the status in here
        self._phase_synthesis(
            day, total_days, kb_summary,
            hypothesis_response, research_response,
            critique_response, devils_response, day_status 
        )

        # Update previous debate so the Lead Scientist knows the outcome tomorrow
        self.previous_debate = (
            f"=== DAY {day} DEBATE RECORD ===\n"
            f"OFFICIAL STATUS: {day_status.upper()}\n\n"
            f"HYPOTHESIS PROPOSED:\n{hypothesis_response}\n\n"
            f"RESEARCH FINDINGS:\n{research_response}\n\n"
            f"PEER CRITIC OBJECTIONS:\n{critique_response}\n\n"
            f"DEVIL'S ADVOCATE CHALLENGE:\n{devils_response}"
        )

    # ─────────────────────────────────────────────
    # PHASES
    # ─────────────────────────────────────────────

    def _phase_hypothesis(self, day: int, total_days: int,kb_summary: str) -> str:
        """
        Lead scientist proposes today's hypothesis and assigns tasks.

        Context: Just the KB + the research topic.
        No other agents have acted yet — clean slate each day.
        """
        
        urgency_note = ""
        if day == total_days:
            urgency_note = "CRITICAL: This is the FINAL DAY of the simulation. You must prioritize finalizing a safe, consensus-driven hypothesis that the Red Team will not reject easily. Do not propose wild new theories today."

        revision_instruction = ""
        if self.previous_debate:
            revision_instruction = (
                "CRITICAL — READ THIS FIRST:\n"
                "Yesterday's debate is in your context above. You MUST:\n"
                "  1. Identify the strongest objection the critic raised\n"
                "  2. Identify the core assumption the devil's advocate attacked\n"
                "  3. Your new hypothesis MUST directly address both.\n"
                "  Do not repeat yesterday's hypothesis. Do not ignore the objections.\n"
                "  The agents will check if you actually responded to their feedback."
            )

        task = f"""
We are researching: {self.research_topic}

This is Day {day} out of {total_days} total days.
{urgency_note}
{revision_instruction}

Your job today:
1. Propose ONE clear, testable hypothesis — refined from yesterday's objections if Day 2+
2. Assign specific tasks to Dr. Watanabe (researcher), Dr. Al-Rashid (critic), and Prof. Holt (devil's advocate)
3. Be specific — vague tasks produce vague results

Remember: bold hypotheses are better than safe ones.
        """

        # Build context from previous day's debate.
        # On Day 1 this is empty — no prior debate exists.
        # From Day 2 onwards the lead scientist reads exactly what
        # the critic and devil's advocate objected to yesterday,
        # so the new hypothesis directly addresses those flaws.
        prior_context = self.previous_debate if self.previous_debate else ""

        # ---> NEW: ORCHESTRATOR DEBUG LOGGING <---
        print(f"\n[DEBUG - ORCHESTRATOR] Sending context to {self.agents['lead'].name} for Day {day}:")
        if prior_context:
            print(f"  -> Prior Context: YES ({len(prior_context)} chars from Day {day-1} debate)")
            # Print a tiny preview so you can verify it's the right text
            print(f"  -> Preview: {prior_context[:80].replace(chr(10), ' ')}...") 
        else:
            print("  -> Prior Context: NONE (Clean slate for Day 1)")
        # -----------------------------------------

        response = self.agents["lead"].act(
            day=day, phase="hypothesis",
            kb_summary=kb_summary,
            context=prior_context,
            task=task
        )

        self.kb.log_transcript(day, "hypothesis", self.agents["lead"].name, response)
        self._print_agent_output("Lead Scientist", response)
        
        # ---> UPDATE THIS LINE: Capture the ID <---
        self.current_hypothesis_id = self.kb.add_hypothesis(day=day, content=response[:200])

        return response

    def _phase_research(self, day: int, total_days: int, kb_summary: str, hypothesis_response: str) -> str:
        """
        Researcher investigates the assigned task.

        Context: Includes the lead scientist's hypothesis and task assignment.
        The researcher must build on the KB and report honestly.
        """
        
        urgency_note = ""
        if day == total_days:
            urgency_note = "CRITICAL: This is the FINAL DAY. You must prioritize practical, conclusive findings over exploring new tangents. We need a definitive answer today."

        task = f"""
Review Dr. Osei's hypothesis and your assigned task above.
This is Day {day} out of {total_days} total days.
{urgency_note}
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

    def _phase_debate(self, day: int, total_days: int, kb_summary: str,
                      hypothesis_response: str, research_response: str) -> tuple[str, str]:
        """
        Critic and devil's advocate challenge the work.

        KEY ASYMMETRY:
          - Critic sees: researcher's findings (they critique the METHOD)
          - Devil's advocate sees: lead scientist's hypothesis (they attack the PREMISE)
        """

        # Calculate if it is the final day to force consensus
        urgency_note = "" 
        if day == total_days:
            urgency_note = "CRITICAL: This is the FINAL DAY. You must not demand major revisions. If the core idea is sound, you MUST support it so we have a finalized finding. Only reject if the flaw is truly fatal."

        # ─── CRITIC EXAMINES RESEARCH ───
        critic_task = f"""
Review Dr. Watanabe's findings report above with your sharpest eye.
This is Day {day} out of {total_days} total days.
{urgency_note}

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


        # ─── DEVIL'S ADVOCATE ATTACKS HYPOTHESIS ───
        devils_task = f"""
Attack Dr. Osei's hypothesis at its foundations.
This is Day {day} out of {total_days} total days.
{urgency_note}

Don't critique the methodology that's Dr. Al-Rashid's job.
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


        # ─── STORE CONTRADICTIONS ───
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


        # ─── DUAL-AGENT VERDICT TALLY LOGIC ───
        #
        # HOW VOTING WORKS:
        #   Each day the lead scientist proposes a NEW/refined hypothesis.
        #   The votes on Day 1 are about H1. Day 2 votes are about H2. Etc.
        #   Accumulating votes across different hypotheses makes no sense —
        #   a "reject" on the rough Day 1 idea should not count against the
        #   polished Day 3 version.
        #
        #   Instead:
        #     - Non-final days: votes are recorded but status stays "open".
        #       The votes INFORM the lead scientist's next revision — that
        #       is their only purpose on early days.
        #     - Final day: TODAY'S votes (and only today's) decide the outcome.
        #       This is the vote that counts.

        # ── Step 1: Parse today's votes ───────────────────────────────────────
        # BINARY ONLY: agents vote SUPPORT or REJECT.
        # No abstain state exists. If the regex finds nothing it is a parse
        # failure — the LLM ignored the instruction or used odd formatting.
        # We fix it with one cheap follow-up call, not by treating it as a vote.
        _VERDICT_RE = re.compile(
            r'VERDICT[:\s]+\[?\s*(accept|support|supported|reject)\s*\]?',
            re.IGNORECASE
        )

        def _extract_verdict(response, agent_name):
            match = _VERDICT_RE.search(response)
            if match:
                return match.group(1).lower()
            # Parse failed — ask once more, cheaply
            print(f"  [PARSE FAIL] {agent_name} — no VERDICT found, requesting clarification")
            clarification = call_llm(
                system_prompt=(
                    "You are " + agent_name + ". You just reviewed a research hypothesis "
                    "but forgot to include your final verdict."
                ),
                user_message=(
                    "Your previous response was:\n" + response[-600:] + "\n\n"
                    "State your final verdict in exactly this format:\n"
                    "VERDICT: SUPPORT\nor\nVERDICT: REJECT\n"
                    "One line only. No other text."
                )
            )
            retry_match = _VERDICT_RE.search(clarification)
            if retry_match:
                v = retry_match.group(1).lower()
                print(f"  [PARSE RETRY] {agent_name} clarified: {v.upper()}")
                return v
            # Both attempts failed — default to reject.
            # A hypothesis should earn its passing grade, not receive it by default.
            print(f"  [PARSE ERROR] {agent_name} could not be parsed after retry — defaulting to REJECT")
            return "reject"

        critic_verdict = _extract_verdict(critique_response, self.agents["critic"].name)
        devil_verdict  = _extract_verdict(devils_response,   self.agents["devil"].name)

        # Show raw tail for debugging — lets you see exactly what the agent wrote
        print(f"\n  [RAW CRITIC TAIL]  {critique_response.strip()[-120:]!r}")
        print(f"  [RAW DEVIL TAIL]   {devils_response.strip()[-120:]!r}")
        print(f"  [VOTE] Day {day}/{total_days} | "
              f"Critic: {critic_verdict.upper()} | Devil: {devil_verdict.upper()}")

        # ── Step 2: Tally binary votes ────────────────────────────────────────
        all_verdicts  = [v for v in [critic_verdict, devil_verdict] if v is not None]
        votes_for     = sum(1 for v in all_verdicts if v in ("accept", "support", "supported"))
        votes_against = sum(1 for v in all_verdicts if v == "reject")

        print(f"  [TALLY] For: {votes_for} | Against: {votes_against} | "
              f"Abstained: {2 - len(all_verdicts)}")

       # ── Step 3: Decide status & Conditional Tie-Breaker ──────────────────
        if votes_for > votes_against:
            status = "supported"
        elif votes_against > votes_for:
            status = "rejected"
        else:
            # ---> EXACT TIE (1-1) - TRIGGER THE ARCHIVIST <---
            print("\n  [TIE-BREAKER] The panel is deadlocked 1-1! Calling Dr. Nair (Archivist)...")
            
            tiebreaker_task = f"""
The peer review panel is completely deadlocked on Dr. Osei's hypothesis. 
The Critic voted {critic_verdict.upper()} and the Devil's Advocate voted {devil_verdict.upper()}.

As the neutral Archivist, you must break this tie. You do not vote on the science itself, but on the *logical strength of the arguments*. Read the debate provided in the context. Whose argument was more rigorous, evidence-backed, and logically sound?

Cast the deciding vote by ending your response with exactly:
VERDICT: SUPPORT (if the Critic/Lead's defense was stronger)
or
VERDICT: REJECT (if the Devil's Advocate's attack was stronger)
            """
            
            tiebreaker_response = self.agents["archivist"].act(
                day=day, phase="tiebreaker",
                kb_summary=kb_summary,
                context=f"--- CRITIC'S REVIEW ---\n{critique_response}\n\n--- DEVIL'S ADVOCATE CHALLENGE ---\n{devils_response}",
                task=tiebreaker_task
            )
            
            # Use the existing regex parser to read her vote
            tb_verdict = _extract_verdict(tiebreaker_response, self.agents["archivist"].name)
            
            print(f"  [RAW ARCHIVIST TAIL] {tiebreaker_response.strip()[-100:]!r}")
            print(f"  [TIE-BREAKER VOTE] Archivist decided: {tb_verdict.upper()}")
            
            # Apply the deciding vote
            if tb_verdict in ["accept", "support", "supported"]:
                votes_for += 1
                status = "supported"
            else:
                votes_against += 1
                status = "rejected"

        # ── Step 4: Write to database ─────────────────────────────────────────
        if hasattr(self, 'current_hypothesis_id'):
            self.kb.update_hypothesis(
                hypothesis_id=self.current_hypothesis_id,
                status=status,
                votes_for=votes_for,
                votes_against=votes_against
            )

        # RETURN THE STATUS TOO
        return critique_response, devils_response, status

    def _phase_synthesis(self, day: int, total_days: int,kb_summary: str,
                         hypothesis_response: str, research_response: str,
                         critique_response: str, devils_response: str, day_status: str):
        """
        Archivist synthesizes everything. Orchestrator commits to KB.

        The archivist sees EVERYTHING — all four outputs.
        They're the only agent with full information.
        Their recommendation decides what enters the canonical KB.
        """
        urgency_note = ""
        if day == total_days:
            urgency_note = "CRITICAL: This is the FINAL DAY. Your synthesis today will serve as the ultimate conclusion for the entire simulation. Be decisive."

        full_days_context = f"""
        === LEAD SCIENTIST (Dr. Osei) ===
        {hypothesis_response}

        === RESEARCHER (Dr. Watanabe) ===
        {research_response}

        === PEER CRITIC (Dr. Al-Rashid) ===
        {critique_response}

        === DEVIL'S ADVOCATE (Prof. Holt) ===
        {devils_response}

        === OFFICIAL VOTING OUTCOME ===
        The final official status for today's hypothesis is: {day_status.upper()}
                """

        synthesis_task = f"""
You have the complete record of Day {day}'s work.
This is Day {day} out of {total_days} total days.
{urgency_note}
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

        # Pass the status to the KB committer
        self._commit_to_kb(day, synthesis_response, research_response, day_status)

    # ─────────────────────────────────────────────
    # KB COMMIT LOGIC
    # ─────────────────────────────────────────────

    def _commit_to_kb(self, day: int, synthesis_response: str, research_response: str, day_status: str):
        """
        Commit validated findings to the KB.

        Only runs on SUPPORTED days. On REJECTED/OPEN days we log and exit
        immediately — no LLM call wasted, nothing false committed.

        WHY THE OLD VERSION FAILED:
          It passed day_status as a hint inside the prompt, but the LLM parser
          could still return approved:false or an empty list even on SUPPORTED
          days — especially when the synthesis text was dominated by objections
          from rejected earlier days. We now gate the entire commit on
          day_status BEFORE calling the LLM.
        """

        # ── Gate: only commit on supported days ──────────────────────────────
        if day_status.upper() != "SUPPORTED":
            print(f"    ○ Day {day} status is {day_status.upper()} — nothing committed to KB")
            return

        # ── Extract findings from the supported day ───────────────────────────
        # We ask the parser to extract findings from BOTH the archivist synthesis
        # AND the researcher report directly. This prevents the case where a
        # synthesis full of debate noise causes the parser to return nothing.
        parse_prompt = "You are a data extraction system. Extract structured findings from research reports."

        parse_request = f"""
Today is a SUPPORTED day — the hypothesis survived peer review.
Your job is to extract the validated scientific findings so they can be stored.

ARCHIVIST SYNTHESIS (what the archivist said was established today):
{synthesis_response}

RESEARCHER FINDINGS (the empirical work done today):
{research_response[:800]}

INSTRUCTIONS:
- Extract 1-3 concrete, specific findings that are supported by the researcher's work.
- Each finding must be a factual claim, not a process description.
- BAD:  "The team investigated fine-tuning approaches"
- GOOD: "LoRA fine-tuning with rank 16 preserved 94% of baseline MMLU performance"
- Set approved: true for all findings you extract (this is a supported day).
- Confidence should reflect how strongly the evidence supports the claim (1-10).

Return ONLY this JSON, no other text:
{{
  "recommended_findings": [
    {{
      "title": "short 5-8 word title",
      "content": "the finding in 1-2 sentences",
      "confidence": 7.0,
      "approved": true
    }}
  ],
  "open_questions": ["question 1", "question 2"],
  "day_verdict": "productive"
}}
"""

        parsed = call_llm_json(parse_prompt, parse_request)

        # ── Fallback: if JSON parse failed, extract directly from researcher ──
        if not parsed or not parsed.get("recommended_findings"):
            print("    [Parser returned empty — using researcher findings directly]")
            # Pull the FINDINGS section from the researcher response as a fallback
            findings_text = ""
            for line in research_response.split("\n"):
                if line.strip().startswith("FINDINGS:"):
                    findings_text = line.replace("FINDINGS:", "").strip()
                    break
            if not findings_text:
                findings_text = research_response[:300]

            self.kb.add_finding(
                day=day,
                author=self.agents["researcher"].name,
                title=f"Day {day} validated finding",
                content=findings_text[:400],
                confidence=6.0,
                domain=self.research_topic[:50]
            )
            print(f"    ✓ KB ← fallback finding from researcher (Day {day})")
            return

        # ── Commit all extracted findings ─────────────────────────────────────
        committed = 0
        for finding in parsed.get("recommended_findings", []):
            if not finding.get("title") or not finding.get("content"):
                continue
            self.kb.add_finding(
                day=day,
                author=self.agents["researcher"].name,
                title=finding.get("title", "Untitled finding"),
                content=finding.get("content", ""),
                confidence=float(finding.get("confidence", 6.0)),
                domain=self.research_topic[:50]
            )
            committed += 1
            print(f"    ✓ KB ← \"{finding.get('title', 'finding')}\" (conf={finding.get('confidence', '?')})")

        questions = parsed.get("open_questions", [])
        if committed == 0:
            print(f"    ○ Parser returned findings but none had content — check synthesis output")
        if questions:
            print(f"    Open questions for tomorrow: {len(questions)}")
            for q in questions[:2]:
                print(f"      → {q[:80]}")

    # ─────────────────────────────────────────────
    # DISPLAY HELPERS
    # ─────────────────────────────────────────────

    def _print_agent_output(self, label: str, response: str):
        """
        Parse and print agent output field by field.

        Each agent has a known output format (HYPOTHESIS:, FINDINGS:, etc.).
        Instead of dumping raw text, we extract each field and print it on
        its own labelled line — much easier to read in the terminal.

        Fields we recognise across all agents:
          Lead:       HYPOTHESIS, REASONING, TASKS, CONFIDENCE
          Researcher: TASK_ADDRESSED, METHOD, FINDINGS, LIMITATIONS, CONFIDENCE, CITES
          Critic:     FINDING_REVIEWED, MAIN_OBJECTION, FLAW_TYPE, SEVERITY,
                      WHAT_WOULD_FIX_IT, VERDICT
          Devil:      HYPOTHESIS_CHALLENGED, CORE_ASSUMPTION_ATTACKED,
                      COUNTERARGUMENT, ALTERNATIVE_HYPOTHESIS, SEVERITY,
                      WHAT_WOULD_FIX_IT, VERDICT
          Archivist:  DAY_SUMMARY, FINDINGS_PROPOSED, OBJECTIONS_RAISED,
                      CONTRADICTIONS_WITH_KB, RECOMMENDED_FOR_KB, OPEN_QUESTIONS
        """
        # Fields to extract. Value is (max_chars, show_full_or_truncate)
        # True = show fully (short fields), False = truncate to max_chars
        FIELDS = [
            # Lead Scientist
            ("HYPOTHESIS",              160, True),
            ("REASONING",               140, False),
            ("TASKS",                   200, False),
            ("CONFIDENCE",               10, True),
            # Researcher
            ("TASK_ADDRESSED",          120, False),
            ("METHOD",                  120, False),
            ("FINDINGS",                180, False),
            ("LIMITATIONS",             120, False),
            ("CITES",                   100, False),
            # Critic + Devil
            ("FINDING_REVIEWED",        120, False),
            ("MAIN_OBJECTION",          160, False),
            ("FLAW_TYPE",                30, True),
            ("SEVERITY",                 20, True),
            ("WHAT_WOULD_FIX_IT",       140, False),
            ("CORE_ASSUMPTION_ATTACKED",140, False),
            ("COUNTERARGUMENT",         160, False),
            ("ALTERNATIVE_HYPOTHESIS",  140, False),
            ("QUESTION_FOR_GROUP",      120, False),
            ("VERDICT",                  20, True),
            # Archivist
            ("DAY_SUMMARY",             200, False),
            ("FINDINGS_PROPOSED",       200, False),
            ("OBJECTIONS_RAISED",       200, False),
            ("CONTRADICTIONS_WITH_KB",  160, False),
            ("RECOMMENDED_FOR_KB",      200, False),
            ("OPEN_QUESTIONS",          200, False),
        ]

        # Parse the response into a dict of field -> value
        parsed = {}
        current_key = None
        current_lines = []

        for line in response.split("\n"):
            stripped = line.strip()
            matched = False
            for field_name, _, _ in FIELDS:
                if stripped.upper().startswith(field_name + ":"):
                    if current_key:
                        parsed[current_key] = " ".join(current_lines).strip()
                    current_key = field_name
                    current_lines = [stripped[len(field_name)+1:].strip()]
                    matched = True
                    break
            if not matched and current_key and stripped:
                current_lines.append(stripped)

        if current_key:
            parsed[current_key] = " ".join(current_lines).strip()

        # Print header
        bar = "─" * max(1, 42 - len(label))
        print(f"\n  ┌─ {label} {bar}")

        if parsed:
            # Print only fields that have content, in definition order
            for field_name, max_chars, show_full in FIELDS:
                val = parsed.get(field_name, "").strip()
                if not val:
                    continue
                # Truncate long values unless show_full
                display = val if show_full else (val[:max_chars] + ("..." if len(val) > max_chars else ""))
                # Multi-line values: indent continuation lines
                lines = display.split("\n")
                label_str = f"{field_name}:"
                print(f"  │  {label_str:<26} {lines[0]}")
                for extra in lines[1:]:
                    if extra.strip():
                        print(f"  │  {'':<26} {extra.strip()}")
        else:
            # Fallback: no fields matched — print raw (truncated)
            for line in response[:400].split("\n"):
                print(f"  │  {line}")
            if len(response) > 400:
                print(f"  │  ... [{len(response)-400} more chars]")

        print(f"  └{'─'*44}")

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