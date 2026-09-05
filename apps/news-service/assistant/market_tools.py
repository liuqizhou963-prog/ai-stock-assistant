"""Small factual market-quote adapter.

The quote endpoint is public and does not require a user API key.  It is used
only for current facts; forecasting and trading advice remain the assistant's
responsibility and are still rejected by the intent/prompt rules.
"""

import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta


QUOTE_URL = "https://hq.sinajs.cn/list={}"
SUGGEST_URL = "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key={}"
SOURCE_NAME = "新浪财经"
REQUEST_TIMEOUT = 8

DEFAULT_SYMBOLS = ["sh000001", "sz399001", "sz399006"]
ALIASES = {
    "上证": "sh000001",
    "上证指数": "sh000001",
    "沪指": "sh000001",
    "深证成指": "sz399001",
    "深成指": "sz399001",
    "创业板": "sz399006",
    "创业板指": "sz399006",
    "沪深300": "sh000300",
    "科创50": "sh000688",
    "黄金": "hf_XAU",
    "现货黄金": "hf_XAU",
    "伦敦金": "hf_XAU",
    "XAUUSD": "hf_XAU",
    "XAU": "hf_XAU",
    "白银": "hf_XAG",
    "现货白银": "hf_XAG",
    "伦敦银": "hf_XAG",
    "XAGUSD": "hf_XAG",
    "XAG": "hf_XAG",
    "原油": "hf_CL",
    "美原油": "hf_CL",
    "WTI": "hf_CL",
    "美元指数": "DINIW",
    "DXY": "DINIW",
}

_CODE_RE = re.compile(r"(?<!\d)([036]\d{5})(?!\d)")
_QUOTE_TERMS_RE = re.compile(
    r"实时|当前|今日|今天|涨跌|涨幅|跌幅|上涨|下跌|涨|跌|行情|报价|股价|价格|"
    r"大盘|指数|开盘|收盘|成交量|黄金|白银|原油|美元|XAU|XAG|WTI|DXY|gold|silver|oil|"
    r"MACD|KDJ|均线|布林|K线|历史|走势|PE|市盈率|PB|市净率|ROE|负债率|市值|财报"
)
_NOISE_RE = re.compile(
    r"请问|帮我|查询|看看|现在|当前|实时|今天|今日|涨了多少|跌了多少|涨跌|"
    r"行情|股价|价格|怎么样|如何|多少|表现|走势|历史|K线|MACD|KDJ|均线|布林|是多少|的|吗|呢"
)
_ANALYSIS_TERMS_RE = re.compile(
    r"新闻|消息|原因|为什么|为何|公告|政策|业绩|财报|资讯|报道|分析|解读|MACD|KDJ|均线|布林|K线|历史|走势|PE|市盈率|PB|市净率|ROE|负债率|市值"
)


def _request_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        raw = response.read(512 * 1024)
        text = raw.decode("utf-8", errors="replace")
        # Sina may return GBK for quote names on this legacy endpoint.
        if "\ufffd" in text:
            text = raw.decode("gb18030", errors="replace")
        return text


def _symbol_from_code(code: str) -> str:
    if code.startswith("6"):
        return "sh" + code
    return "sz" + code


def normalize_symbol(symbol: str) -> str:
    symbol = str(symbol or "").strip()
    if re.fullmatch(r"[036]\d{5}", symbol):
        return _symbol_from_code(symbol)
    return symbol.lower() if symbol.lower().startswith(("sh", "sz")) else symbol


def _resolve_by_suggest(query: str) -> str | None:
    if not query:
        return None
    try:
        url = SUGGEST_URL.format(urllib.parse.quote(query, safe=""))
        text = _request_text(url)
    except (OSError, urllib.error.URLError, TimeoutError):
        return None

    match = re.search(r'var suggestvalue="(.*?)";', text, re.DOTALL)
    if not match:
        return None
    # The fourth comma-separated field is the Sina symbol, e.g. sh600519.
    fields = match.group(1).split(",")
    if len(fields) >= 4 and re.fullmatch(r"(?:sh|sz)\d{6}", fields[3]):
        return fields[3]
    return None


def _symbols_for_message(message: str) -> list[str]:
    for alias, symbol in sorted(ALIASES.items(), key=lambda item: -len(item[0])):
        if alias in message or alias.upper() in message.upper():
            return [symbol]

    codes = [_symbol_from_code(code) for code in _CODE_RE.findall(message)]
    if codes:
        return list(dict.fromkeys(codes))[:5]

    if not _QUOTE_TERMS_RE.search(message):
        return []

    # Broad market questions should show representative major indices rather
    # than resolving words such as "大盘" as if they were a stock name.
    if re.search(r"大盘|股市|市场|A股", message):
        return list(DEFAULT_SYMBOLS)

    query = _NOISE_RE.sub(" ", message)
    query = re.sub(r"[^\w\u4e00-\u9fff]", " ", query).strip()
    query = re.sub(r"\s+", " ", query)
    if query and query not in {"市场", "股票", "股市", "A股"}:
        symbol = _resolve_by_suggest(query)
        if symbol:
            return [symbol]
    return list(DEFAULT_SYMBOLS)


def _number(value: str, digits: int = 2):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _quote_freshness(date: str, quote_time: str) -> str:
    if not date:
        return "unknown"
    try:
        quoted = datetime.strptime(
            f"{date} {quote_time or '00:00:00'}", "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone(timedelta(hours=8)))
        age = (datetime.now(timezone(timedelta(hours=8))) - quoted).total_seconds()
    except (TypeError, ValueError):
        return "unknown"
    if age < 0:
        return "future_timestamp"
    if age <= 45 * 60:
        return "intraday"
    return "latest_close"


def _parse_quote(symbol: str, text: str) -> dict | None:
    match = re.search(
        rf'var hq_str_{re.escape(symbol)}="(.*?)";', text, re.DOTALL
    )
    if not match:
        return None
    fields = match.group(1).split(",")

    if symbol.startswith("hf_"):
        # Futures/commodities use a compact format: current, bid, ask,
        # settlement, open, high, low, previous settlement, ... date, name.
        if len(fields) < 14:
            return None
        price = _number(fields[0], 4)
        previous_close = _number(fields[7], 4)
        open_price = _number(fields[4], 4)
        high = _number(fields[5], 4)
        low = _number(fields[6], 4)
        volume = None
        amount = None
        date = fields[12]
        quote_time = fields[6]
        name = fields[13]
    elif symbol == "DINIW":
        # Dollar index format: time, current, bid, previous, ... name, date.
        if len(fields) < 10:
            return None
        price = _number(fields[1], 4)
        previous_close = _number(fields[5], 4)
        open_price = None
        high = None
        low = None
        volume = None
        amount = None
        date = fields[10] if len(fields) > 10 else ""
        quote_time = fields[0]
        name = fields[9]
    else:
        if len(fields) < 32 or not fields[0]:
            return None
        previous_close = _number(fields[2], 4)
        price = _number(fields[3], 4)
        open_price = _number(fields[1], 4)
        high = _number(fields[4], 4)
        low = _number(fields[5], 4)
        volume = _number(fields[8], 0)
        amount = _number(fields[9], 2)
        date = fields[30] if len(fields) > 30 else ""
        quote_time = fields[31] if len(fields) > 31 else ""
        name = fields[0]

    if price is None or previous_close in (None, 0):
        return None

    change = round(price - previous_close, 4)
    change_pct = round(change / previous_close * 100, 2)
    return {
        "symbol": symbol,
        "name": name,
        "price": price,
        "open": open_price,
        "high": high,
        "low": low,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "amplitude_pct": round((high - low) / previous_close * 100, 2)
        if high is not None and low is not None
        else None,
        "volume": volume,
        "amount": amount,
        "date": date,
        "time": quote_time,
        "trade_date": date,
        "quote_time": quote_time,
        "source": SOURCE_NAME,
        "freshness": _quote_freshness(date, quote_time),
        "status": "available",
    }


def get_market_quotes(message: str) -> list[dict]:
    """Return current quotes relevant to a user message.

    Failures intentionally degrade to an empty list so news and knowledge
    questions continue to work when the public quote service is unavailable.
    """
    symbols = _symbols_for_message(message)
    if not symbols:
        return []
    return get_quotes_for_symbols(symbols)


def get_quotes_for_symbols(symbols: list[str]) -> list[dict]:
    normalized = []
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip()
        normalized.append(normalize_symbol(symbol))
    symbols = list(dict.fromkeys(symbol for symbol in normalized if symbol))
    if not symbols:
        return []
    try:
        text = _request_text(QUOTE_URL.format(",".join(symbols)))
    except (OSError, urllib.error.URLError, TimeoutError):
        return []
    return [quote for symbol in symbols if (quote := _parse_quote(symbol, text))]


def symbols_for_message(message: str) -> list[str]:
    """Expose the message-to-instrument resolver to research features."""
    return _symbols_for_message(message)


def is_market_only_query(message: str) -> bool:
    """Whether a request only needs factual quotes and no article/LLM analysis."""
    return bool(_symbols_for_message(message)) and not _ANALYSIS_TERMS_RE.search(message)


def format_market_quotes(quotes: list[dict]) -> str:
    if not quotes:
        return ""
    dates = [quote.get("trade_date") for quote in quotes if quote.get("trade_date")]
    times = [quote.get("quote_time") for quote in quotes if quote.get("quote_time")]
    as_of = f"{dates[0]} {times[0]}" if dates and times else "时间未知"
    lines = [f"### 行情快照（截至 {as_of}）", ""]
    lines.append("| 标的 | 现价 | 涨跌 | 涨跌幅 | 开盘 | 最高 | 最低 | 成交量 | 成交额 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")

    def display(value):
        if value is None:
            return "-"
        return f"{value:.4f}".rstrip("0").rstrip(".")

    for quote in quotes:
        sign = "+" if quote["change"] >= 0 else ""
        lines.append(
            f"| {quote['name']} ({quote['symbol']}) | {display(quote.get('price'))} | "
            f"{sign}{display(quote.get('change'))} | {sign}{quote.get('change_pct', 0):.2f}% | "
            f"{display(quote.get('open'))} | {display(quote.get('high'))} | "
            f"{display(quote.get('low'))} | {display(quote.get('volume'))} | "
            f"{display(quote.get('amount'))} |"
        )
    rising = sum(1 for quote in quotes if quote.get("change", 0) > 0)
    falling = sum(1 for quote in quotes if quote.get("change", 0) < 0)
    flat = len(quotes) - rising - falling
    lines.extend([
        "",
        f"盘面小结：{rising} 个上涨，{falling} 个下跌，{flat} 个平盘。",
        f"数据来源：{quotes[0].get('source', SOURCE_NAME)}；交易日期：{', '.join(dict.fromkeys(dates)) or '未知'}。",
        "以上为行情事实，不代表涨跌预测或买卖建议。",
    ])
    return "\n".join(lines)
