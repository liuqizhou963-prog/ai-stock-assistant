import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data.js")

# 确保 scripts 目录可导入
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.data_store import load_data_file  # noqa: E402
from .article_index import make_article_key    # noqa: E402

_cache: list = []
_cache_lock = threading.Lock()

_SUBINDUSTRY_RULES = (
    ("储能", ("储能", "电化学储能", "液流电池")),
    ("光伏", ("光伏", "硅料", "组件", "逆变器")),
    ("风电", ("风电", "海风", "风机")),
    ("锂电池", ("锂电", "电池", "正极", "负极", "电解液")),
    ("充电桩", ("充电桩", "充换电")),
    ("大模型", ("大模型", "LLM", "生成式AI", "生成式 AI")),
    ("芯片", ("芯片", "半导体", "晶圆", "封装", "HBM")),
    ("机器人", ("机器人", "人形机器人", "机械臂")),
)


def _subindustry(text):
    for name, keywords in _SUBINDUSTRY_RULES:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return name
    return ""


def reload_articles(path=None):
    # reload_articles（从 data.js 重新加载文章进内存缓存，返回文章总数）
    global _cache
    path = path or DATA_PATH
    if not os.path.exists(path):
        return 0
    try:
        data = load_data_file(path)
    except Exception:
        return 0

    articles = []
    for industry in data.get("industries", []):
        ikey = industry.get("key", "")
        iname = industry.get("name", "")
        for item in industry.get("items", []):
            article = dict(item)
            article["industry_key"] = ikey
            article["industry_name"] = iname
            # 生成文章唯一键，供推荐打分时比对已收藏文章（规划 §5.1）
            article["article_key"] = make_article_key(
                item.get("url", ""),
                item.get("source", ""),
                item.get("title", ""),
            )
            article["content_text"] = " ".join(
                filter(None, [
                    ikey, iname,
                    item.get("title", ""),
                    item.get("zh", ""),
                    item.get("summary", ""),
                    item.get("source", ""),
                ])
            )
            article["subindustry_name"] = _subindustry(article["content_text"])
            articles.append(article)

    # Keep every consumer's default view aligned with publication time.
    articles.sort(key=lambda item: item.get("ts", 0) or 0, reverse=True)

    with _cache_lock:
        _cache = articles
    return len(articles)


def get_articles() -> list:
    # get_articles（返回当前内存缓存中的文章列表副本）
    with _cache_lock:
        return list(_cache)


def freshness_score(ts: int) -> int:
    # freshness_score（24h 内满分 5 分，之后每 12h 减 1 分，最低 0 分；规划 §5.4）
    if not ts:
        return 0
    age_hours = (time.time() - ts) / 3600
    return max(0, 5 - int(age_hours / 12))


def search_articles(
    keywords: list,
    industry_key: str = None,
    saved_keys: set = None,
    limit: int = 12,
) -> list:
    # search_articles（关键词打分排序，返回 Top limit 条候选文章；规划 §8.2）
    if not keywords:
        return []

    saved_keys = saved_keys or set()
    articles = get_articles()
    scored = []

    for article in articles:
        if industry_key and article.get("industry_key") != industry_key:
            continue

        title_text = (
            article.get("title", "") + " " + article.get("zh", "")
        ).lower()
        summary_text = article.get("summary", "").lower()

        kw_score = 0
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in title_text:
                kw_score += 3   # 标题命中 +3
            if kw_lower in summary_text:
                kw_score += 1   # 摘要命中 +1

        # 只有命中至少一个关键词，才计入候选；新鲜度仅作排序加权
        if kw_score > 0:
            score = kw_score + freshness_score(article.get("ts", 0))
            # 已收藏相似主题命中 +2（规划 §8.2）
            if article.get("article_key") in saved_keys:
                score += 2
            scored.append((score, article))

    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored[:limit]]
