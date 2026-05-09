"""Application configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Holds all runtime configuration values sourced from .env."""

    CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")
    RESUME_WORDED_API_KEY: str = os.getenv("RESUME_WORDED_API_KEY", "")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "3"))
    ATS_SCORE_THRESHOLD: float = float(os.getenv("ATS_SCORE_THRESHOLD", "85"))

    @classmethod
    def validate(cls) -> None:
        """Raise ValueError if required keys are missing."""
        if not cls.CLAUDE_API_KEY or cls.CLAUDE_API_KEY == "your_key_here":
            raise ValueError("CLAUDE_API_KEY is not set in .env")


config = Config()
