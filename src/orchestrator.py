"""Agent orchestrator that coordinates the full optimization pipeline."""

import logging

from config import config
from agents import ResumeParser, JDAnalyzer, GapFinder, SuggestionGenerator, Validator
from apis.claude_api import ClaudeAPIClient
from storage.db import SQLiteDB

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates all agents to iteratively optimize a resume against a job description."""

    def __init__(self) -> None:
        """Instantiate all agents and shared dependencies."""
        self._claude = ClaudeAPIClient(api_key=config.CLAUDE_API_KEY)
        self._db = SQLiteDB()
        # Agents self-initialise their Claude client from config;
        # passing explicitly here keeps a single shared client instance.
        self._parser = ResumeParser(claude_client=self._claude)
        self._jd_analyzer = JDAnalyzer(claude_client=self._claude)
        self._gap_finder = GapFinder()
        self._suggestion_gen = SuggestionGenerator()
        self._validator = Validator()

    def run(self, resume_path: str, jd_path: str, output_path: str) -> None:
        """Execute the full optimization loop and write results to output_path."""
        logger.info("Starting optimization: resume=%s  jd=%s", resume_path, jd_path)

        run_id = self._db.save_run(resume_path, jd_path)

        resume = self._parser.parse(resume_path)
        job_description = self._jd_analyzer.analyze(jd_path)

        for iteration in range(1, config.MAX_ITERATIONS + 1):
            logger.info("Iteration %d / %d", iteration, config.MAX_ITERATIONS)

            gaps = self._gap_finder.find_gaps(resume, job_description)
            suggestions = self._suggestion_gen.generate(resume, gaps)
            metrics = self._validator.validate(resume, job_description)

            self._db.save_metrics(run_id, metrics)
            logger.info("ATS score: %.1f  gaps: %d", metrics.ats_score, metrics.gaps_remaining)

            if metrics.passed_threshold:
                logger.info("Threshold reached — stopping early.")
                break

        self._write_output(resume, output_path)
        self._db.close()
        logger.info("Done. Output written to %s", output_path)

    def _write_output(self, resume, output_path: str) -> None:
        """Serialize the optimized resume to the output file."""
        import pathlib
        pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(output_path).write_text(resume.raw_text, encoding="utf-8")
