"""Specialized agents used in the resume optimization pipeline."""

from agents.parser import ResumeParser
from agents.analyzer import JDAnalyzer
from agents.gap_finder import GapFinder


class SuggestionGenerator:
    """Uses Claude to generate targeted rewrite suggestions for identified gaps."""

    def generate(self, resume, gaps):
        """Return a list of Suggestion instances addressing the provided gaps."""
        raise NotImplementedError


class Validator:
    """Scores an optimized resume and verifies ATS threshold compliance."""

    def validate(self, resume, job_description):
        """Return an OptimizationMetrics instance with current scores."""
        raise NotImplementedError


__all__ = [
    "ResumeParser",
    "JDAnalyzer",
    "GapFinder",
    "SuggestionGenerator",
    "Validator",
]
