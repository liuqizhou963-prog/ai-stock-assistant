import hashlib
import json
import os
import time

from .db import get_connection


def make_article_key(url, source, title):
    # make_article_key（根据 URL 或「来源+标题」生成 MD5 唯一键，用于 saved_articles 表）
    raw = url or f"{source}{title}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def load_data_js(path):
    # load_data_js（读取 data.js，提取其中的 JSON 对象；兼容 window.DATA= 和 const data= 前缀）
    with open(path, encoding="utf-8") as f:
        text = f.read()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("data.js 中没有找到数据对象")
    return json.loads(text[start : end + 1])


def save_article(article_key, url, title, source, industry_key, note="", tags=None):
    # save_article（收藏一篇文章：写入 saved_articles 表，并在 memories 表插入 saved_article 类型记忆）
    tags = tags or []
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    tags_json = json.dumps(tags, ensure_ascii=False)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO saved_articles(article_key, url, title, source, industry_key, note, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_key,
                url or "",
                title or "",
                source or "",
                industry_key or "",
                note or "",
                tags_json,
                now,
            ),
        )
        # 联动写入 memories 表，用于"我的记忆"收藏文章分类展示
        conn.execute(
            """
            INSERT INTO memories(memory_type, title, content, tags, source, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "saved_article",
                title or "",
                note or f"收藏自 {source}",
                tags_json,
                source or "",
                1.0,
                now,
                now,
            ),
        )


def list_saved_article_keys():
    # list_saved_article_keys（返回所有已收藏文章的 article_key 集合，用于推荐打分加权）
    with get_connection() as conn:
        rows = conn.execute("SELECT article_key FROM saved_articles").fetchall()
    return {row["article_key"] for row in rows}
