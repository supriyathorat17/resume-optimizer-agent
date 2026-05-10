"""GapFinder — compares a resume against a job description and returns ranked gaps."""

import logging
from typing import List

from utils.json_utils import parse_json_response

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 1500

# ---------------------------------------------------------------------------
# Severity ordering used for log summaries
# ---------------------------------------------------------------------------
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert technical recruiter performing a skills gap analysis.
You will receive a candidate's resume profile and a job description's requirements.
Your job is to identify every meaningful gap — skills, experience, or qualifications
the role requires that the candidate has not demonstrated.

Return ONLY a JSON object in this exact format — no markdown, no commentary:
{
  "gaps": [
    {
      "skill": "Name of the missing skill or requirement",
      "type": "hard | soft | experience | keyword",
      "severity": "critical | high | medium | low",
      "reason": "One sentence explaining why this gap matters for this specific role",
      "impact_on_fit": <integer 0-100>
    }
  ]
}

Severity guide:
- critical : must-have, candidate will likely be screened out without it
- high     : strongly preferred, significant negative signal if absent
- medium   : moderately important, noticeable but not disqualifying
- low      : nice-to-have, minor gap

impact_on_fit guide (0-100):
- 85-100 : deal-breaker gap
- 65-84  : significant gap, likely to hurt candidacy
- 40-64  : moderate gap, worth addressing
- 0-39   : minor gap, low priority

Rules:
- Only report genuine gaps — do not flag skills the resume already demonstrates.
- Be specific: "Kubernetes" not "container technologies".
- Do NOT invent requirements that aren't in the job description.
- If there are no meaningful gaps, return {"gaps": []}.
- Never include a skill in gaps if the resume shows clear evidence of it."""


def _build_user_message(resume, jd, missing_hard: List[str], missing_soft: List[str]) -> str:
    """Construct the analysis prompt with all relevant context."""
    resume_skills = resume.flat_skills()
    experience_summary = "\n".join(
        f"  - {exp.role} at {exp.company} ({exp.start_date} – {exp.end_date})"
        for exp in resume.experience
    ) or "  (none listed)"

    bullets_summary = "\n".join(
        f"  • {bullet}"
        for exp in resume.experience
        for bullet in exp.bullets[:3]   # cap at 3 per role to stay within token budget
    ) or "  (none)"

    projects_summary = "\n".join(
        f"  - {p.title}: {', '.join(p.tech_stack)}"
        for p in resume.projects
    ) or "  (none listed)"

    pre_filtered = ""
    if missing_hard:
        pre_filtered += f"\nPre-identified missing hard skills: {', '.join(missing_hard)}"
    if missing_soft:
        pre_filtered += f"\nPre-identified missing soft skills: {', '.join(missing_soft)}"

    return f"""\
## RESUME PROFILE

Skills on resume: {', '.join(resume_skills) or '(none listed)'}
Certifications: {', '.join(resume.certifications) or '(none)'}

Work history:
{experience_summary}

Key accomplishments:
{bullets_summary}

Projects:
{projects_summary}

---
## JOB REQUIREMENTS

Role: {jd.title or 'N/A'} at {jd.company or 'N/A'}
Seniority: {jd.seniority_level or 'N/A'}

Required hard skills: {', '.join(jd.hard_skills) or '(none specified)'}
Required soft skills: {', '.join(jd.soft_skills) or '(none specified)'}
Must-have experience: {' | '.join(jd.must_have_experience) or '(none specified)'}
Nice-to-have: {', '.join(jd.nice_to_have) or '(none specified)'}
Key ATS keywords: {', '.join(jd.keywords[:30]) or '(none)'}
{pre_filtered}
---
Identify every gap between the resume profile and the job requirements above."""


class GapFinder:
    """Compares a parsed Resume against a parsed JobDescription using Claude.

    Usage:
        gaps = GapFinder().find_gaps(resume, jd)
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

    def find_gaps(self, resume, jd) -> List:
        """Identify and return gaps sorted by impact_on_fit descending.

        Args:
            resume: A populated Resume instance from ResumeParser.
            jd:     A populated JobDescription instance from JDAnalyzer.

        Returns:
            List[Gap] sorted most-critical-first. Empty list if no gaps found.
        """
        from models import Gap

        resume_skills = resume.flat_skills()

        if not jd.hard_skills and not jd.soft_skills and not jd.must_have_experience:
            logger.warning(
                "JobDescription has no categorised requirements — "
                "gap analysis may be incomplete. Check that JDAnalyzer ran correctly."
            )

        # Quick set-based pre-filter so the prompt can highlight obvious misses
        missing_hard = self._find_missing(jd.hard_skills, resume_skills)
        missing_soft = self._find_missing(jd.soft_skills, resume_skills)

        logger.info(
            "Pre-filter — JD hard skills: %d, missing: %d | "
            "JD soft skills: %d, missing: %d",
            len(jd.hard_skills), len(missing_hard),
            len(jd.soft_skills), len(missing_soft),
        )

        raw = self._claude.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_message=_build_user_message(resume, jd, missing_hard, missing_soft),
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0,
        )

        gaps = self._parse_gaps(raw)

        # Sort most impactful first
        gaps.sort(key=lambda g: g.impact_on_fit, reverse=True)

        self._log_summary(gaps, resume.name or "candidate")
        return gaps

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_gaps(raw: str) -> list:
        """Parse Claude's JSON response into a list of Gap instances."""
        from models import Gap

        try:
            data = parse_json_response(raw)
        except ValueError as exc:
            logger.error("Failed to parse gap analysis JSON: %s", exc)
            return []

        raw_gaps = data.get("gaps")
        if not isinstance(raw_gaps, list):
            logger.error("Expected 'gaps' list in response, got: %s", type(raw_gaps))
            return []

        gaps: list = []
        for item in raw_gaps:
            if not isinstance(item, dict):
                logger.warning("Skipping non-dict gap entry: %s", item)
                continue
            try:
                gap_type = str(item.get("type", "hard")).strip().lower()
                reason = str(item.get("reason", "")).strip()

                gap = Gap(
                    skill=str(item.get("skill", "Unknown")).strip(),
                    type=gap_type,
                    severity=str(item.get("severity", "medium")).strip().lower(),
                    reason=reason,
                    impact_on_fit=float(item.get("impact_on_fit", 50)),
                    # backward-compat fields derived automatically
                    category=_type_to_category(gap_type),
                    description=reason,
                )
                gaps.append(gap)
            except Exception as exc:
                logger.warning("Skipping malformed gap entry %s: %s", item, exc)

        return gaps

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_missing(required: List[str], resume_skills: List[str]) -> List[str]:
        """Return items from required that have no fuzzy match in resume_skills."""
        resume_lower = [s.lower() for s in resume_skills]
        missing = []
        for skill in required:
            skill_l = skill.lower()
            # Match if the skill is a substring of any resume skill or vice versa
            if not any(skill_l in r or r in skill_l for r in resume_lower):
                missing.append(skill)
        return missing

    @staticmethod
    def _log_summary(gaps: list, name: str) -> None:
        if not gaps:
            logger.info("No gaps found for %s — strong match!", name)
            return

        counts: dict = {}
        for g in gaps:
            counts[g.severity] = counts.get(g.severity, 0) + 1

        breakdown = "  ".join(
            f"{sev.upper()}: {counts[sev]}"
            for sev in ("critical", "high", "medium", "low")
            if sev in counts
        )
        logger.info(
            "Gap analysis for %s — %d gaps found  |  %s",
            name, len(gaps), breakdown,
        )
        for gap in gaps:
            logger.info(
                "  [%s] %-30s  impact=%3.0f  %s",
                gap.severity.upper()[:4],
                gap.skill,
                gap.impact_on_fit,
                gap.reason,
            )


def _type_to_category(gap_type: str) -> str:
    """Map Gap.type values to the legacy Gap.category vocabulary."""
    return {
        "hard": "skill",
        "soft": "skill",
        "experience": "experience",
        "keyword": "keyword",
    }.get(gap_type, "skill")
