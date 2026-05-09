"""SQLite persistence layer for storing optimization sessions and metrics."""

import sqlite3
from pathlib import Path


class SQLiteDB:
    """Manages a local SQLite database for run history and metrics."""

    DEFAULT_PATH = "data/optimizer.db"

    def __init__(self, db_path: str = DEFAULT_PATH) -> None:
        """Open (or create) the SQLite database at the given path."""
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create tables if they do not already exist."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resume_path TEXT NOT NULL,
                jd_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER REFERENCES runs(id),
                iteration INTEGER,
                ats_score REAL,
                gaps_remaining INTEGER,
                suggestions_applied INTEGER,
                passed_threshold INTEGER
            );
            """
        )
        self._conn.commit()

    def save_run(self, resume_path: str, jd_path: str) -> int:
        """Insert a new run record and return its ID."""
        cursor = self._conn.execute(
            "INSERT INTO runs (resume_path, jd_path) VALUES (?, ?)",
            (resume_path, jd_path),
        )
        self._conn.commit()
        return cursor.lastrowid

    def save_metrics(self, run_id: int, metrics) -> None:
        """Persist an OptimizationMetrics instance for a given run."""
        self._conn.execute(
            """
            INSERT INTO metrics
                (run_id, iteration, ats_score, gaps_remaining, suggestions_applied, passed_threshold)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                metrics.iteration,
                metrics.ats_score,
                metrics.gaps_remaining,
                metrics.suggestions_applied,
                int(metrics.passed_threshold),
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
