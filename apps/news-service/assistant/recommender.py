import re

from .article_cache import search_articles
from .article_index import list_saved_article_keys


def extract_keywords(text: str) -> list:
    # extract_keywords（按空白和常见标点切分；在 ASCII/中文边界进一步拆分；
    # 对中文段生成二元组；去重保序。例："AI市场" → ["AI市场","AI","市场"]）
    tokens = re.split(r'[\s，。？！、；：「」【】()（）""\.\,\?\!\n\r]+', text)
    seen = set()
    keywords = []

    def _add(kw):
        kw = kw.strip()
        if len(kw) >= 2 and kw not in seen:
            seen.add(kw)
            keywords.append(kw)

    for t in tokens:
        t = t.strip()
        if not t:
            continue
        _add(t)
        # 在 ASCII 与中文之间切分（"AI市场" → ["AI", "市场"]）
        parts = re.split(
            r'(?<=[A-Za-z0-9])(?=[一-鿿])|(?<=[一-鿿])(?=[A-Za-z0-9])',
            t
        )
        if len(parts) > 1:
            for p in parts:
                _add(p)
        # 对中文段生成二元组（"新能源汽车" → ["新能","能源","源汽","汽车"]）
        for seg in re.findall(r'[一-鿿]+', t):
            _add(seg)
            for i in range(len(seg) - 1):
                _add(seg[i:i + 2])

    return keywords


def keywords_from_memories(memories: list) -> list:
    # keywords_from_memories（从用户记忆的标题、内容、标签中提取关键词）
    seen = set()
    keywords = []
    for mem in memories:
        for text in (mem.get("title", ""), mem.get("content", "")):
            for kw in extract_keywords(text):
                if kw not in seen:
                    seen.add(kw)
                    keywords.append(kw)
        for tag in mem.get("tags", []):
            tag = str(tag).strip()
            if len(tag) >= 2 and tag not in seen:
                seen.add(tag)
                keywords.append(tag)
    return keywords


def recommend(
    user_message: str,
    memories: list = None,
    industry_key: str = None,
    limit: int = 12,
) -> list:
    # recommend（合并消息关键词和记忆关键词，加载已收藏文章键，检索相关文章；规划 §8.1）
    memories = memories or []
    msg_kws = extract_keywords(user_message)
    mem_kws = keywords_from_memories(memories)

    seen = set()
    all_kws = []
    for kw in msg_kws + mem_kws:
        if kw not in seen:
            seen.add(kw)
            all_kws.append(kw)

    # 读取已收藏文章键，用于推荐打分 +2（规划 §8.2）
    # DB 不可用时降级为空集，不影响基础检索
    try:
        saved_keys = list_saved_article_keys()
    except Exception:
        saved_keys = set()

    return search_articles(
        all_kws,
        industry_key=industry_key,
        saved_keys=saved_keys,
        limit=limit,
    )
