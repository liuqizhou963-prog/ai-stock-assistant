"""Deterministic research helpers used by the assistant and research panel."""

import re
from statistics import median

from . import fundamentals
from . import market_tools


_CODE_RE = re.compile(r"(?<!\d)([036]\d{5})(?!\d)")


def extract_symbols(text: str) -> list[str]:
    values = re.findall(r"(?i)\b(?:sh|sz)\d{6}\b", str(text or ""))
    values.extend(market_tools._symbol_from_code(code) for code in _CODE_RE.findall(str(text or "")))
    return list(dict.fromkeys(value.lower() for value in values))


def parse_screen_conditions(text: str) -> dict:
    text = str(text or "")
    conditions = {}

    def number(patterns):
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    pe_max = number([r"(?:PE|市盈率)\s*(?:不高于|低于|小于|<=?)\s*(\d+(?:\.\d+)?)"])
    if pe_max is not None:
        conditions["pe_max"] = pe_max
    elif re.search(r"低\s*PE|低市盈率|便宜", text, re.IGNORECASE):
        conditions["pe_max"] = 20.0

    roe_min = number([r"ROE\s*(?:不低于|高于|大于|>=?)\s*(\d+(?:\.\d+)?)\s*%?"])
    if roe_min is not None:
        conditions["roe_min"] = roe_min
    elif re.search(r"高\s*ROE|高净资产收益率", text, re.IGNORECASE):
        conditions["roe_min"] = 15.0

    revenue_min = number([
        r"(?:营收|营业收入)(?:增长|增速)?\s*(?:超过|高于|大于|不低于|>=?)\s*(\d+(?:\.\d+)?)\s*%?",
        r"营收增长\s*(\d+(?:\.\d+)?)\s*%?\s*(?:以上|以内)?",
    ])
    if revenue_min is not None:
        conditions["revenue_growth_min"] = revenue_min

    profit_min = number([
        r"(?:净利润|利润)(?:增长|增速)?\s*(?:超过|高于|大于|不低于|>=?)\s*(\d+(?:\.\d+)?)\s*%?",
    ])
    if profit_min is not None:
        conditions["profit_growth_min"] = profit_min

    return conditions


def is_screen_query(text: str) -> bool:
    return bool(
        re.search(r"选股|筛选|筛出|符合条件|低PE|高ROE|营收增长|净利润增长", str(text or ""), re.IGNORECASE)
    )


def _matches(snapshot: dict, conditions: dict) -> tuple[bool, list[str]]:
    checks = {
        "pe_max": (snapshot.get("pe"), lambda value, limit: value <= limit, "PE"),
        "roe_min": (snapshot.get("roe"), lambda value, limit: value >= limit, "ROE"),
        "revenue_growth_min": (snapshot.get("revenue_growth"), lambda value, limit: value >= limit, "营收增速"),
        "profit_growth_min": (snapshot.get("profit_growth"), lambda value, limit: value >= limit, "净利润增速"),
    }
    reasons = []
    for key, (value, predicate, label) in checks.items():
        if key not in conditions:
            continue
        if value is None:
            return False, [f"{label}缺失"]
        if not predicate(value, conditions[key]):
            return False, [f"{label}不满足条件"]
        reasons.append(f"{label}满足")
    return True, reasons


def screen_stocks(symbols: list[str], conditions: dict, fetcher=None) -> dict:
    fetcher = fetcher or fundamentals.get_fundamentals
    results = []
    warnings = []
    for raw_symbol in list(dict.fromkeys(symbols or []))[:30]:
        symbol = market_tools.normalize_symbol(raw_symbol)
        try:
            snapshot = fetcher(symbol)
        except (ValueError, RuntimeError, OSError) as error:
            warnings.append({"symbol": symbol, "message": str(error)})
            continue
        matched, reasons = _matches(snapshot, conditions)
        results.append({"snapshot": snapshot, "matched": matched, "reasons": reasons})
    return {
        "conditions": conditions,
        "candidates": len(results),
        "matched": [item for item in results if item["matched"]],
        "all": results,
        "warnings": warnings,
        "evidence": {
            "source": "东方财富公开财务接口",
            "scope": "用户提供的候选股票",
            "conditions": conditions,
        },
    }


def compare_snapshots(snapshots: list[dict]) -> dict:
    usable = [item for item in snapshots if item]
    peers = {}
    for item in usable:
        peers.setdefault(item.get("industry") or "未分类行业", []).append(item)
    comparison = []
    for industry, group in peers.items():
        for item in group:
            row = dict(item)
            metrics = {}
            for key in ("pe", "pb", "roe", "revenue_growth", "profit_growth"):
                values = [peer.get(key) for peer in group if isinstance(peer.get(key), (int, float))]
                value = item.get(key)
                metrics[key + "_median"] = round(median(values), 4) if values else None
                metrics[key + "_vs_median"] = (
                    round(value - metrics[key + "_median"], 4)
                    if isinstance(value, (int, float)) and metrics[key + "_median"] is not None
                    else None
                )
            row["industry"] = industry
            row["comparison"] = metrics
            comparison.append(row)
    return {
        "items": comparison,
        "peer_count": len(usable),
        "evidence": {
            "source": "东方财富公开财务接口",
            "scope": "本次提交的候选股票，按接口返回行业分组；不是全市场排名",
        },
    }


def _display(value, suffix=""):
    if value is None:
        return "-"
    return f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def format_screen_report(result: dict) -> str:
    conditions = result.get("conditions") or {}
    condition_text = "、".join(
        f"PE≤{conditions['pe_max']}" if key == "pe_max" else
        f"ROE≥{conditions['roe_min']}%" if key == "roe_min" else
        f"营收增速≥{conditions['revenue_growth_min']}%" if key == "revenue_growth_min" else
        f"净利润增速≥{conditions['profit_growth_min']}%"
        for key in ("pe_max", "roe_min", "revenue_growth_min", "profit_growth_min")
        if key in conditions
    ) or "未识别到筛选条件"
    lines = [
        "### 条件选股结果",
        f"筛选条件：{condition_text}",
        "",
        "| 股票 | 行业 | PE | ROE | 营收增速 | 净利润增速 | 结果 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in result.get("all", []):
        data = item["snapshot"]
        lines.append(
            f"| {data.get('name', '-') } ({data.get('symbol', '-')}) | {data.get('industry', '-')} | "
            f"{_display(data.get('pe'))} | {_display(data.get('roe'), '%')} | "
            f"{_display(data.get('revenue_growth'), '%')} | {_display(data.get('profit_growth'), '%')} | "
            f"{'满足' if item['matched'] else '不满足'} |"
        )
    lines.extend([
        "",
        f"结果：{len(result.get('matched', []))}/{result.get('candidates', 0)} 只满足。",
        f"证据：{result.get('evidence', {}).get('source', '-')}；范围：{result.get('evidence', {}).get('scope', '-')}。",
        "数据缺失或请求失败的候选不会被判定为满足，请结合财报日期复核。",
    ])
    return "\n".join(lines)


def format_compare_report(result: dict) -> str:
    lines = [
        "### 同行样本比较",
        "",
        "| 股票 | 行业 | PE | 行业样本中位数 | ROE | 行业样本中位数 | 营收增速 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in result.get("items", []):
        cmp = item.get("comparison", {})
        lines.append(
            f"| {item.get('name', '-')} ({item.get('symbol', '-')}) | {item.get('industry', '-')} | "
            f"{_display(item.get('pe'))} | {_display(cmp.get('pe_median'))} | "
            f"{_display(item.get('roe'), '%')} | {_display(cmp.get('roe_median'), '%')} | "
            f"{_display(item.get('revenue_growth'), '%')} |"
        )
    lines.extend([
        "",
        f"样本：{result.get('peer_count', 0)} 只股票。",
        f"证据：{result.get('evidence', {}).get('source', '-')}；{result.get('evidence', {}).get('scope', '-')}。",
    ])
    return "\n".join(lines)
