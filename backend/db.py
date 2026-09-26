from __future__ import annotations

import sqlite3

from backend.fal_api import DATA_ROOT

DB_PATH = DATA_ROOT / "db" / "stillroom.sqlite3"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, timeout=10)
