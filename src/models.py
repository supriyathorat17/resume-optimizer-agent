"""Pydantic data models shared across all agents."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Resume sub-models
# ---------------------------------------------------------------------------

class ExperienceEntry(BaseModel):
    """One position held at a single company."""

    company: str
    role: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None       # "Present" or a date string
    location: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    """One degree or credential from a single institution."""

    school: str
    degree: str
    field: Optional[str] = None
    gpa: Optional[str] = None
    graduation_date: Optional[str] = None


class SkillGroup(BaseModel):
    """A named category of skills (e.g. 'Languages', 'Frameworks')."""

    category: str
    items: List[str] = Field(default_factory=list)


class Project(BaseModel):
    """A personal or professional project listed on the resume."""

    title: str
    description: str
    tech_stack: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level Resume model
# ---------------------------------------------------------------------------

class Resume(BaseModel):
    """Structured representation of a parsed resume."""

    raw_text: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    experience: List[ExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    skills: List[SkillGroup] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)

    def flat_skills(self) -> List[str]:
        """Return all skill items as a flat list, regardless of category."""
        return [item for group in self.skills for item in group.items]


# ---------------------------------------------------------------------------
# Job description sub-models
# ---------------------------------------------------------------------------

class SalaryRange(BaseModel):
    """Optional compensation range extracted from a job posting."""

    min_value: Optional[float] = None
    max_value: Optional[float] = None
    currency: str = "USD"
    period: str = "yearly"   # yearly | hourly | monthly


# ---------------------------------------------------------------------------
# Top-level JobDescription model
# ---------------------------------------------------------------------------

class JobDescription(BaseModel):
    """Structured representation of a parsed job description."""

    raw_text: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None   # full-time | part-time | contract
    seniority_level: Optional[str] = None   # junior | mid | senior | staff | …

    # Categorised skill lists populated by JDAnalyzer
    hard_skills: List[str] = Field(default_factory=list)        # technical: Python, AWS, k8s …
    soft_skills: List[str] = Field(default_factory=list)        # interpersonal: leadership, …
    must_have_experience: List[str] = Field(default_factory=list)  # "5+ years Python", domains
    nice_to_have: List[str] = Field(default_factory=list)       # preferred but not required

    # Broader lists kept for pipeline compatibility
    required_skills: List[str] = Field(default_factory=list)    # hard + soft combined
    preferred_skills: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    salary: Optional[SalaryRange] = None

    def all_required(self) -> List[str]:
        """Return hard_skills + soft_skills + must_have_experience as one flat list."""
        return self.hard_skills + self.soft_skills + self.must_have_experience


# ---------------------------------------------------------------------------
# Pipeline models
# ---------------------------------------------------------------------------

class Gap(BaseModel):
    """A single gap identified between a resume and a job description."""

    skill: str                          # The missing skill or requirement name
    type: str = "hard"                  # hard | soft | experience | keyword
    severity: str = "medium"           # critical | high | medium | low
    reason: str = ""                    # Why this gap matters for the role
    impact_on_fit: float = 50.0        # 0–100; used to sort gaps most-critical-first

    # Kept for backward compatibility with the rest of the pipeline
    category: str = ""                  # derived: hard/soft→"skill", experience→"experience"
    description: str = ""              # mirrors reason


class Suggestion(BaseModel):
    """An actionable suggestion for improving a resume section."""

    gap: str                        # The gap this suggestion addresses
    suggested_revision: str         # Concrete bullet point or skill addition
    reasoning: str                  # Why this revision closes the gap
    section: str                    # experience | skills | projects | summary
    priority: int = 5               # 1–10, higher = more impactful

    # Backward-compat aliases — auto-populated from the primary fields
    original: Optional[str] = None  # existing resume text being replaced (if any)
    suggested: str = ""             # mirrors suggested_revision
    rationale: str = ""             # mirrors reasoning

    @model_validator(mode="after")
    def _sync_compat_fields(self) -> "Suggestion":
        """Keep suggested/rationale in sync with the primary fields."""
        if not self.suggested:
            self.suggested = self.suggested_revision
        if not self.rationale:
            self.rationale = self.reasoning
        return self


class OptimizationMetrics(BaseModel):
    """Scores and metadata captured after each optimization iteration."""

    iteration: int
    ats_score: float
    gaps_remaining: int
    suggestions_applied: int
    passed_threshold: bool
