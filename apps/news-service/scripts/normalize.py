import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "fbclid",
    "gclid",
}
# TRACKING_KEYS（需要从链接中去除的跟踪参数）


def normalize_url(url):
    # normalize_url（生成用于去重的规范化链接）
    if not url:
        return ""

    value = url.strip()
    parts = urlsplit(value)

    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_KEYS
    ]

    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path,
        urlencode(query),
        "",
    ))


def normalize_title(title):
    # normalize_title（生成用于去重的规范化标题）
    return re.sub(r"\s+", " ", (title or "").strip()).casefold()


def is_redline(item, keywords):
    # is_redline（判断新闻是否命中过滤词）
    text = " ".join([
        item.get("title", ""),
        item.get("summary", ""),
    ]).casefold()

    return any(
        str(keyword).casefold() in text
        for keyword in keywords
    )


def safe_timestamp(item):
    # safe_timestamp（安全读取时间戳）
    try:
        return int(item.get("ts") or 0)
    except (TypeError, ValueError):
        return 0


def normalize_items(
    items,
    recent_days=7,
    redline_keywords=(),
    now_ts=None,
    future_tolerance_seconds=0,
):
    # normalize_items（完成过滤、去重和排序）
    if now_ts is None:
        import time
        now_ts = int(time.time())

    cutoff = now_ts - recent_days * 24 * 60 * 60
    result = []
    seen = set()

    for item in items:
        title = item.get("title", "").strip()

        if not title:
            continue

        if is_redline(item, redline_keywords):
            continue

        timestamp = safe_timestamp(item)

        if timestamp and timestamp < cutoff:
            continue

        # Future-dated feed entries must not appear in the live list.
        if timestamp and timestamp > now_ts + future_tolerance_seconds:
            continue

        url_key = normalize_url(item.get("url", ""))

        if url_key:
            unique_key = "url:" + url_key
        else:
            source = item.get("source", "").strip().casefold()
            unique_key = "title:" + source + ":" + normalize_title(title)

        if unique_key in seen:
            continue

        seen.add(unique_key)
        result.append(dict(item))

    result.sort(
        key=safe_timestamp,
        reverse=True,
    )

    return result
