import argparse
import copy
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")
DEFAULT_TIMEOUT = 15
MAX_ATTEMPTS = 3
MAX_FEED_BYTES = 2 * 1024 * 1024


CANDIDATES = [
    {
        "name": "OpenAI",
        "hint": "ai",
        "type": "rss",
        "url": "https://openai.com/news/rss.xml",
    },
    {
        "name": "NASA",
        "hint": "space",
        "type": "rss",
        "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    },
]


TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "fbclid",
    "gclid",
}


def now_iso():
    # now_iso（生成统一的检查时间）
    return datetime.now(BEIJING).isoformat(
        timespec="seconds"
    )


def normalize_url(url):
    # normalize_url（生成用于重复检测的规范化地址）
    parts = urlsplit((url or "").strip())

    query = [
        (key, value)
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if key.lower() not in TRACKING_KEYS
    ]

    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path,
        urlencode(query),
        "",
    ))


def local_name(tag):
    # local_name（去掉 XML 命名空间）
    return tag.split("}")[-1]


def check_liveness(source, timeout=DEFAULT_TIMEOUT):
    # check_liveness（真实检查 RSS 或 Atom 信息源）
    request = urllib.request.Request(
        source["url"],
        headers={
            "User-Agent": "investment-news-source-checker/1.0",
            "Accept": "application/rss+xml,application/atom+xml,application/xml",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_FEED_BYTES + 1)

    if len(raw) > MAX_FEED_BYTES:
        raise ValueError("响应超过大小限制")

    root = ET.fromstring(raw)
    entries = sum(
        1
        for element in root.iter()
        if local_name(element.tag) in {"item", "entry"}
    )

    if entries == 0:
        raise ValueError("没有找到 RSS 或 Atom 条目")

    return {
        "ok": True,
        "entries": entries,
    }


def inspect_source(
    source,
    checker=check_liveness,
    attempts=MAX_ATTEMPTS,
    checked_at=None,
):
    # inspect_source（检查单个源并保留重试记录）
    errors = []
    checked_at = checked_at or now_iso()

    for attempt in range(1, attempts + 1):
        try:
            result = checker(source)

            if result.get("ok"):
                return {
                    **source,
                    "status": "active",
                    "attempts": attempt,
                    "checked_at": checked_at,
                    "entries": result.get("entries", 0),
                    "error": "",
                }

            errors.append("检查器返回失败")
        except Exception as error:
            errors.append(str(error))

    return {
        **source,
        "status": "inactive",
        "review": "needs_review",
        "attempts": attempts,
        "checked_at": checked_at,
        "entries": 0,
        "error": errors[-1] if errors else "检查失败",
    }


def find_duplicate_urls(sources):
    # find_duplicate_urls（查找同一地址被重复配置的情况）
    grouped = defaultdict(list)

    for source in sources:
        grouped[normalize_url(source["url"])].append(source["name"])

    return {
        url: names
        for url, names in grouped.items()
        if len(names) > 1
    }


def build_report(
    candidates,
    checker=check_liveness,
    attempts=MAX_ATTEMPTS,
    checked_at=None,
):
    # build_report（生成活跃、失效和重复源报告）
    checked_at = checked_at or now_iso()
    duplicates = find_duplicate_urls(candidates)
    results = []

    for source in candidates:
        url = normalize_url(source["url"])

        if url in duplicates:
            results.append({
                **source,
                "status": "duplicate",
                "review": "blocked",
                "attempts": 0,
                "checked_at": checked_at,
                "entries": 0,
                "error": "同一地址被配置到多个信息源",
            })
            continue

        results.append(
            inspect_source(
                source,
                checker=checker,
                attempts=attempts,
                checked_at=checked_at,
            )
        )

    return {
        "checked_at": checked_at,
        "total": len(results),
        "active": [
            source
            for source in results
            if source["status"] == "active"
        ],
        "inactive": [
            source
            for source in results
            if source["status"] == "inactive"
        ],
        "duplicates": duplicates,
        "results": results,
    }


def load_config(path=None):
    # load_config（读取当前正式配置）
    path = Path(path or ROOT / "sources.json")
    return json.loads(path.read_text(encoding="utf-8"))


def build_proposed_config(current_config, report):
    # build_proposed_config（生成等待人工确认的新配置）
    if report["duplicates"]:
        raise ValueError("存在重复信息源，不能生成配置")

    current_sources = current_config.get("sources", [])
    current_by_url = {
        normalize_url(source["url"]): source
        for source in current_sources
    }

    proposed_by_url = dict(current_by_url)

    for source in report["active"]:
        proposed_by_url[normalize_url(source["url"])] = {
            "name": source["name"],
            "hint": source["hint"],
            "type": source.get("type", "rss"),
            "url": source["url"],
        }

    proposed = copy.deepcopy(current_config)
    proposed["sources"] = list(proposed_by_url.values())
    proposed["maintenance"] = {
        "checked_at": report["checked_at"],
        "pending_review": [
            source["name"]
            for source in report["inactive"]
        ],
    }

    return proposed


def source_diff(old_config, new_config):
    # source_diff（生成配置变更清单）
    old = {
        normalize_url(source["url"]): source
        for source in old_config.get("sources", [])
    }
    new = {
        normalize_url(source["url"]): source
        for source in new_config.get("sources", [])
    }

    return {
        "added": [
            source
            for url, source in new.items()
            if url not in old
        ],
        "removed": [
            source
            for url, source in old.items()
            if url not in new
        ],
        "retained": [
            source
            for url, source in new.items()
            if url in old
        ],
    }


def write_config(config, path, approved=False):
    # write_config（人工确认后原子替换正式配置）
    if not approved:
        raise PermissionError("没有人工确认，不能写入正式配置")

    path = Path(path)
    temporary_path = Path(str(path) + ".candidate")
    payload = json.dumps(config, ensure_ascii=False, indent=2)

    temporary_path.write_text(payload + "\n", encoding="utf-8")
    os.replace(temporary_path, path)


def main():
    # main（检查候选源并按需生成配置）
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approve",
        action="store_true",
        help="确认后写入正式 sources.json",
    )
    args = parser.parse_args()

    current_config = load_config()
    report = build_report(CANDIDATES)

    print(json.dumps(report, ensure_ascii=False, indent=2))

    proposed = build_proposed_config(current_config, report)
    print(json.dumps(
        source_diff(current_config, proposed),
        ensure_ascii=False,
        indent=2,
    ))

    if args.approve:
        write_config(
            proposed,
            ROOT / "sources.json",
            approved=True,
        )
        print("已人工确认，正式配置已更新")
    else:
        print("当前只是检查和预览，没有修改正式配置")


if __name__ == "__main__":
    main()
