"""
查询改写 + 多路检索合并
LLM 将用户问题改写为 2-3 个不同角度的检索词，
分别检索后合并去重，提升文章召回率。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.llm import call as _llm_call, load_config, LLMError  # noqa: E402
from .article_cache import search_articles                          # noqa: E402
from .article_index import list_saved_article_keys                 # noqa: E402
from .recommender import extract_keywords, keywords_from_memories  # noqa: E402

_REWRITE_SYSTEM = """你是一个搜索词生成助手。
将用户的问题改写为2-3个不同角度的中文检索词组，每行一个，直接输出检索词，不要编号或解释。
检索词要覆盖不同的表达方式和相关概念，帮助找到更多相关文章。

示例：
输入：AI算力受政策影响大吗
输出：
AI算力 政策监管 限制
GPU出口管制 半导体设备
算力基础设施 国家政策 补贴"""


def rewrite_queries(message: str, root: str = None) -> list:
    """
    用 LLM 把用户问题改写成多个检索角度。
    返回列表：[原始消息, 改写1, 改写2, ...]
    LLM 失败时只返回原始消息。
    """
    root = root or ROOT
    try:
        config = load_config(root)
        raw = _llm_call(_REWRITE_SYSTEM, message, config=config)
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        return [message] + lines[:3]
    except (LLMError, Exception):
        return [message]


def recommend_with_rewrite(
    user_message: str,
    memories: list = None,
    industry_key: str = None,
    limit: int = 12,
    root: str = None,
) -> list:
    """
    查询改写 + 多路检索 + 合并去重 + 打分排序。
    替代 recommender.recommend()，在 news_query 意图时使用。
    """
    memories = memories or []
    root = root or ROOT

    # 获取已收藏文章键（用于打分加权）
    try:
        saved_keys = list_saved_article_keys()
    except Exception:
        saved_keys = set()

    # 生成多个检索角度
    queries = rewrite_queries(user_message, root)

    # 记忆关键词（所有路共用）
    mem_kws = keywords_from_memories(memories)

    seen_keys: set = set()
    all_candidates: list = []

    for query in queries:
        msg_kws = extract_keywords(query)
        # 合并去重，消息关键词优先
        combined = list(dict.fromkeys(msg_kws + mem_kws))
        results = search_articles(
            combined,
            industry_key=industry_key,
            saved_keys=saved_keys,
            limit=limit,
        )
        for article in results:
            key = article.get("article_key") or article.get("url", "")
            if key and key not in seen_keys:
                seen_keys.add(key)
                all_candidates.append(article)

    # search_articles 已按分数排序，多路合并后截断
    return all_candidates[:limit]
