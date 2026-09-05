import json
import inspect
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlsplit
# datetime、timezone（用于生成带时区的数据生成时间）

from fetch_one import fetch_one
from feed_parser import BEIJING
# fetch_one（单个信息源抓取函数）

from normalize import normalize_items
# normalize_items（新闻归一化、过滤、去重和排序函数）

from data_store import write_data_file
# write_data_file（校验后原子写入网页数据）


HERE = os.path.dirname(os.path.abspath(__file__))
# HERE（当前脚本所在目录）

ROOT = os.path.dirname(HERE)
# ROOT（项目根目录）

MAX_WORKERS = 8
# MAX_WORKERS（最大并发数；减少 106 个信息源的整体等待时间）
# 原项目正式配置包含 106 个信息源；保留余量用于后续维护，但仍限制配置规模。
MAX_SOURCES = 150
MAX_ITEMS_PER_INDUSTRY = 500
MAX_REDLINE_KEYWORDS = 100
MAX_KEYWORD_LENGTH = 64
ALLOWED_CONFIG_KEYS = {
    "_comment",
    "fetch",
    "redline_keywords",
    "industries",
    "sources",
}
ALLOWED_FETCH_KEYS = {"per_source", "timeout", "recent_days"}
ALLOWED_INDUSTRY_KEYS = {"key", "name", "accent"}
ALLOWED_SOURCE_KEYS = {"name", "hint", "type", "url"}


def _bounded_int(value, name, minimum, maximum):
    # _bounded_int（校验有范围的整数配置）
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("{} 必须是整数".format(name))
    if not minimum <= value <= maximum:
        raise ValueError("{} 必须在 {} 到 {} 之间".format(name, minimum, maximum))
    return value


def validate_config(config):
    # validate_config（校验抓取配置和资源上限）
    if not isinstance(config, dict):
        raise ValueError("sources.json 顶层必须是对象")

    unknown = set(config) - ALLOWED_CONFIG_KEYS
    if unknown:
        raise ValueError("sources.json 存在未知字段：" + ", ".join(sorted(unknown)))

    fetch_config = config.get("fetch", {})
    if not isinstance(fetch_config, dict):
        raise ValueError("fetch 必须是对象")

    unknown = set(fetch_config) - ALLOWED_FETCH_KEYS
    if unknown:
        raise ValueError("fetch 存在未知字段：" + ", ".join(sorted(unknown)))

    _bounded_int(fetch_config.get("per_source", 5), "per_source", 1, 50)
    _bounded_int(fetch_config.get("timeout", 20), "timeout", 1, 600)
    _bounded_int(fetch_config.get("recent_days", 7), "recent_days", 1, 365)

    industries = config.get("industries", [])
    if not isinstance(industries, list) or not industries:
        raise ValueError("industries 必须是非空数组")

    industry_keys = set()
    for industry in industries:
        if not isinstance(industry, dict):
            raise ValueError("行业配置必须是对象")
        unknown = set(industry) - ALLOWED_INDUSTRY_KEYS
        if unknown:
            raise ValueError("行业配置存在未知字段：" + ", ".join(sorted(unknown)))
        for field in ("key", "name", "accent"):
            if not isinstance(industry.get(field), str) or not industry[field].strip():
                raise ValueError("行业字段 {} 必须是非空文本".format(field))
        if industry["key"] in industry_keys:
            raise ValueError("行业 key 不能重复：" + industry["key"])
        industry_keys.add(industry["key"])

    sources = config.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources 必须是数组")
    if len(sources) > MAX_SOURCES:
        raise ValueError("sources 不能超过 {} 个".format(MAX_SOURCES))

    seen_urls = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("信息源配置必须是对象")
        unknown = set(source) - ALLOWED_SOURCE_KEYS
        if unknown:
            raise ValueError("信息源配置存在未知字段：" + ", ".join(sorted(unknown)))
        for field in ("name", "hint", "type", "url"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                raise ValueError("信息源字段 {} 必须是非空文本".format(field))
        if source["hint"] not in industry_keys:
            raise ValueError("信息源 hint 不对应任何行业：" + source["hint"])
        parts = urlsplit(source["url"])
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("信息源 URL 必须是 http 或 https")
        normalized_url = source["url"].strip().lower().split("#", 1)[0]
        if normalized_url in seen_urls:
            raise ValueError("信息源 URL 不能重复：" + source["url"])
        seen_urls.add(normalized_url)

    keywords = config.get("redline_keywords", [])
    if not isinstance(keywords, list) or len(keywords) > MAX_REDLINE_KEYWORDS:
        raise ValueError("redline_keywords 数量超出限制")
    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword.strip() or len(keyword) > MAX_KEYWORD_LENGTH:
            raise ValueError("过滤词必须是长度不超过 {} 的非空文本".format(MAX_KEYWORD_LENGTH))

    return config


def load_config():
    # load_config（读取信息源配置）
    path = os.path.join(ROOT, "sources.json")

    with open(path, encoding="utf-8") as file:
        return validate_config(json.load(file))


def fetch_source(args):
    # fetch_source（抓取一个配置中的信息源）
    source, per_source, timeout = args

    try:
        fetch_parameters = inspect.signature(fetch_one).parameters
        if "timeout" in fetch_parameters:
            items = fetch_one(
                source["url"],
                source["name"],
                timeout=timeout,
            )
        else:
            # Keep simple two-argument test doubles and older integrations working.
            items = fetch_one(source["url"], source["name"])

        return {
            "name": source["name"],
            "hint": source["hint"],
            "ok": True,
            "items": items[:per_source],
            "error": "",
        }

    except Exception as error:
        return {
            "name": source["name"],
            "hint": source["hint"],
            "ok": False,
            "items": [],
            "error": str(error)[:160],
        }


def build_result(config):
    # build_result（构建按行业分组的结果）
    fetch_config = config.get("fetch", {})
    per_source = int(fetch_config.get("per_source", 5))
    timeout = int(fetch_config.get("timeout", 20))
    recent_days = int(fetch_config.get("recent_days", 7))
    redline_keywords = config.get("redline_keywords", [])
    sources = config.get("sources", [])

    industries = {}

    for industry in config.get("industries", []):
        industries[industry["key"]] = {
            "key": industry["key"],
            "name": industry["name"],
            "accent": industry["accent"],
            "total": 0,
            "items": [],
            "sources": [],
        }

    tasks = [
        (source, per_source, timeout)
        for source in sources
    ]

    worker_count = min(MAX_WORKERS, max(1, len(tasks)))

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = list(pool.map(fetch_source, tasks))

    for result in results:
        industry = industries.get(result["hint"])

        if industry is None:
            continue

        industry["total"] += 1
        industry["sources"].append({
            "name": result["name"],
            "ok": result["ok"],
            "error": result["error"],
        })
        industry["items"].extend(result["items"])

        if len(industry["items"]) > MAX_ITEMS_PER_INDUSTRY:
            industry["items"] = industry["items"][:MAX_ITEMS_PER_INDUSTRY]

    for industry in industries.values():
        industry["items"] = normalize_items(
            industry["items"],
            recent_days=recent_days,
            redline_keywords=redline_keywords,
        )

    return {
        "industries": list(industries.values()),
        "sources": results,
    }


def build_web_data(config, result):
    # build_web_data（把抓取结果组装成网页数据契约）
    recent_days = int(config.get("fetch", {}).get("recent_days", 7))

    industries = []

    for industry in result["industries"]:
        industries.append({
            "key": industry["key"],
            "name": industry["name"],
            "accent": industry["accent"],
            "total": industry["total"],
            "items": industry["items"],
            "points": [],
        })

    total_sources = sum(
        industry["total"]
        for industry in industries
    )

    total_items = sum(
        len(industry["items"])
        for industry in industries
    )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(
            BEIJING
        ).isoformat(timespec="seconds"),
        "recent_days": recent_days,
        "industries": industries,
        "stats": {
            "industries": len(industries),
            "total_sources": total_sources,
            "total_items": total_items,
        },
        "has_ai": False,
    }


def main():
    # main（程序入口）
    config = load_config()
    result = build_result(config)

    failed_sources = [
        source
        for source in result["sources"]
        if not source["ok"]
    ]

    source_count = len(result["sources"])

    if source_count and len(failed_sources) == source_count:
        print("抓取阶段失败：全部 {} 个信息源未成功".format(source_count))
        raise SystemExit(2)

    data = build_web_data(config, result)

    data_path = os.path.join(ROOT, "data.js")
    write_data_file(data, data_path)

    print("已生成网页数据文件：", data_path)

    if failed_sources:
        print(
            "警告：{} 个信息源未成功，已使用其余信息源生成数据".format(
                len(failed_sources)
            )
        )


if __name__ == "__main__":
    main()
