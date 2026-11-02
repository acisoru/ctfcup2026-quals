import os
import sqlite3
import time

DATA_DIR = "/data"
DB_PATH = os.path.join(DATA_DIR, "uroki.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    teacher TEXT NOT NULL,
    scheduled_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    homework TEXT,
    file_name TEXT,
    file_path TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_lesson ON comments (lesson_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _query(sql, args=()):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def _exec(sql, args=()):
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def create_lesson(title, subject, teacher, scheduled_at) -> int:
    return _exec(
        "INSERT INTO lessons (title, subject, teacher, scheduled_at, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (title, subject, teacher, scheduled_at, int(time.time())),
    )


def get_lesson(lesson_id):
    rows = _query("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    return rows[0] if rows else None


def list_lessons(q=None, status=None, subject=None):
    where, args = [], []
    if q:
        where.append("(title LIKE ? ESCAPE '\\' OR teacher LIKE ? ESCAPE '\\' OR subject LIKE ? ESCAPE '\\')")
        pat = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        args += [pat, pat, pat]
    if status:
        where.append("status = ?")
        args.append(status)
    if subject:
        where.append("subject = ?")
        args.append(subject)
    sql = "SELECT * FROM lessons"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY scheduled_at, id"
    return _query(sql, tuple(args))


def update_lesson(lesson_id, title, subject, teacher, scheduled_at) -> None:
    _exec(
        "UPDATE lessons SET title = ?, subject = ?, teacher = ?, scheduled_at = ? WHERE id = ?",
        (title, subject, teacher, scheduled_at, lesson_id),
    )


def set_homework(lesson_id, homework) -> None:
    _exec("UPDATE lessons SET homework = ? WHERE id = ?", (homework, lesson_id))


def set_status(lesson_id, status) -> None:
    _exec("UPDATE lessons SET status = ? WHERE id = ?", (status, lesson_id))


def get_lesson_for_delete(lesson_id):
    rows = _query("SELECT file_path FROM lessons WHERE id = ?", (lesson_id,))
    return rows[0] if rows else None


def delete_lesson(lesson_id) -> None:
    _exec("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    _exec("DELETE FROM comments WHERE lesson_id = ?", (lesson_id,))


def add_comment(lesson_id, author, body) -> int:
    return _exec(
        "INSERT INTO comments (lesson_id, author, body, created_at) VALUES (?, ?, ?, ?)",
        (lesson_id, author, body, int(time.time())),
    )


def list_comments(lesson_id):
    return _query("SELECT * FROM comments WHERE lesson_id = ? ORDER BY id", (lesson_id,))


def delete_comment(comment_id) -> None:
    _exec("DELETE FROM comments WHERE id = ?", (comment_id,))


def status_counts():
    rows = _query("SELECT status, COUNT(*) AS cnt FROM lessons GROUP BY status")
    return {r["status"]: r["cnt"] for r in rows}


def teacher_directory():
    return _query(
        "SELECT teacher, COUNT(*) AS total, SUM(status = 'planned') AS upcoming "
        "FROM lessons GROUP BY teacher ORDER BY total DESC, teacher"
    )


def subject_directory():
    return _query(
        "SELECT subject, COUNT(*) AS total, SUM(status = 'planned') AS upcoming "
        "FROM lessons GROUP BY subject ORDER BY total DESC, subject"
    )


def set_attachment(lesson_id, file_name, file_path) -> None:
    _exec(
        "UPDATE lessons SET file_name = ?, file_path = ? WHERE id = ?",
        (file_name, file_path, lesson_id),
    )


def mark_done(lesson_id) -> None:
    _exec("UPDATE lessons SET status = 'done' WHERE id = ?", (lesson_id,))


def list_planned():
    return _query("SELECT * FROM lessons WHERE status = 'planned' ORDER BY id")
