"""Historical candles and common technical indicators."""

import base64
import io
import json
import re
import threading
import time
import urllib.request


HISTORY_URL = (
    "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_DATA="
    "/CN_MarketDataService.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={days}"
)
_cache = {}
_cache_lock = threading.Lock()


def normalize_symbol(symbol):
    symbol = str(symbol or "").strip()
    if re.fullmatch(r"(?:sh|sz)\d{6}", symbol, re.IGNORECASE):
        return symbol.lower()
    if re.fullmatch(r"[036]\d{5}", symbol):
        return ("sh" if symbol.startswith("6") else "sz") + symbol
    raise ValueError("只支持 sh/sz 股票代码")


def fetch_candles(symbol, days=120, scale=240):
    symbol = normalize_symbol(symbol)
    days = max(30, min(int(days), 500))
    scale = max(1, min(int(scale), 240))
    key = (symbol, days, scale)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < 60:
            return [dict(item) for item in cached[1]]

    request = urllib.request.Request(
        HISTORY_URL.format(symbol=symbol, days=days, scale=scale),
        headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        text = response.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    match = re.search(r"var _DATA=\((\[.*?\])\);", text, re.DOTALL)
    if not match:
        raise RuntimeError("历史行情接口返回格式错误")
    rows = json.loads(match.group(1))
    candles = []
    for row in rows:
        try:
            candles.append({
                "day": row["day"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0)),
            })
        except (KeyError, TypeError, ValueError):
            continue
    if not candles:
        raise RuntimeError("没有找到历史行情")
    with _cache_lock:
        _cache[key] = (time.time(), candles)
    return [dict(item) for item in candles]


def _sma(values, window):
    result = []
    for index in range(len(values)):
        if index + 1 < window:
            result.append(None)
        else:
            result.append(sum(values[index + 1 - window:index + 1]) / window)
    return result


def _ema(values, window):
    result = []
    alpha = 2 / (window + 1)
    current = None
    for value in values:
        current = value if current is None else alpha * value + (1 - alpha) * current
        result.append(current)
    return result


def calculate_indicators(candles):
    closes = [item["close"] for item in candles]
    highs = [item["high"] for item in candles]
    lows = [item["low"] for item in candles]
    sma5 = _sma(closes, 5)
    sma10 = _sma(closes, 10)
    sma20 = _sma(closes, 20)
    volumes = [float(item.get("volume", 0) or 0) for item in candles]
    volume_ma5 = _sma(volumes, 5)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    gains = [0]
    losses = [0]
    for previous, current in zip(closes, closes[1:]):
        delta = current - previous
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    rsi = []
    for index in range(len(closes)):
        start = max(0, index - 13)
        avg_gain = sum(gains[start:index + 1]) / max(1, index - start + 1)
        avg_loss = sum(losses[start:index + 1]) / max(1, index - start + 1)
        rsi.append(100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))

    k_values, d_values, j_values = [], [], []
    k = d = 50.0
    for index in range(len(candles)):
        start = max(0, index - 8)
        highest = max(highs[start:index + 1])
        lowest = min(lows[start:index + 1])
        rsv = 50 if highest == lowest else (closes[index] - lowest) / (highest - lowest) * 100
        k = 2 / 3 * k + 1 / 3 * rsv
        d = 2 / 3 * d + 1 / 3 * k
        k_values.append(k)
        d_values.append(d)
        j_values.append(3 * k - 2 * d)

    upper, middle, lower = [], [], []
    for index in range(len(closes)):
        start = max(0, index - 19)
        values = closes[start:index + 1]
        mid = sum(values) / len(values) if len(values) == 20 else None
        std = (sum((value - mid) ** 2 for value in values) / 20) ** 0.5 if mid is not None else None
        middle.append(mid)
        upper.append(mid + 2 * std if mid is not None else None)
        lower.append(mid - 2 * std if mid is not None else None)

    result = []
    for index, candle in enumerate(candles):
        item = dict(candle)
        item["sma5"] = sma5[index]
        item["sma10"] = sma10[index]
        item["sma20"] = sma20[index]
        item["volume_ma5"] = volume_ma5[index]
        item["volume_ratio"] = (
            volumes[index] / volume_ma5[index]
            if volume_ma5[index]
            else None
        )
        item["dif"] = dif[index]
        item["dea"] = dea[index]
        item["macd"] = 2 * (dif[index] - dea[index])
        item["rsi14"] = rsi[index]
        item["k"] = k_values[index]
        item["d"] = d_values[index]
        item["j"] = j_values[index]
        item["boll_upper"] = upper[index]
        item["boll_mid"] = middle[index]
        item["boll_lower"] = lower[index]
        result.append(item)
    return result


def get_history(symbol, days=120, scale=240):
    candles = calculate_indicators(fetch_candles(symbol, days, scale))
    latest = candles[-1]
    return {
        "symbol": normalize_symbol(symbol),
        "days": len(candles),
        "candles": candles,
        "latest": latest,
    }


def make_chart(history):
    """Return a PNG data URL for the local research panel."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    candles = history["candles"]
    dates = [item["day"] for item in candles]
    closes = [item["close"] for item in candles]
    sma20 = [item["sma20"] for item in candles]
    fig, (price_ax, volume_ax) = plt.subplots(
        2, 1, figsize=(10, 5), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    fig.patch.set_facecolor("#0a0c10")
    for axis in (price_ax, volume_ax):
        axis.set_facecolor("#0a0c10")
        axis.tick_params(colors="#9ca3af", labelsize=8)
        for spine in axis.spines.values():
            spine.set_color("#27303c")
        axis.grid(color="#27303c", alpha=.65, linewidth=.6)
    price_ax.plot(dates, closes, color="#f59e0b", linewidth=1.8, label="Close")
    price_ax.plot(dates, sma20, color="#60a5fa", linewidth=1.1, label="MA20")
    volume_ax.bar(dates, [item["volume"] for item in candles], color="#64748b", width=.7)
    price_ax.legend(loc="upper left", fontsize=8, facecolor="#111827", labelcolor="#e5e7eb")
    price_ax.set_title(f"{history['symbol']} · {history['days']} sessions", color="#e5e7eb", fontsize=10)
    fig.autofmt_xdate()
    output = io.BytesIO()
    fig.tight_layout()
    fig.savefig(output, format="png", dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
