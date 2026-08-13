import hashlib
import html
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT_DIR / "config"
STATE_DIR = ROOT_DIR / "state"
DATABASE_PATH = STATE_DIR / "news.db"
TAXONOMY_PATH = CONFIG_DIR / "news-taxonomy.json"
SOURCES_PATH = CONFIG_DIR / "news-sources.json"

app = FastAPI(title="Desktop Agent Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def taxonomy_data() -> dict[str, Any]:
    return load_json(TAXONOMY_PATH)


def database() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            primary_sector TEXT NOT NULL DEFAULT '宏观与市场',
            industry TEXT NOT NULL DEFAULT '',
            topics TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_health (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            last_checked_at TEXT,
            last_success_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            item_count INTEGER NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.commit()
    return connection


def clean_text(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify(title: str, summary: str) -> tuple[str, str, list[str]]:
    text = f"{title} {summary}".lower()
    data = taxonomy_data()
    industry = ""
    primary_sector = "宏观与市场"
    for sector in data["primarySectors"]:
        for candidate in sector.get("industries", []):
            if candidate.lower() in text:
                primary_sector = sector["name"]
                industry = candidate
                break
        if industry:
            break
    for topic in data["themes"]:
        if topic.lower() in text:
            if not industry and topic in {"AI", "芯片", "算力", "消费电子"}:
                primary_sector = "科技与传媒"
            break
    topics = [topic for topic in data["themes"] if topic.lower() in text]
    if any(word in text for word in ("政策", "利率", "汇率", "央行", "市场")):
        primary_sector = "宏观与市场"
    return primary_sector, industry, topics


def news_item(title: str, summary: str, url: str, published: str, source: dict[str, Any]) -> dict[str, Any]:
    primary_sector, industry, topics = classify(title, summary)
    fingerprint = hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()
    return {
        "fingerprint": fingerprint,
        "title": title,
        "summary": summary[:500],
        "url": url,
        "source_id": source["id"],
        "source_name": source["name"],
        "published_at": published or None,
        "fetched_at": now_iso(),
        "primary_sector": primary_sector,
        "industry": industry,
        "topics": topics,
    }


def parse_feed(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(payload)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{*}entry")
    results = []
    for item in items[:50]:
        def value(*names: str) -> str:
            for name in names:
                child = item.find(name)
                if child is None:
                    child = item.find(f"{{*}}{name}")
                if child is not None and child.text:
                    return clean_text(child.text)
            return ""

        title = value("title")
        link = value("link", "guid")
        if not link:
            link_node = item.find("{*}link")
            link = link_node.attrib.get("href", "") if link_node is not None else ""
        summary = value("description", "summary", "content")
        published = value("pubDate", "published", "updated")
        if not title or not link:
            continue
        results.append(news_item(title, summary, link, published, source))
    return results


def parse_cls(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    results = []
    for item in data.get("data", {}).get("roll_data", [])[:100]:
        title = clean_text(item.get("title") or item.get("brief") or item.get("content"))
        summary = clean_text(item.get("content") or item.get("brief"))
        article_id = item.get("id")
        if not title or not article_id:
            continue
        published = ""
        if item.get("ctime"):
            published = datetime.fromtimestamp(item["ctime"], timezone.utc).isoformat()
        results.append(news_item(title, summary, f"https://www.cls.cn/detail/{article_id}", published, source))
    return results


def parse_eastmoney(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    results = []
    for item in data.get("data", {}).get("fastNewsList", [])[:100]:
        title = clean_text(item.get("title"))
        summary = clean_text(item.get("summary"))
        if not title:
            continue
        code = item.get("code", "")
        results.append(news_item(title, summary, f"https://kuaixun.eastmoney.com/news/{code}", item.get("showTime", ""), source))
    return results


def fetch_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source["format"] == "cls":
        params = {"appName": "CailianpressWeb", "os": "web", "sv": "7.7.5", "last_time": "", "refresh_type": "1", "rn": "50"}
        query = urlencode(sorted(params.items()))
        sign = hashlib.md5(hashlib.sha1(query.encode("utf-8")).hexdigest().encode("utf-8")).hexdigest()
        request = Request(f"{source['url']}?{query}&sign={sign}", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cls.cn/"})
        with urlopen(request, timeout=10) as response:
            return parse_cls(response.read(), source)
    if source["format"] == "eastmoney":
        params = {"client": "web", "biz": "web_724", "fastColumn": "102", "sortEnd": "", "pageSize": "100", "req_trace": str(uuid.uuid4())}
        request = Request(f"{source['url']}?{urlencode(params)}", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://kuaixun.eastmoney.com/"})
        with urlopen(request, timeout=10) as response:
            return parse_eastmoney(response.read(), source)
    request = Request(source["url"], headers={"User-Agent": "DesktopAgent/0.1"})
    with urlopen(request, timeout=10) as response:
        return parse_feed(response.read(), source)


def refresh_sources() -> dict[str, Any]:
    sources = load_json(SOURCES_PATH).get("sources", [])
    connection = database()
    inserted = 0
    source_results = []
    for source in sources:
        checked_at = now_iso()
        status = "ok"
        detail = ""
        items: list[dict[str, Any]] = []
        try:
            items = fetch_source(source)
            for item in items:
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO news
                    (fingerprint, title, summary, url, source_id, source_name, published_at, fetched_at, primary_sector, industry, topics)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item["fingerprint"], item["title"], item["summary"], item["url"], item["source_id"], item["source_name"], item["published_at"], item["fetched_at"], item["primary_sector"], item["industry"], json.dumps(item["topics"], ensure_ascii=False)),
                )
                inserted += cursor.rowcount
        except (OSError, URLError, ElementTree.ParseError, TimeoutError) as error:
            status = "error"
            detail = str(error)[:240]
        connection.execute(
            """INSERT INTO source_health (source_id, source_name, last_checked_at, last_success_at, status, item_count, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET last_checked_at=excluded.last_checked_at,
            last_success_at=CASE WHEN excluded.status='ok' THEN excluded.last_checked_at ELSE source_health.last_success_at END,
            status=excluded.status, item_count=excluded.item_count, detail=excluded.detail""",
            (source["id"], source["name"], checked_at, checked_at if status == "ok" else None, status, len(items), detail),
        )
        source_results.append({"id": source["id"], "name": source["name"], "status": status, "itemCount": len(items), "detail": detail})
    connection.commit()
    connection.close()
    return {"inserted": inserted, "sources": source_results, "refreshedAt": now_iso()}


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "desktop-agent-backend", "status": "ok"}


@app.get("/taxonomy")
def taxonomy() -> dict[str, Any]:
    return taxonomy_data()


@app.get("/sources")
def sources() -> list[dict[str, Any]]:
    connection = database()
    configured = load_json(SOURCES_PATH).get("sources", [])
    rows = connection.execute("SELECT * FROM source_health ORDER BY source_name").fetchall()
    connection.close()
    by_id = {row["source_id"]: dict(row) for row in rows}
    return [
        by_id.get(
            source["id"],
            {
                "source_id": source["id"],
                "source_name": source["name"],
                "status": "pending",
                "item_count": 0,
                "detail": "尚未刷新",
                "last_checked_at": None,
            },
        )
        for source in configured
    ]


@app.get("/news")
def news(
    primary_sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    connection = database()
    configured_sources = load_json(SOURCES_PATH).get("sources", [])
    source_ids = [source["id"] for source in configured_sources]
    clauses = [f"source_id IN ({','.join('?' for _ in source_ids)})"] if source_ids else ["1 = 0"]
    params: list[Any] = list(source_ids)
    if primary_sector:
        clauses.append("primary_sector = ?")
        params.append(primary_sector)
    if industry:
        clauses.append("industry = ?")
        params.append(industry)
    if topic:
        clauses.append("topics LIKE ?")
        params.append(f'%"{topic}"%')
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = connection.execute(f"SELECT COUNT(*) FROM news {where}", params).fetchone()[0]
    rows = connection.execute(
        f"SELECT * FROM news {where} ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    latest = connection.execute("SELECT MAX(fetched_at) FROM news").fetchone()[0]
    connection.close()
    items = []
    for row in rows:
        item = dict(row)
        item["topics"] = json.loads(item["topics"])
        items.append(item)
    return {"items": items, "count": len(items), "total": total, "offset": offset, "limit": limit, "updatedAt": latest}


@app.post("/refresh")
def refresh() -> dict[str, Any]:
    return refresh_sources()
