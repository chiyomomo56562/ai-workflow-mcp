"""SQLite connection helpers reserved for the Phase 1 persistence slice."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(database: str | Path = ":memory:") -> sqlite3.Connection:
    """Create a SQLite connection with foreign-key enforcement enabled."""
    connection = sqlite3.connect(str(database))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

