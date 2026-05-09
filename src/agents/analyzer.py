"""JDAnalyzer — categorizes job description requirements into structured fields via Claude."""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction schema
# ---------------------------------------------------------------------------

_SCHEMA_DESCRIPTION = """\
{
  "title": "Job title or null",
  "company": "Company name or null",
  "location": "City/State, 'Remote', 'Hybrid' or null",
  "employment_type": "full-time | part-time | contract | internship or null",
  "seniority_level": "intern | junior | mid | senior | staff | principal | director or null",

  "hard_skills": [
    "Every concrete technical skill: programming languages, frameworks, libraries, platforms,
     databases, cloud services, DevOps tools, certifications — items the role REQUIRES"
  ],

  "soft_skills": [
    "Every interpersonal / behavioral skill: leadership, communication, collaboration,
     problem-solving, mentoring, stakeholder management — items the role REQUIRES"
  ],

  "must_have_experience": [
    "Explicit experience requirements stated as facts: '5+ years Python',
     'experience with distributed systems', 'prior startup experience',
     'background in fintech' — copy the phrasing from the JD closely"
  ],

  "nice_to_have": [
    "Skills, experience, tools, or qualifications listed under 'Preferred',
     'Nice to have', 'Bonus', 'Plus', 'Ideal candidate' — not strictly required"
  ],

  "responsibilities": [
    "Key responsibilities and day-to-day duties, verbatim from the JD"
  ],

  "qualifications": [
    "Formal educational requirements and credentialing statements"
  ],

  "keywords": [
    "Every high-value ATS keyword from across the entire posting: technical terms,
     methodologies (Agile, Scrum), domain nouns, product names, acronyms.
     Include items already in other lists — this is the comprehensive ATS scan list."
  ],

  "salary": {
    "min_value": 120000,
    "max_value": 160000,
    "currency": "USD",
    "period": "yearly | hourly | monthly"
  }
}"""

_SYSTEM_PROMPT = f"""\
You are an expert technical recruiter and ATS specialist. Your job is to read a job \
description and extract every requirement into a structured JSON object.

Use this exact schema:
{_SCHEMA_DESCRIPTION}

Classification rules:
1. hard_skills — ONLY technical, tool-based, or domain-specific skills that are REQUIRED.
   Examples: Python, Kubernetes, PostgreSQL, Terraform, React, CI/CD, REST APIs.
2. soft_skills — ONLY behavioral/interpersonal skills that are REQUIRED.
   Examples: leadership, written communication, cross-functional collaboration.
3. must_have_experience — Explicit experience statements with years, domains, or \
   industries that are clearly REQUIRED (not preferred). Copy the wording closely.
4. nice_to_have — Anything under 'preferred', 'bonus', 'nice to have', 'plus', or \
   'ideal'. If ambiguous, lean toward nice_to_have.
5. keywords — Be exhaustive: every acronym, tool, methodology, domain term that an \
   ATS scanner would look for. Overlap with other lists is expected and correct.
6. salary — Set to null if no compensation info is present.
7. Use null for absent scalar fields; use [] for absent list fields — never omit keys.
8. Respond with the JSON object ONLY — no markdown, no commentary."""


class JDAnalyzer:
    """Parses a job description and returns a structured JobDescription instance.

    Usage:
        jd = JDAnalyzer().analyze("We are looking for a Senior Python Engineer...")
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

    def analyze(self, text: str):
        """Analyze raw job description text and return a populated JobDescription.

        Args:
            text: The full job description as a plain string.

        Returns:
            JobDescription with hard_skills, soft_skills, must_have_experience,
            nice_to_have, and all other structured fields populated.
        """
        if not text or not text.strip():
            raise ValueError("Job description text is empty.")

        logger.info("Analyzing JD (%d chars) with Claude", len(text))

        data = self._analyze_with_claude(text.strip())
        return self._build_model(text, data)

    def analyze_file(self, file_path: str):
        """Read a JD file (PDF/DOCX/TXT) and delegate to analyze().

        Convenience wrapper — prefer analyze() when the text is already in memory.
        """
        from utils.text import extract_text

        raw_text = extract_text(file_path)
        logger.info("Loaded JD from '%s' (%d chars)", file_path, len(raw_text))
        return self.analyze(raw_text)

    # ------------------------------------------------------------------
    # Claude extraction
    # ------------------------------------------------------------------

    def _analyze_with_claude(self, text: str) -> Dict[str, Any]:
        return self._claude.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_message=f"Analyze this job description:\n\n{text}",
        )

    # ------------------------------------------------------------------
    # Model assembly
    # ------------------------------------------------------------------

    def _build_model(self, raw_text: str, data: Dict[str, Any]):
        from models import JobDescription

        hard_skills = self._clean_list(data.get("hard_skills"))
        soft_skills = self._clean_list(data.get("soft_skills"))
        nice_to_have = self._clean_list(data.get("nice_to_have"))

        # required_skills = union of hard + soft for backward-compatible pipeline use
        required_skills = self._deduplicate(hard_skills + soft_skills)

        jd = JobDescription(
            raw_text=raw_text,
            title=data.get("title"),
            company=data.get("company"),
            location=data.get("location"),
            employment_type=data.get("employment_type"),
            seniority_level=data.get("seniority_level"),
            hard_skills=hard_skills,
            soft_skills=soft_skills,
            must_have_experience=self._clean_list(data.get("must_have_experience")),
            nice_to_have=nice_to_have,
            required_skills=required_skills,
            preferred_skills=nice_to_have,   # mirror for pipeline compat
            responsibilities=self._clean_list(data.get("responsibilities")),
            qualifications=self._clean_list(data.get("qualifications")),
            keywords=self._deduplicate(self._clean_list(data.get("keywords"))),
            salary=self._build_salary(data.get("salary")),
        )

        self._log_summary(jd)
        return jd

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_salary(raw):
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
            logger.warning("Could not parse salary field: %s — %s", raw, exc)
            return None

    @staticmethod
    def _clean_list(value) -> List[str]:
        """Normalise Claude output to a clean list of non-empty strings."""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if v and str(v).strip()]
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        return []

    @staticmethod
    def _deduplicate(items: List[str]) -> List[str]:
        """Remove case-insensitive duplicates while preserving insertion order."""
        seen: set = set()
        result = []
        for item in items:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    @staticmethod
    def _log_summary(jd) -> None:
        logger.info(
            "JD parsed — title: %r | company: %r | seniority: %r | "
            "hard_skills: %d | soft_skills: %d | must_have_exp: %d | "
            "nice_to_have: %d | keywords: %d",
            jd.title,
            jd.company,
            jd.seniority_level,
            len(jd.hard_skills),
            len(jd.soft_skills),
            len(jd.must_have_experience),
            len(jd.nice_to_have),
            len(jd.keywords),
        )
        if jd.hard_skills:
            logger.debug("Hard skills: %s", ", ".join(jd.hard_skills))
        if jd.soft_skills:
            logger.debug("Soft skills: %s", ", ".join(jd.soft_skills))
        if jd.must_have_experience:
            logger.debug("Must-have experience: %s", " | ".join(jd.must_have_experience))
        if jd.nice_to_have:
            logger.debug("Nice to have: %s", ", ".join(jd.nice_to_have))
