"""SuggestionGenerator — produces concrete resume revision suggestions for each gap."""

import logging
from typing import List

from utils.json_utils import parse_json_response

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 2000

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert resume writer and career coach. You will receive a candidate's \
resume profile and a ranked list of skill/experience gaps identified for a specific role.

Your job is to generate concrete, specific resume revision suggestions that close \
each gap — written as polished resume bullet points or skill additions.

Return ONLY a JSON object in this exact format — no markdown, no commentary:
{
  "suggestions": [
    {
      "gap": "The exact gap being addressed",
      "suggested_revision": "Ready-to-paste resume bullet point or skill addition",
      "reasoning": "One sentence: why this revision closes the gap",
      "section": "experience | skills | projects | summary",
      "priority": <integer 1-10>
    }
  ]
}

Priority guide (1-10):
- 9-10 : critical gap, must address before applying
- 7-8  : high impact, strongly recommended
- 5-6  : moderate impact, worth adding if space allows
- 1-4  : low impact, optional polish

Rules for suggested_revision:
- Write in first-person-removed style (no "I"), past tense for past roles
- Be SPECIFIC: name the exact technology / methodology from the gap
- Add quantified impact wherever plausible: percentages, scale, team size
- For skills gaps → write: "Add to Skills section: Python (advanced), FastAPI, ..."
- For experience gaps → write a full bullet point using the STAR/XYZ pattern
- For keyword gaps → weave the keyword naturally into an existing bullet point
- Never fabricate facts — frame suggestions as templates the candidate fills in
- Each suggestion must directly name the skill or keyword from the gap"""


def _build_user_message(resume, gaps: List) -> str:
    """Compose the full prompt with resume context and ranked gaps."""

    # ── Resume snapshot ───────────────────────────────────────────────────────
    skills_str = ", ".join(resume.flat_skills()) or "(none listed)"
    certs_str = ", ".join(resume.certifications) or "(none)"

    experience_lines = []
    for exp in resume.experience:
        experience_lines.append(
            f"  [{exp.start_date} – {exp.end_date}] {exp.role} @ {exp.company}"
        )
        for bullet in exp.bullets[:4]:     # cap to keep within token budget
            experience_lines.append(f"    • {bullet}")
    experience_str = "\n".join(experience_lines) or "  (none)"

    projects_str = "\n".join(
        f"  - {p.title} ({', '.join(p.tech_stack)}): {p.description}"
        for p in resume.projects
    ) or "  (none)"

    summary_str = resume.summary or "(no summary)"

    # ── Gaps list (already sorted by impact_on_fit descending) ───────────────
    gaps_lines = []
    for i, gap in enumerate(gaps, 1):
        gaps_lines.append(
            f"  {i}. [{gap.severity.upper()}] {gap.skill}  "
            f"(type={gap.type}, impact={gap.impact_on_fit:.0f}/100)\n"
            f"     Reason: {gap.reason}"
        )
    gaps_str = "\n".join(gaps_lines) or "  (no gaps identified)"

    return f"""\
## CANDIDATE RESUME SNAPSHOT

Summary: {summary_str}
Skills: {skills_str}
Certifications: {certs_str}

Work Experience:
{experience_str}

Projects:
{projects_str}

---
## IDENTIFIED GAPS (sorted most critical first)

{gaps_str}

---
Generate one targeted suggestion per gap above.
Order suggestions by priority (highest first).
Make every suggested_revision copy-paste ready."""


class SuggestionGenerator:
    """Generates concrete resume revision suggestions for each identified gap.

    Usage:
        suggestions = SuggestionGenerator().generate(resume, gaps)
    """

    def __init__(self, claude_client=None) -> None:
        """Use a provided ClaudeAPIClient or create one from config automatically."""
        if claude_client is None:
            from apis.claude_api import ClaudeAPIClient
            from config import config
            claude_client = ClaudeAPIClient(api_key=config.CLAUDE_API_KEY)
        self._claude = claude_client

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(self, resume, gaps: List) -> List:
        """Generate and return suggestions sorted by priority descending.

        Args:
            resume: Populated Resume instance from ResumeParser.
            gaps:   List[Gap] from GapFinder, ideally sorted by impact_on_fit.

        Returns:
            List[Suggestion] sorted highest-priority first. Empty list on failure.
        """
        if not gaps:
            logger.warning("No gaps provided — nothing to generate suggestions for.")
            return []

        logger.info(
            "Generating suggestions for %d gaps (candidate: %s)",
            len(gaps), resume.name or "unknown",
        )

        raw = self._claude.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_message=_build_user_message(resume, gaps),
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0,
        )

        suggestions = self._parse_suggestions(raw)

        # Sort highest priority first
        suggestions.sort(key=lambda s: s.priority, reverse=True)

        self._log_summary(suggestions)
        return suggestions

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_suggestions(raw: str) -> list:
        """Parse Claude's JSON response into a list of Suggestion instances."""
        from models import Suggestion

        try:
            data = parse_json_response(raw)
        except ValueError as exc:
            logger.error("Failed to parse suggestions JSON: %s", exc)
            return []

        raw_items = data.get("suggestions")
        if not isinstance(raw_items, list):
            logger.error(
                "Expected 'suggestions' list in response, got: %s", type(raw_items)
            )
            return []

        suggestions: list = []
        for item in raw_items:
            if not isinstance(item, dict):
                logger.warning("Skipping non-dict suggestion entry: %s", item)
                continue
            try:
                revision = str(item.get("suggested_revision", "")).strip()
                reason = str(item.get("reasoning", "")).strip()
                priority = int(item.get("priority", 5))
                priority = max(1, min(10, priority))   # clamp to 1-10

                suggestion = Suggestion(
                    gap=str(item.get("gap", "")).strip(),
                    suggested_revision=revision,
                    reasoning=reason,
                    section=str(item.get("section", "experience")).strip().lower(),
                    priority=priority,
                    # backward-compat mirrors
                    suggested=revision,
                    rationale=reason,
                )
                suggestions.append(suggestion)
            except Exception as exc:
                logger.warning("Skipping malformed suggestion %s: %s", item, exc)

        return suggestions

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    @staticmethod
    def _log_summary(suggestions: list) -> None:
        if not suggestions:
            logger.warning("No suggestions were generated.")
            return

        avg_priority = sum(s.priority for s in suggestions) / len(suggestions)

        logger.info(
            "Generated %d suggestions  |  avg priority: %.1f / 10",
            len(suggestions), avg_priority,
        )

        section_counts: dict = {}
        for s in suggestions:
            section_counts[s.section] = section_counts.get(s.section, 0) + 1
        section_str = "  ".join(
            f"{sec}: {cnt}" for sec, cnt in sorted(section_counts.items())
        )
        logger.info("Suggestions by section — %s", section_str)

        for s in suggestions:
            logger.info(
                "  [P%02d] %-28s → %s",
                s.priority, s.gap[:28], s.suggested_revision[:80],
            )
