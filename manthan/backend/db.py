"""
MANTHAN - Lecture Amnesia Fixer
SQLite database layer. Uses plain sqlite3 (no ORM) to keep the reference
implementation dependency-light and easy to read/extend.
"""
import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "manthan.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    streak INTEGER DEFAULT 0,
    last_active_date TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    source_type TEXT NOT NULL,        -- 'live_recording' | 'file_upload' | 'text_paste'
    transcript TEXT,
    created_at TEXT NOT NULL,
    time_offset_minutes INTEGER DEFAULT 0  -- dev-only clock skew for demoing D1/D7/D30/D45
);

CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    concept_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,              -- 'day1' | 'day7' | 'day30' | 'day45'
    due_at TEXT NOT NULL,
    completed INTEGER DEFAULT 0,
    completed_at TEXT,
    score REAL,                       -- 0-100, null until completed
    UNIQUE(lecture_id, stage)
);

CREATE TABLE IF NOT EXISTS quiz_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    question TEXT NOT NULL,
    options_json TEXT NOT NULL,
    correct_index INTEGER NOT NULL,
    explanation TEXT
);

CREATE TABLE IF NOT EXISTS badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    badge_name TEXT NOT NULL,         -- Starter | Walker | Flyer | Supreme
    awarded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teach_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    explanation_text TEXT NOT NULL,
    coverage_score REAL NOT NULL,
    feedback TEXT,
    passed INTEGER NOT NULL,
    submitted_at TEXT NOT NULL
);
"""


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now_iso():
    return datetime.datetime.utcnow().isoformat()
