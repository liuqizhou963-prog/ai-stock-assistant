import os
import sqlite3
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, "state")
DB_PATH = os.path.join(STATE_DIR, "assistant.db")


@contextmanager
def get_connection():
    # get_connection（获取数据库连接，退出时提交并关闭，Windows 下避免文件锁）
    os.makedirs(STATE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    # init_db（建表，幂等操作，服务启动时调用一次）
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
              id          INTEGER PRIMARY KEY AUTOINCREMENT,
              memory_type TEXT    NOT NULL,
              title       TEXT    NOT NULL,
              content     TEXT    NOT NULL,
              tags        TEXT    NOT NULL DEFAULT '[]',
              source      TEXT    NOT NULL DEFAULT '',
              confidence  REAL    NOT NULL DEFAULT 1.0,
              created_at  TEXT    NOT NULL,
              updated_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS saved_articles (
              id           INTEGER PRIMARY KEY AUTOINCREMENT,
              article_key  TEXT    NOT NULL,
              url          TEXT    NOT NULL DEFAULT '',
              title        TEXT    NOT NULL,
              source       TEXT    NOT NULL DEFAULT '',
              industry_key TEXT    NOT NULL DEFAULT '',
              note         TEXT    NOT NULL DEFAULT '',
              tags         TEXT    NOT NULL DEFAULT '[]',
              created_at   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_logs (
              id         INTEGER PRIMARY KEY AUTOINCREMENT,
              role       TEXT    NOT NULL,
              message    TEXT    NOT NULL,
              created_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watchlist (
              id          INTEGER PRIMARY KEY AUTOINCREMENT,
              symbol      TEXT    NOT NULL UNIQUE,
              name        TEXT    NOT NULL DEFAULT '',
              asset_type  TEXT    NOT NULL DEFAULT 'stock',
              note        TEXT    NOT NULL DEFAULT '',
              created_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_alerts (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              symbol        TEXT    NOT NULL,
              name          TEXT    NOT NULL DEFAULT '',
              condition     TEXT    NOT NULL CHECK(condition IN ('above', 'below')),
              threshold     REAL    NOT NULL,
              enabled       INTEGER NOT NULL DEFAULT 1,
              triggered_at  TEXT    NOT NULL DEFAULT '',
              created_at    TEXT    NOT NULL
            );
        """)
