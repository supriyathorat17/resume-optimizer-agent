"""Entry point for the Resume Optimizer Agent CLI."""

import argparse
import logging
import sys

from config import config
from orchestrator import AgentOrchestrator


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Optimize a resume against a job description using AI agents."
    )
    parser.add_argument("--resume", required=True, help="Path to resume file (PDF or DOCX)")
    parser.add_argument("--jd", required=True, help="Path to job description file (TXT or PDF)")
    parser.add_argument("--output", default="output/optimized_resume.txt", help="Output file path")
    return parser


def main() -> None:
    """Parse arguments, validate config, and run the orchestrator."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/run.log"),
        ],
    )

    args = build_parser().parse_args()

    try:
        config.validate()
    except ValueError as exc:
        logging.error("Configuration error: %s", exc)
        sys.exit(1)

    orchestrator = AgentOrchestrator()
    orchestrator.run(resume_path=args.resume, jd_path=args.jd, output_path=args.output)


if __name__ == "__main__":
    main()
