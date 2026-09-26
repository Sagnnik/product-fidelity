from __future__ import annotations

import sqlite3

from backend import db as storage

FREE_CAMPAIGNS = 3
def connect() -> sqlite3.Connection:
    db = storage.connect()
    db.execute(
        "CREATE TABLE IF NOT EXISTS free_usage (user_id TEXT PRIMARY KEY, campaigns_started INTEGER NOT NULL)"
    )
    return db


def free_used(user_id: str) -> int:
    db = connect()
    try:
        row = db.execute("SELECT campaigns_started FROM free_usage WHERE user_id = ?", (user_id,)).fetchone()
        return row[0] if row else 0
    finally:
        db.close()


def reserve_free_campaign(user_id: str) -> bool:
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT campaigns_started FROM free_usage WHERE user_id = ?", (user_id,)).fetchone()
        used = row[0] if row else 0
        if used >= FREE_CAMPAIGNS:
            db.rollback()
            return False
        db.execute(
            "INSERT INTO free_usage (user_id, campaigns_started) VALUES (?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET campaigns_started = campaigns_started + 1",
            (user_id,),
        )
        db.commit()
        return True
    finally:
        db.close()


def release_free_campaign(user_id: str) -> None:
    db = connect()
    try:
        db.execute(
            "UPDATE free_usage SET campaigns_started = MAX(0, campaigns_started - 1) WHERE user_id = ?",
            (user_id,),
        )
        db.commit()
    finally:
        db.close()
