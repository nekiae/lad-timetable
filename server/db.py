"""Хранилище: SQLite, школа — один JSON-документ.

Документ школы — ровно тот формат, что пишет Streamlit в data/school.json:
{"tables": {...}, "settings": {...}, "wishes": {...}}. Схему таблиц не
разбираем на колонки: она ещё меняется, а миграции за пять дней не нужны.

Каждое сохранение — новая ревизия, старые не удаляются. Урок 08.09.2026:
автосохранение молча стёрло 52 учителя, и вернуть их удалось только из git.
Здесь любое прошлое состояние школы достаётся одним запросом.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import ROOT

DB_PATH = Path(os.environ.get("LAD_DB", ROOT / "data" / "lad.sqlite3"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS schools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS school_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id TEXT NOT NULL REFERENCES schools(id),
    doc TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS rev_by_school ON school_revisions(school_id, id);
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL REFERENCES schools(id),
    revision_id INTEGER,
    lessons TEXT NOT NULL,
    meta TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sched_by_school ON schedules(school_id, created_at);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------- школы

def list_schools() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, updated_at FROM schools ORDER BY updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def create_school(doc: dict) -> str:
    school_id, now = _new_id(), time.time()
    name = (doc.get("settings") or {}).get("name") or "Новая школа"
    with connect() as conn:
        conn.execute("INSERT INTO schools VALUES (?, ?, ?, ?)", (school_id, name, now, now))
        conn.execute("INSERT INTO school_revisions (school_id, doc, created_at) VALUES (?, ?, ?)",
                     (school_id, json.dumps(doc, ensure_ascii=False), now))
    return school_id


def get_school(school_id: str) -> tuple[dict, int] | None:
    """Последняя ревизия документа школы и её номер."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, doc FROM school_revisions WHERE school_id = ? ORDER BY id DESC LIMIT 1",
            (school_id,)).fetchone()
    return (json.loads(row["doc"]), row["id"]) if row else None


def save_school(school_id: str, doc: dict) -> int:
    now = time.time()
    name = (doc.get("settings") or {}).get("name") or "Школа"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO school_revisions (school_id, doc, created_at) VALUES (?, ?, ?)",
            (school_id, json.dumps(doc, ensure_ascii=False), now))
        conn.execute("UPDATE schools SET name = ?, updated_at = ? WHERE id = ?",
                     (name, now, school_id))
        return cur.lastrowid


def list_revisions(school_id: str, limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at FROM school_revisions WHERE school_id = ? "
            "ORDER BY id DESC LIMIT ?", (school_id, limit)).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------- расписания

def save_schedule(school_id: str, revision_id: int | None, lessons: list[dict],
                  meta: dict) -> str:
    schedule_id = _new_id()
    with connect() as conn:
        conn.execute("INSERT INTO schedules VALUES (?, ?, ?, ?, ?, ?)",
                     (schedule_id, school_id, revision_id,
                      json.dumps(lessons, ensure_ascii=False),
                      json.dumps(meta, ensure_ascii=False), time.time()))
    return schedule_id


def get_schedule(schedule_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    return _schedule_row(row)


def latest_schedule(school_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM schedules WHERE school_id = ? ORDER BY created_at DESC LIMIT 1",
            (school_id,)).fetchone()
    return _schedule_row(row)


def _schedule_row(row) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["lessons"] = json.loads(data["lessons"])
    data["meta"] = json.loads(data["meta"])
    return data
