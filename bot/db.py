import sqlite3
from datetime import datetime

DB_NAME = "party.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        # ИСПРАВЛЕНО: добавлено IF NOT EXISTS, чтобы не падало при перезапуске
        c.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            track_url TEXT,
            track_title TEXT,
            added_at TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            track_id INTEGER,
            user_id INTEGER,
            UNIQUE(track_id, user_id)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            track_url TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
        """)

        conn.commit()

def add_track(user_id: int, url: str, title: str):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO queue (user_id, track_url, track_title, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, url, title, datetime.utcnow().isoformat())
        )

        c.execute("""
            INSERT INTO stats(track_url, count)
            VALUES (?, 1)
            ON CONFLICT(track_url)
            DO UPDATE SET count = count + 1
        """, (url,))

        conn.commit()


def get_current_track():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # ИСПРАВЛЕНО: добавили track_title в SELECT
        c.execute("SELECT id, track_url, track_title FROM queue ORDER BY id LIMIT 1")
        return c.fetchone()


def pop_track():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM queue WHERE id = (SELECT id FROM queue ORDER BY id LIMIT 1)")
        conn.commit()

def add_vote(track_id: int, user_id: int) -> bool:
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO votes (track_id, user_id) VALUES (?, ?)",
                (track_id, user_id)
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def count_votes(track_id: int) -> int:
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM votes WHERE track_id = ?", (track_id,))
        return c.fetchone()[0]


def clear_votes(track_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM votes WHERE track_id = ?", (track_id,))
        conn.commit()

# --- Новые функции для команд /queue и /top ---

def get_queue_list(limit=10):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT track_title, track_url FROM queue ORDER BY id LIMIT ?", (limit,))
        return c.fetchall()

def get_top_stats(limit=5):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT track_url, count FROM stats ORDER BY count DESC LIMIT ?", (limit,))
        return c.fetchall()


def clear_queue_list():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Удаляем все треки из очереди
        c.execute("DELETE FROM queue")
        # Удаляем все голоса за пропуск
        c.execute("DELETE FROM votes")
        conn.commit()