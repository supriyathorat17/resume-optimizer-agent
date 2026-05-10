"""Specialized agents used in the resume optimization pipeline."""

from agents.parser import ResumeParser
from agents.analyzer import JDAnalyzer
from agents.gap_finder import GapFinder
from agents.suggester import SuggestionGenerator


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
