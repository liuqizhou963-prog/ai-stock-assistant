"""Best-effort public company metrics adapter."""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import httpx


URL = (
    "https://push2.eastmoney.com/api/qt/stock/get?secid={secid}"
    "&fields=f43,f57,f58,f116,f117,f127,f162,f163,f164,f167,f170"
)
FINANCE_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code={code}"
DUPONT_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/DBFXAjaxNew?code={code}"
CASHFLOW_DATES_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/xjllbDateAjaxNew?companyType=4&reportDateType=0&code={code}"
CASHFLOW_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/xjllbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={dates}&code={code}"
_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 300


def _secid(symbol):
    symbol = str(symbol or "").lower().strip()
    if symbol.startswith("sh") and symbol[2:].isdigit():
        return "1." + symbol[2:]
    if symbol.startswith("sz") and symbol[2:].isdigit():
        return "0." + symbol[2:]
    raise ValueError("只支持 sh/sz 股票代码")


def _request_json(url):
    try:
        response = httpx.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://emweb.securities.eastmoney.com/",
            },
            timeout=8,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as error:
        raise OSError("东方财富接口请求失败") from error


def get_fundamentals(symbol):
    cache_key = str(symbol or "").lower().strip()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and time.time() - cached[0] < _CACHE_TTL:
            return dict(cached[1])
    try:
        payload = _request_json(URL.format(secid=_secid(symbol)))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError("财务指标数据源暂时不可用") from error

    data = payload.get("data") or {}
    if not data:
        raise RuntimeError("没有找到该股票的财务指标")

    def number(key, scale=1):
        value = data.get(key)
        try:
            return round(float(value) * scale, 4) if value not in (None, "-") else None
        except (TypeError, ValueError):
            return None

    code = str(symbol).upper()
    try:
        finance_payload = _request_json(FINANCE_URL.format(code=code))
        finance = (finance_payload.get("data") or [None])[0] or {}
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        finance = {}

    try:
        dupont_payload = _request_json(DUPONT_URL.format(code=code))
        dupont = (dupont_payload.get("bgq") or [None])[0] or {}
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        dupont = {}

    cashflow = {}
    try:
        dates_payload = _request_json(CASHFLOW_DATES_URL.format(code=code))
        dates = [item.get("REPORT_DATE") for item in (dates_payload.get("data") or [])[:5]]
        dates = [date for date in dates if date]
        if dates:
            cashflow_payload = _request_json(
                CASHFLOW_URL.format(code=code, dates=urllib.parse.quote(",".join(dates), safe=""))
            )
            cashflow = (cashflow_payload.get("data") or [None])[0] or {}
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        cashflow = {}

    def raw(data, key):
        value = data.get(key)
        return value if isinstance(value, (int, float)) else None

    report_date = finance.get("REPORT_DATE") or dupont.get("REPORT_DATE") or cashflow.get("REPORT_DATE")
    revenue = raw(finance, "TOTALOPERATEREVE")
    profit = raw(finance, "PARENTNETPROFIT")
    roe = raw(dupont, "ROE")
    if roe is None:
        roe = raw(finance, "ROEJQ")

    result = {
        "symbol": str(symbol).lower(),
        "name": data.get("f58", ""),
        "price": number("f43", 0.01),
        "change_pct": number("f170", 0.01),
        "market_cap": number("f116"),
        "float_market_cap": number("f117"),
        "pe": number("f162", 0.01),
        "pb": number("f167", 0.01),
        "industry": data.get("f127") or "",
        "revenue": revenue,
        "revenue_growth": raw(finance, "TOTALOPERATEREVETZ"),
        "net_profit": profit,
        "profit_growth": raw(finance, "PARENTNETPROFITTZ"),
        "gross_margin": round(raw(finance, "MLR") / revenue * 100, 2)
        if raw(finance, "MLR") is not None and revenue
        else None,
        "net_margin": round(profit / revenue * 100, 2)
        if profit is not None and revenue
        else None,
        "roe": roe,
        "operating_cash_flow": raw(cashflow, "NETCASH_OPERATE"),
        "operating_cash_flow_growth": raw(cashflow, "NETCASH_OPERATE_YOY"),
        "debt_ratio": raw(dupont, "DEBT_ASSET_RATIO"),
        "report_date": report_date,
        "source": "东方财富",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "evidence": {
            "quote_endpoint": "东方财富行情接口",
            "finance_endpoint": "东方财富主要指标/杜邦/现金流接口",
            "report_date": report_date,
            "warning": "财务字段按最新可用报告期返回；缺失字段保持为空，不做推算。",
        },
    }
    with _CACHE_LOCK:
        _CACHE[cache_key] = (time.time(), dict(result))
    return result
