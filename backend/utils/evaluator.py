"""
evaluator.py — The analysis layer.

This is what separates a project from a toy.
You ran the simulation. Now what did you LEARN from it?

Three evaluations:
  1. BeliefTracker   — how did agent confidence scores change over days?
  2. CitationGraph   — which agents cited whose work? (social network of ideas)
  3. HypothesisAudit — which hypotheses survived, which died, and why?

These are the outputs you present in an interview or writeup.
"""

import json
import re
import sqlite3
import os
from collections import defaultdict


class Evaluator:
    """
    Post-simulation analysis. Call after orchestrator.run() completes.

    Usage:
        eval = Evaluator(data_dir="data")
        eval.run_all()
    """

    def __init__(self, data_dir: str = "data"):
        db_path = os.path.join(data_dir, "knowledge_base.db")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"No simulation data found at {db_path}. Run the simulation first.")
        self.conn = sqlite3.connect(db_path)

    def run_all(self):
        """Run all evaluations and print results."""
        print("\n" + "="*60)
        print("SIMULATION ANALYSIS")
        print("="*60)

        self.belief_drift_report()
        self.citation_graph()
        self.hypothesis_audit()
        self.debate_intensity_report()

    # ─────────────────────────────────────────────
    # 1. BELIEF DRIFT
    # How did confidence scores change across the simulation?
    # High drift = the group is learning and updating
    # Low drift = agents are entrenched, not responding to evidence
    # ─────────────────────────────────────────────

    def belief_drift_report(self):
        """
        Extract confidence scores from each agent's responses over time.
        Looks for patterns like "CONFIDENCE: 7" in transcript text.
        """
        print("\n--- BELIEF DRIFT REPORT ---")

        rows = self.conn.execute(
            "SELECT day, agent, content FROM transcript ORDER BY day, id"
        ).fetchall()

        # agent_name -> {day -> [confidence_scores]}
        confidence_by_agent = defaultdict(lambda: defaultdict(list))

        for day, agent, content in rows:
            # Extract confidence scores from agent output
            # Agents are prompted to output "CONFIDENCE: X"
            matches = re.findall(r'CONFIDENCE[:\s]+(\d+(?:\.\d+)?)', content, re.IGNORECASE)
            for m in matches:
                confidence_by_agent[agent][day].append(float(m))

        if not confidence_by_agent:
            print("No confidence scores found in transcript.")
            return

        for agent, day_scores in sorted(confidence_by_agent.items()):
            scores_by_day = []
            for day in sorted(day_scores.keys()):
                avg = sum(day_scores[day]) / len(day_scores[day])
                scores_by_day.append((day, avg))

            if len(scores_by_day) < 2:
                continue

            # Calculate drift = change from first to last day
            first_score = scores_by_day[0][1]
            last_score = scores_by_day[-1][1]
            drift = last_score - first_score
            direction = "↑" if drift > 0 else "↓" if drift < 0 else "→"

            score_str = " → ".join(f"Day{d}:{s:.1f}" for d, s in scores_by_day)
            print(f"  {agent:<25} {score_str}  ({direction} drift: {drift:+.1f})")

    # ─────────────────────────────────────────────
    # 2. CITATION GRAPH
    # Who cites whom? Reveals the social structure of knowledge.
    # An agent that gets cited a lot = epistemic authority
    # An agent that never gets cited = marginalized voice
    # ─────────────────────────────────────────────

    def citation_graph(self):
        """
        Detect when agents reference each other by name in their outputs.
        This is a proxy for intellectual influence.
        """
        print("\n--- CITATION GRAPH ---")

        rows = self.conn.execute(
            "SELECT agent, content FROM transcript ORDER BY day, id"
        ).fetchall()

        # Map of agent names (lowercase) for detection
        agent_names = {
            "osei": "Dr. Osei (Lead Scientist)",
            "watanabe": "Dr. Watanabe (Researcher)",
            "al-rashid": "Dr. Al-Rashid (Critic)",
            "holt": "Prof. Holt (Devil's Advocate)",
            "nair": "Dr. Nair (Archivist)",
        }

        # citations[citer][cited] = count
        citations = defaultdict(lambda: defaultdict(int))

        for agent, content in rows:
            content_lower = content.lower()
            for name_key, full_name in agent_names.items():
                if name_key in content_lower and name_key not in agent.lower():
                    citations[agent][full_name] += content_lower.count(name_key)

        if not citations:
            print("  No cross-citations detected.")
            return

        for citer, cited_dict in sorted(citations.items()):
            for cited, count in sorted(cited_dict.items(), key=lambda x: -x[1]):
                print(f"  {citer:<30} → {cited} ({count}x)")

    # ─────────────────────────────────────────────
    # 3. HYPOTHESIS AUDIT
    # Which hypotheses survived? Which were killed by critique?
    # The "graveyard" of dead hypotheses is scientifically valuable.
    # ─────────────────────────────────────────────

    def hypothesis_audit(self):
        """Audit the fate of all hypotheses proposed during the simulation."""
        print("\n--- HYPOTHESIS AUDIT ---")

        hypotheses = self.conn.execute(
            "SELECT id, day, content, status, votes_for, votes_against FROM hypotheses ORDER BY day"
        ).fetchall()

        if not hypotheses:
            print("  No hypotheses in registry.")
            return

        survived = 0
        rejected = 0
        open_h = 0

        for h_id, day, content, status, vf, va in hypotheses:
            icon = {"supported": "✓", "rejected": "✗", "open": "?"}.get(status, "?")
            print(f"  [{icon}] Day {day}: {content[:80]}...")
            print(f"        Status: {status} | For: {vf} | Against: {va}")

            if status == "supported":
                survived += 1
            elif status == "rejected":
                rejected += 1
            else:
                open_h += 1

        print(f"\n  Survived: {survived} | Rejected: {rejected} | Open: {open_h}")
        if survived + rejected > 0:
            rate = survived / (survived + rejected) * 100
            print(f"  Hypothesis survival rate: {rate:.0f}%")

    # ─────────────────────────────────────────────
    # 4. DEBATE INTENSITY
    # How contested was each day? High = productive tension.
    # Low = either boring consensus or everyone gave up.
    # ─────────────────────────────────────────────

    def debate_intensity_report(self):
        """
        Measure how much contradiction and challenge occurred each day.
        Proxy: count words like "disagree", "flaw", "however", "challenge", "wrong"
        in critique and devil's advocate outputs.
        """
        print("\n--- DEBATE INTENSITY ---")

        challenge_words = [
            "disagree", "flaw", "however", "challenge", "wrong", "incorrect",
            "fails to", "overlooks", "ignores", "contradicts", "insufficient",
            "problematic", "invalid", "reject", "fatal"
        ]

        rows = self.conn.execute(
            "SELECT day, phase, content FROM transcript WHERE phase IN ('critique', 'devils_advocate') ORDER BY day"
        ).fetchall()

        day_intensity = defaultdict(int)
        day_word_count = defaultdict(int)

        for day, phase, content in rows:
            content_lower = content.lower()
            day_word_count[day] += len(content.split())
            for word in challenge_words:
                day_intensity[day] += content_lower.count(word)

        if not day_intensity:
            print("  No debate data found.")
            return

        # max_intensity = max(day_intensity.values()) if day_intensity else 1
        # Ensure max_intensity is at least 1 to prevent ZeroDivisionError
        max_intensity = max(max(day_intensity.values()), 1) if day_intensity else 1

        for day in sorted(day_intensity.keys()):
            intensity = day_intensity[day]
            # Visual bar
            bar_len = int((intensity / max_intensity) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"  Day {day}: [{bar}] {intensity} challenge signals")

        most_intense = max(day_intensity, key=day_intensity.get)
        print(f"\n  Most contested day: Day {most_intense}")
