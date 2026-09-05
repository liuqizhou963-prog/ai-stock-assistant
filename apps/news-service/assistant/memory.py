import json
import time

from .db import get_connection


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def list_memories():
    # list_memories（查询所有记忆，按id降序）
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, memory_type, title, content, tags, created_at "
            "FROM memories ORDER BY id DESC"
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["tags"] = json.loads(item["tags"])
        except Exception:
            item["tags"] = []
        result.append(item)
    return result


def save_memory(memory_type, title, content, tags=None):
    # save_memory（写入一条长期记忆，返回新记录 id）
    tags = tags or []
    now = _now()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO memories
              (memory_type, title, content, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                memory_type,
                title,
                content,
                json.dumps(tags, ensure_ascii=False),
                now,
                now,
            ),
        )
        return cur.lastrowid


def delete_memory(memory_id):
    # delete_memory（物理删除指定记忆）
    with get_connection() as conn:
        conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
