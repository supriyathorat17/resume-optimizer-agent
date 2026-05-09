"""ResumeParser — extracts structured data from PDF/DOCX resumes via Claude."""

import logging
from typing import Any, Dict

from utils.text import extract_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction schema shown to Claude (kept as a constant for prompt stability)
# ---------------------------------------------------------------------------

_SCHEMA_DESCRIPTION = """\
{
  "name": "Full name or null",
  "email": "Email address or null",
  "phone": "Phone number or null",
  "location": "City, State/Country or null",
  "summary": "Professional summary paragraph or null",
  "experience": [
    {
      "company": "Company name",
      "role": "Job title",
      "start_date": "e.g. Jan 2020 or 2020-01 or null",
      "end_date": "e.g. Mar 2023 or Present or null",
      "location": "City, State or null",
      "bullets": ["Accomplishment or responsibility sentence", ...]
    }
  ],
  "education": [
    {
      "school": "Institution name",
      "degree": "e.g. B.S., M.S., Ph.D.",
      "field": "Field of study or null",
      "gpa": "e.g. 3.8/4.0 or null",
      "graduation_date": "e.g. May 2018 or null"
    }
  ],
  "skills": [
    {
      "category": "e.g. Languages, Frameworks, Tools, Databases, Cloud, Soft Skills",
      "items": ["Skill1", "Skill2", ...]
    }
  ],
  "projects": [
    {
      "title": "Project name",
      "description": "One or two sentence description",
      "tech_stack": ["Technology1", "Technology2", ...]
    }
  ],
  "certifications": ["Certification name and issuer", ...]
}"""

_SYSTEM_PROMPT = f"""\
You are a precise resume parser. Your sole job is to extract every piece of \
information from the provided resume text and return it as a single JSON object.

Use this exact schema:
{_SCHEMA_DESCRIPTION}

Strict rules:
- Preserve original wording for bullet points, descriptions, and titles.
- Use null for any field that is absent — never omit keys.
- Group skills by their stated category. If the resume has no categories, \
  infer sensible ones (Languages, Frameworks, Tools, etc.). \
  As a last resort use "General".
- Deduplicate skill items.
- Include ALL work experience entries, projects, and education records found.
- Respond with the JSON object only — no markdown, no commentary."""


class ResumeParser:
    """Extracts structured resume data from PDF/DOCX files using Claude."""

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

    def parse(self, file_path: str):
        """Parse a resume file and return a fully populated Resume instance.

        Raises FileNotFoundError for missing files and ValueError for
        unsupported types or files that yield no extractable text.
        """
        from models import Resume, ExperienceEntry, EducationEntry, SkillGroup, Project

        raw_text = extract_text(file_path)
        logger.info("Extracted %d chars from '%s', sending to Claude", len(raw_text), file_path)

        data = self._extract_with_claude(raw_text)

        resume = Resume(
            raw_text=raw_text,
            name=data.get("name"),
            email=data.get("email"),
            phone=data.get("phone"),
            location=data.get("location"),
            summary=data.get("summary"),
            experience=self._build_experience(data.get("experience", [])),
            education=self._build_education(data.get("education", [])),
            skills=self._build_skills(data.get("skills", [])),
            projects=self._build_projects(data.get("projects", [])),
            certifications=self._coerce_list(data.get("certifications")),
        )

        logger.info(
            "Parsed resume: name=%s  exp=%d  edu=%d  skill_groups=%d  projects=%d",
            resume.name,
            len(resume.experience),
            len(resume.education),
            len(resume.skills),
            len(resume.projects),
        )
        return resume

    # ------------------------------------------------------------------
    # Claude extraction
    # ------------------------------------------------------------------

    def _extract_with_claude(self, raw_text: str) -> Dict[str, Any]:
        return self._claude.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_message=f"Parse this resume:\n\n{raw_text}",
        )

    # ------------------------------------------------------------------
    # Model builders — each tolerates missing or malformed Claude output
    # ------------------------------------------------------------------

    @staticmethod
    def _build_experience(entries) -> list:
        from models import ExperienceEntry

        result = []
        for raw in entries or []:
            if not isinstance(raw, dict):
                continue
            result.append(
                ExperienceEntry(
                    company=raw.get("company") or "Unknown Company",
                    role=raw.get("role") or "Unknown Role",
                    start_date=raw.get("start_date"),
                    end_date=raw.get("end_date"),
                    location=raw.get("location"),
                    bullets=ResumeParser._coerce_list(raw.get("bullets")),
                )
            )
        return result

    @staticmethod
    def _build_education(entries) -> list:
        from models import EducationEntry

        result = []
        for raw in entries or []:
            if not isinstance(raw, dict):
                continue
            result.append(
                EducationEntry(
                    school=raw.get("school") or "Unknown Institution",
                    degree=raw.get("degree") or "Unknown Degree",
                    field=raw.get("field"),
                    gpa=raw.get("gpa"),
                    graduation_date=raw.get("graduation_date"),
                )
            )
        return result

    @staticmethod
    def _build_skills(entries) -> list:
        from models import SkillGroup

        result = []
        for raw in entries or []:
            if not isinstance(raw, dict):
                continue
            items = ResumeParser._coerce_list(raw.get("items"))
            if items:
                result.append(
                    SkillGroup(
                        category=raw.get("category") or "General",
                        items=items,
                    )
                )
        return result

    @staticmethod
    def _build_projects(entries) -> list:
        from models import Project

        result = []
        for raw in entries or []:
            if not isinstance(raw, dict):
                continue
            result.append(
                Project(
                    title=raw.get("title") or "Untitled Project",
                    description=raw.get("description") or "",
                    tech_stack=ResumeParser._coerce_list(raw.get("tech_stack")),
                )
            )
        return result

    @staticmethod
    def _coerce_list(value) -> list:
        """Return value as a list, handling None, single strings, and existing lists."""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str):
            return [value] if value.strip() else []
        return []
