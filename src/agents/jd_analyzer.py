"""JDAnalyzer — extracts structured requirements from job descriptions via Claude."""

import logging
from typing import Any, Dict

from utils.text import extract_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction schema
# ---------------------------------------------------------------------------

_SCHEMA_DESCRIPTION = """\
{
  "title": "Job title or null",
  "company": "Company name or null",
  "location": "Location or 'Remote' or null",
  "employment_type": "full-time | part-time | contract | internship or null",
  "seniority_level": "intern | junior | mid | senior | staff | principal | director or null",
  "required_skills": [
    "Skill or technology that is explicitly required"
  ],
  "preferred_skills": [
    "Skill or technology listed as preferred/nice-to-have"
  ],
  "responsibilities": [
    "Responsibility or duty sentence, verbatim from the JD"
  ],
  "qualifications": [
    "Qualification or requirement sentence (education, years of exp, etc.)"
  ],
  "keywords": [
    "High-value ATS keyword — technical terms, methodologies, tools, certifications"
  ],
  "salary": {
    "min_value": 120000,
    "max_value": 160000,
    "currency": "USD",
    "period": "yearly"
  }
}"""

_SYSTEM_PROMPT = f"""\
You are an expert recruiter and ATS (Applicant Tracking System) specialist. \
Analyze the provided job description and extract all structured information \
into a single JSON object.

Use this exact schema:
{_SCHEMA_DESCRIPTION}

Strict rules:
- required_skills: only skills/technologies explicitly marked as required or \
  listed under "Requirements" / "Must have".
- preferred_skills: skills under "Preferred", "Nice to have", "Bonus", "Plus".
- keywords: extract every significant technical term, methodology, tool, \
  framework, certification, or domain noun that an ATS would scan for. \
  Include terms from all sections. Aim for completeness over brevity.
- seniority_level: infer from the title and body text even if not stated explicitly.
- salary: set to null if no compensation information is present; otherwise \
  populate only the fields you can read from the text.
- Use null for any scalar field that is absent — never omit keys.
- Respond with the JSON object only — no markdown, no commentary."""


class JDAnalyzer:
    """Parses a job description file and returns a structured JobDescription instance."""

    def __init__(self, claude_client) -> None:
        """Accept an initialised ClaudeAPIClient for LLM-based extraction."""
        self._claude = claude_client

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(self, file_path: str):
        """Analyze a job description file and return a populated JobDescription.

        Accepts PDF, DOCX, or plain text files.
        Raises FileNotFoundError for missing files.
        """
        from models import JobDescription, SalaryRange

        raw_text = extract_text(file_path)
        logger.info("Extracted %d chars from '%s', sending to Claude", len(raw_text), file_path)

        data = self._analyze_with_claude(raw_text)

        salary = self._build_salary(data.get("salary"))

        jd = JobDescription(
            raw_text=raw_text,
            title=data.get("title"),
            company=data.get("company"),
            location=data.get("location"),
            employment_type=data.get("employment_type"),
            seniority_level=data.get("seniority_level"),
            required_skills=self._coerce_list(data.get("required_skills")),
            preferred_skills=self._coerce_list(data.get("preferred_skills")),
            responsibilities=self._coerce_list(data.get("responsibilities")),
            qualifications=self._coerce_list(data.get("qualifications")),
            keywords=self._deduplicate(self._coerce_list(data.get("keywords"))),
            salary=salary,
        )

        logger.info(
            "Analyzed JD: title=%s  company=%s  required=%d  preferred=%d  keywords=%d",
            jd.title,
            jd.company,
            len(jd.required_skills),
            len(jd.preferred_skills),
            len(jd.keywords),
        )
        return jd

    # ------------------------------------------------------------------
    # Claude extraction
    # ------------------------------------------------------------------

    def _analyze_with_claude(self, raw_text: str) -> Dict[str, Any]:
        return self._claude.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_message=f"Analyze this job description:\n\n{raw_text}",
        )

    # ------------------------------------------------------------------
    # Model builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_salary(raw):
        """Build a SalaryRange from the Claude-returned dict, or return None."""
        from models import SalaryRange

        if not raw or not isinstance(raw, dict):
            return None
        try:
            return SalaryRange(
                min_value=raw.get("min_value"),
                max_value=raw.get("max_value"),
                currency=raw.get("currency", "USD"),
                period=raw.get("period", "yearly"),
            )
        except Exception as exc:
            logger.warning("Could not parse salary data: %s — %s", raw, exc)
            return None

    @staticmethod
    def _coerce_list(value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if v and str(v).strip()]
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        return []

    @staticmethod
    def _deduplicate(items: list) -> list:
        """Return items with duplicates removed, preserving order, case-insensitive."""
        seen: set[str] = set()
        result = []
        for item in items:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result
