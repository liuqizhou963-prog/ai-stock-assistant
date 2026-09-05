"""Build a reproducible, local research snapshot from the dashboard data."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from scripts.data_store import load_data_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data.js"
DEFAULT_DB = ROOT / "state" / "research_snapshot.db"

BUSINESS_META = {
    "articles": {
        "description": "按行业归档的投资资讯快照，支持资讯数量、来源和时间统计。",
        "aliases": ["资讯", "新闻", "文章", "投资资讯"],
        "columns": {
            "industry_name": {
                "description": "资讯所属的一级行业名称。",
                "aliases": ["行业", "赛道", "板块"],
            },
            "subindustry_name": {
                "description": "从标题和摘要中归纳出的主题赛道。",
                "aliases": ["主题", "细分赛道"],
            },
            "title": {
                "description": "资讯原始标题。",
                "aliases": ["标题", "新闻标题"],
            },
            "chinese_title": {
                "description": "资讯中文标题，可能为空。",
                "aliases": ["中文标题"],
            },
            "source": {
                "description": "资讯来源名称。",
                "aliases": ["来源", "媒体"],
            },
            "published_at": {
                "description": "资讯发布时间，使用北京时间文本。",
                "aliases": ["发布时间", "日期", "时间"],
            },
            "timestamp": {
                "description": "资讯发布时间的 Unix 时间戳，用于时间排序和过滤。",
                "aliases": ["时间戳", "发布时间戳"],
            },
            "summary": {
                "description": "资讯摘要。",
                "aliases": ["摘要", "内容"],
            },
        },
    }
}


def ensure_snapshot(
    source_path: str | Path = DEFAULT_SOURCE,
    db_path: str | Path = DEFAULT_DB,
) -> dict:
    """Refresh the snapshot only when the source data version changes."""
    source_path = Path(source_path)
    db_path = Path(db_path)
    data = load_data_file(source_path)
    generated_at = str(data.get("generated_at") or "")
    articles = _flatten_articles(data)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshot_meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS articles (
              article_id INTEGER PRIMARY KEY AUTOINCREMENT,
              article_key TEXT NOT NULL UNIQUE,
              industry_key TEXT NOT NULL,
              industry_name TEXT NOT NULL,
              subindustry_name TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL,
              chinese_title TEXT NOT NULL DEFAULT '',
              source TEXT NOT NULL DEFAULT '',
              published_at TEXT NOT NULL DEFAULT '',
              timestamp INTEGER NOT NULL DEFAULT 0,
              url TEXT NOT NULL DEFAULT '',
              summary TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_articles_industry ON articles(industry_name);
            CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
            CREATE INDEX IF NOT EXISTS idx_articles_timestamp ON articles(timestamp);
            """
        )
        previous = conn.execute(
            "SELECT value FROM snapshot_meta WHERE key='generated_at'"
        ).fetchone()
        if previous and previous[0] == generated_at:
            count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            return {
                "database": str(db_path),
                "generated_at": generated_at,
                "article_count": int(count),
                "refreshed": False,
            }

        conn.execute("DELETE FROM articles")
        conn.executemany(
            """
            INSERT INTO articles(
              article_key, industry_key, industry_name, subindustry_name,
              title, chinese_title, source, published_at, timestamp, url, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["article_key"], item["industry_key"], item["industry_name"],
                    item["subindustry_name"], item["title"], item["chinese_title"],
                    item["source"], item["published_at"], item["timestamp"],
                    item["url"], item["summary"],
                )
                for item in articles
            ],
        )
        conn.execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('generated_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (generated_at,),
        )
        conn.commit()
        return {
            "database": str(db_path),
            "generated_at": generated_at,
            "article_count": len(articles),
            "refreshed": True,
        }
    finally:
        conn.close()


def _flatten_articles(data: dict) -> list[dict]:
    items = []
    for industry in data.get("industries", []):
        industry_key = str(industry.get("key") or "")
        industry_name = str(industry.get("name") or industry_key)
        for index, item in enumerate(industry.get("items", [])):
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            source = str(item.get("source") or "").strip()
            article_key = str(item.get("article_key") or "").strip()
            if not article_key:
                article_key = f"{industry_key}:{source}:{url}:{title}:{index}"
            items.append({
                "article_key": article_key,
                "industry_key": industry_key,
                "industry_name": industry_name,
                "subindustry_name": str(item.get("subindustry_name") or ""),
                "title": title,
                "chinese_title": str(item.get("zh") or "").strip(),
                "source": source,
                "published_at": str(item.get("time") or ""),
                "timestamp": _int_timestamp(item.get("ts")),
                "url": url,
                "summary": str(item.get("summary") or "").strip(),
            })
    return items


def _int_timestamp(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
