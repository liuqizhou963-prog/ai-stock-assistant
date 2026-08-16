from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.tools import a_stock_data_source as source


MAX_TOOL_RESULT_CHARS = 24_000
MAX_TOOL_RESULT_ITEMS = 200
DEFAULT_TIMEOUT_SECONDS = 30
CODE_PATTERN = re.compile(r"^(?:sh|sz|bj)?\d{6}(?:\.(?:sh|sz|bj))?$", re.IGNORECASE)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    source_name: str
    properties: dict[str, dict[str, Any]]
    required: tuple[str, ...]
    handler: Callable[[dict[str, Any]], Any]
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    normalizes_stock_code: bool = False

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": list(self.required),
                    "additionalProperties": False,
                },
            },
        }


def field(
    kind: str,
    description: str,
    *,
    default: Any = None,
    enum: list[Any] | None = None,
    minimum: int | float | None = None,
    maximum: int | float | None = None,
    items: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"type": kind, "description": description}
    if default is not None:
        value["default"] = default
    if enum is not None:
        value["enum"] = enum
    if minimum is not None:
        value["minimum"] = minimum
    if maximum is not None:
        value["maximum"] = maximum
    if items is not None:
        value["items"] = items
    return value


CODE = field("string", "A 股六位代码，可带 sh/sz/bj 前后缀。")
STOCK_CODES = field("array", "最多 10 个股票、指数或 ETF 代码。", items={"type": "string"}, maximum=10)
DATE = field("string", "交易日期，格式 YYYY-MM-DD。")
LIMIT = field("integer", "返回条数。", default=20, minimum=1, maximum=200)
PAGES = field("integer", "最多查询页数。", default=2, minimum=1, maximum=5)


def _tdx_bars(args: dict[str, Any]) -> Any:
    frequency = {"5m": 0, "15m": 1, "30m": 2, "60m": 3, "day": 9, "week": 5, "month": 6}[args["period"]]
    return source.tdx_client().bars(symbol=args["code"], frequency=frequency, offset=args["limit"])


def _baidu_kline_records(args: dict[str, Any]) -> list[dict[str, Any]]:
    """将百度备用源的压缩行格式转换为图表和策略可消费的记录。"""
    raw = source.baidu_kline_with_ma(args["code"])
    keys = raw.get("keys", []) if isinstance(raw, dict) else []
    rows = raw.get("rows", []) if isinstance(raw, dict) else []
    records: list[dict[str, Any]] = []
    for line in rows:
        values = str(line).split(",")
        if not keys or len(values) < len(keys):
            continue
        record: dict[str, Any] = {"date": values[keys.index("time")] if "time" in keys else ""}
        for key in ("open", "high", "low", "close", "volume", "ma5avgprice", "ma10avgprice", "ma20avgprice"):
            if key not in keys:
                continue
            value = values[keys.index(key)]
            record[key] = None if value in {"", "--"} else float(value)
        if record.get("date") and all(record.get(key) is not None for key in ("open", "high", "low", "close")):
            records.append(record)
    return records[-100:]


def _tdx_quotes(args: dict[str, Any]) -> Any:
    return source.tdx_client().quotes(symbol=[args["code"]])


def _tdx_transactions(args: dict[str, Any]) -> Any:
    return source.tdx_client().transaction(symbol=args["code"], date=args["trade_date"])


def _tdx_finance(args: dict[str, Any]) -> Any:
    return source.tdx_client().finance(symbol=args["code"])


def _tdx_f10(args: dict[str, Any]) -> Any:
    return source.tdx_client().F10(symbol=args["code"], name=args["category"])


def _latest_hint(args: dict[str, Any]) -> Any:
    return source.tdx_client().F10(symbol=args["code"], name="最新提示")


def _download_report_pdf(args: dict[str, Any]) -> Any:
    report_dir = Path(__file__).resolve().parents[4] / "state" / "agent-reports"
    return source.download_pdf(
        {
            "infoCode": args["info_code"],
            "publishDate": args["publish_date"],
            "orgSName": args["organization"],
            "title": args["title"],
        },
        target_dir=str(report_dir),
    )


def _valuation_metric(args: dict[str, Any]) -> Any:
    if args["metric"] == "forward_pe":
        return source.forward_pe(args["value1"], args["value2"])
    if args["metric"] == "peg":
        return source.calc_peg(args["value1"], args["value2"])
    return source.pe_digestion(args["value1"], args["value2"], args["target_pe"])


def _limit_pool(args: dict[str, Any]) -> Any:
    return {
        "limit_up": source.em_zt_pool,
        "open_limit": source.em_zb_pool,
        "limit_down": source.em_dt_pool,
        "yesterday_limit_up": source.em_yzt_pool,
    }[args["pool"]](args["trade_date"])


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return [_json_safe(row) for row in value.where(pd.notna(value), None).to_dict(orient="records")]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except ValueError:
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _bounded_result(value: Any) -> Any:
    normalized = _json_safe(value)
    if isinstance(normalized, list) and len(normalized) > MAX_TOOL_RESULT_ITEMS:
        normalized = normalized[:MAX_TOOL_RESULT_ITEMS]
    serialized = json.dumps(normalized, ensure_ascii=False, default=str)
    if len(serialized) > MAX_TOOL_RESULT_CHARS:
        return {"truncated": True, "preview": serialized[:MAX_TOOL_RESULT_CHARS]}
    return normalized


def _validate_value(name: str, value: Any, schema: dict[str, Any]) -> Any:
    expected = schema["type"]
    if expected == "string":
        if not isinstance(value, str):
            raise ValueError(f"参数 {name} 必须是文本")
        value = value.strip()
        if not value:
            raise ValueError(f"参数 {name} 不能为空")
        if name in {"code", "underlying"} and not CODE_PATTERN.fullmatch(value):
            raise ValueError(f"参数 {name} 必须是合法的六位证券代码")
        if "date" in name and not DATE_PATTERN.fullmatch(value):
            raise ValueError(f"参数 {name} 必须是 YYYY-MM-DD 日期")
    elif expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"参数 {name} 必须是整数")
    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"参数 {name} 必须是数字")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"参数 {name} 必须是布尔值")
    elif expected == "array":
        if not isinstance(value, list):
            raise ValueError(f"参数 {name} 必须是数组")
        if schema.get("maximum") is not None and len(value) > schema["maximum"]:
            raise ValueError(f"参数 {name} 超过最大数量")
        item_schema = schema.get("items", {})
        value = [_validate_value(f"{name}[]", item, item_schema) for item in value]
    else:
        raise ValueError(f"参数 {name} 的类型不被支持")
    if schema.get("enum") is not None and value not in schema["enum"]:
        raise ValueError(f"参数 {name} 只能使用允许的选项")
    if schema.get("minimum") is not None and value < schema["minimum"]:
        raise ValueError(f"参数 {name} 小于允许范围")
    if schema.get("maximum") is not None and not isinstance(value, list) and value > schema["maximum"]:
        raise ValueError(f"参数 {name} 超过允许范围")
    return value


def validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("工具参数必须是对象")
    unknown = set(arguments) - set(spec.properties)
    if unknown:
        raise ValueError(f"存在未允许的参数：{', '.join(sorted(unknown))}")
    validated: dict[str, Any] = {}
    for name, schema in spec.properties.items():
        if name not in arguments:
            if name in spec.required:
                raise ValueError(f"缺少必填参数：{name}")
            if "default" in schema:
                validated[name] = schema["default"]
            continue
        validated[name] = _validate_value(name, arguments[name], schema)
    if spec.normalizes_stock_code:
        validated["code"] = source.norm_ticker(validated["code"], stock_only=True)
    if "codes" in validated:
        validated["codes"] = [source.norm_ticker(code) for code in validated["codes"]]
    return validated


def _spec(
    name: str,
    description: str,
    source_name: str,
    properties: dict[str, dict[str, Any]],
    handler: Callable[[dict[str, Any]], Any],
    *,
    required: tuple[str, ...] = (),
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    normalizes_stock_code: bool = False,
) -> ToolSpec:
    return ToolSpec(name, description, source_name, properties, required, handler, timeout_seconds, normalizes_stock_code)


TOOL_SPECS = [
    _spec("get_market_quote", "获取实时行情、估值和涨跌停价。", "腾讯财经", {"codes": STOCK_CODES}, lambda a: source.tencent_quote(a["codes"]), required=("codes",)),
    _spec("get_kline", "获取不复权 K 线，支持日周月和分钟周期。", "通达信", {"code": CODE, "period": field("string", "K 线周期。", default="day", enum=["5m", "15m", "30m", "60m", "day", "week", "month"]), "limit": field("integer", "K 线根数。", default=120, minimum=1, maximum=800)}, _tdx_bars, required=("code",), normalizes_stock_code=True),
    _spec("get_order_book", "获取五档盘口报价。", "通达信", {"code": CODE}, _tdx_quotes, required=("code",), normalizes_stock_code=True),
    _spec("get_tick_transactions", "获取指定交易日逐笔成交。", "通达信", {"code": CODE, "trade_date": DATE}, _tdx_transactions, required=("code", "trade_date"), normalizes_stock_code=True),
    _spec("get_kline_with_ma", "获取日 K 线及 MA5、MA10、MA20。", "百度股市通", {"code": CODE}, _baidu_kline_records, required=("code",), normalizes_stock_code=True),
    _spec("get_stock_reports", "获取个股研报、评级和 EPS 预测。", "东方财富研报", {"code": CODE, "max_pages": PAGES}, lambda a: source.eastmoney_reports(a["code"], a["max_pages"]), required=("code",), normalizes_stock_code=True),
    _spec("download_report_pdf", "下载已确认的研报 PDF 到应用专用目录。", "东方财富 PDF", {"info_code": field("string", "研报 infoCode。"), "publish_date": field("string", "研报发布日期。", default=""), "organization": field("string", "机构名称。", default="未知机构"), "title": field("string", "研报标题。", default="研报")}, _download_report_pdf, required=("info_code",)),
    _spec("get_industry_reports", "获取行业研报。", "东方财富研报", {"industry_code": field("string", "东方财富行业代码，* 表示全部。", default="*"), "max_pages": PAGES}, lambda a: source.eastmoney_industry_reports(a["industry_code"], a["max_pages"])),
    _spec("get_eps_forecast", "获取机构一致预期 EPS。", "同花顺", {"code": CODE}, lambda a: source.ths_eps_forecast(a["code"]), required=("code",), normalizes_stock_code=True),
    _spec("search_reports", "按自然语言检索研报，需要 iwencai 配置。", "iwencai", {"query": field("string", "研报检索关键词。"), "limit": LIMIT}, lambda a: source.iwencai_search(a["query"], size=a["limit"]), required=("query",), timeout_seconds=40),
    _spec("screen_stocks", "按自然语言进行选股检索，需要 iwencai 配置。", "iwencai", {"query": field("string", "选股条件。"), "page": field("integer", "页码。", default=1, minimum=1, maximum=10), "limit": LIMIT}, lambda a: source.iwencai_query(a["query"], a["page"], a["limit"]), required=("query",), timeout_seconds=40),
    _spec("get_hot_reasons", "获取当日强势股及题材归因。", "同花顺", {"trade_date": DATE}, lambda a: source.ths_hot_reason(a["trade_date"]), required=("trade_date",)),
    _spec("get_northbound_flow", "获取沪深港通分钟资金流向。", "同花顺", {}, lambda a: source.hsgt_realtime()),
    _spec("get_concept_blocks", "获取个股所属行业、概念和地域板块。", "东方财富", {"code": CODE}, lambda a: source.eastmoney_concept_blocks(a["code"]), required=("code",), normalizes_stock_code=True),
    _spec("get_intraday_fund_flow", "获取个股分钟级资金流。", "东方财富", {"code": CODE}, lambda a: source.eastmoney_fund_flow_minute(a["code"]), required=("code",), normalizes_stock_code=True),
    _spec("get_dragon_tiger", "获取个股龙虎榜记录和买卖席位。", "东方财富", {"code": CODE, "trade_date": DATE, "look_back": field("integer", "回看天数。", default=30, minimum=1, maximum=90)}, lambda a: source.dragon_tiger_board(a["code"], a["trade_date"], a["look_back"]), required=("code", "trade_date"), normalizes_stock_code=True),
    _spec("get_lockup_expiry", "获取历史及未来限售解禁。", "东方财富", {"code": CODE, "trade_date": DATE, "forward_days": field("integer", "未来查询天数。", default=90, minimum=1, maximum=365)}, lambda a: source.lockup_expiry(a["code"], a["trade_date"], a["forward_days"]), required=("code", "trade_date"), normalizes_stock_code=True),
    _spec("get_industry_comparison", "获取行业板块涨跌排名。", "东方财富", {"top_n": LIMIT}, lambda a: source.industry_comparison(a["top_n"])),
    _spec("get_board_fund_flow", "获取行业、概念或地域板块资金流。", "东方财富", {"board_type": field("string", "板块类型。", default="industry", enum=["industry", "concept", "region"]), "period": field("string", "统计周期。", default="today", enum=["today", "5d", "10d"]), "top_n": LIMIT}, lambda a: source.board_fund_flow(a["board_type"], a["period"], a["top_n"])),
    _spec("get_daily_dragon_tiger", "获取全市场龙虎榜和净买额排名。", "东方财富", {"trade_date": DATE, "min_net_buy": field("number", "最低净买入额，单位万元。", default=0, minimum=0, maximum=1000000)}, lambda a: source.daily_dragon_tiger(a["trade_date"], a["min_net_buy"]), required=("trade_date",)),
    _spec("get_margin_trading", "获取融资融券明细。", "东方财富", {"code": CODE, "limit": LIMIT}, lambda a: source.margin_trading(a["code"], a["limit"]), required=("code",), normalizes_stock_code=True),
    _spec("get_block_trades", "获取大宗交易及买卖方营业部。", "东方财富", {"code": CODE, "limit": LIMIT}, lambda a: source.block_trade(a["code"], a["limit"]), required=("code",), normalizes_stock_code=True),
    _spec("get_holder_changes", "获取股东户数变化。", "东方财富", {"code": CODE, "limit": LIMIT}, lambda a: source.holder_num_change(a["code"], a["limit"]), required=("code",), normalizes_stock_code=True),
    _spec("get_dividends", "获取分红送转历史。", "东方财富", {"code": CODE, "limit": LIMIT}, lambda a: source.dividend_history(a["code"], a["limit"]), required=("code",), normalizes_stock_code=True),
    _spec("get_fund_flow_history", "获取个股 120 日资金流。", "东方财富", {"code": CODE}, lambda a: source.stock_fund_flow_120d(a["code"]), required=("code",), normalizes_stock_code=True),
    _spec("get_stock_news", "获取个股相关新闻。", "东方财富", {"code": CODE, "limit": LIMIT}, lambda a: source.eastmoney_stock_news(a["code"], a["limit"]), required=("code",), normalizes_stock_code=True),
    _spec("get_cls_telegraph", "获取财联社实时电报。", "财联社", {"limit": LIMIT}, lambda a: source.cls_telegraph(a["limit"])),
    _spec("get_global_news", "获取东方财富 7x24 财经快讯。", "东方财富", {"limit": LIMIT}, lambda a: source.eastmoney_global_news(a["limit"])),
    _spec("get_finance_snapshot", "获取通达信季报财务快照。", "通达信", {"code": CODE}, _tdx_finance, required=("code",), normalizes_stock_code=True),
    _spec("get_f10", "获取公司 F10 文本资料。", "通达信", {"code": CODE, "category": field("string", "F10 类别。", default="公司概况", enum=["公司概况", "股本股改", "经营分析", "财务分析", "分红扩股", "股东研究", "重大事项", "行业分析", "最新提示"])}, _tdx_f10, required=("code",), normalizes_stock_code=True),
    _spec("get_stock_info", "获取行业、股本、市值和上市日期。", "东方财富", {"code": CODE}, lambda a: source.eastmoney_stock_info(a["code"]), required=("code",), normalizes_stock_code=True),
    _spec("get_financial_statements", "获取资产负债表、利润表或现金流量表。", "新浪财经", {"code": CODE, "report_type": field("string", "报表类型。", default="lrb", enum=["lrb", "fzb", "llb"]), "periods": field("integer", "报告期数量。", default=8, minimum=1, maximum=20)}, lambda a: source.sina_financial_report(a["code"], a["report_type"], a["periods"]), required=("code",), normalizes_stock_code=True),
    _spec("get_announcements", "获取公司公告及 PDF 链接。", "巨潮资讯", {"code": CODE, "limit": LIMIT}, lambda a: source.cninfo_announcements(a["code"], a["limit"]), required=("code",), normalizes_stock_code=True),
    _spec("get_latest_announcements", "获取通达信 F10 最新公告摘要。", "通达信", {"code": CODE}, _latest_hint, required=("code",), normalizes_stock_code=True),
    _spec("get_limit_pool", "获取涨停、炸板、跌停或昨日涨停池。", "东方财富", {"pool": field("string", "池类型。", enum=["limit_up", "open_limit", "limit_down", "yesterday_limit_up"]), "trade_date": DATE}, _limit_pool, required=("pool", "trade_date")),
    _spec("get_limit_up_reasons", "获取涨停原因、题材和封板成功率。", "同花顺", {"trade_date": DATE}, lambda a: source.ths_limit_up_pool(a["trade_date"]), required=("trade_date",)),
    _spec("get_limit_up_sentiment", "获取炸板率、连板高度和连板梯队。", "东方财富", {"trade_date": DATE}, lambda a: source.limit_up_sentiment(a["trade_date"]), required=("trade_date",)),
    _spec("get_stock_monitor", "获取交易所重点监控池。", "东方财富", {"only_active": field("boolean", "是否仅返回当前有效监控。", default=True)}, lambda a: source.em_stock_monitor(a["only_active"])),
    _spec("get_price_anomalies", "获取日内严重异常波动明细。", "东方财富", {"limit": field("integer", "返回条数。", default=100, minimum=1, maximum=200), "page": field("integer", "页码。", default=1, minimum=1, maximum=5)}, lambda a: source.em_price_anomaly(a["limit"], a["page"])),
    _spec("get_price_anomaly_counts", "获取标的异常波动统计。", "东方财富", {"limit": LIMIT, "page": field("integer", "页码。", default=1, minimum=1, maximum=5)}, lambda a: source.em_price_anomaly_count(a["limit"], a["page"])),
    _spec("get_option_contracts", "获取 ETF 期权合约清单。", "新浪财经", {"underlying": field("string", "ETF 六位代码。", default="510050"), "call": field("boolean", "是否认购期权。", default=True)}, lambda a: source.sina_option_codes(a["underlying"], a["call"])),
    _spec("get_option_quote", "获取 ETF 期权 T 型报价。", "新浪财经", {"option_code": field("string", "期权合约代码。")}, lambda a: source.sina_option_tquote(a["option_code"]), required=("option_code",)),
    _spec("get_option_greeks", "获取 ETF 期权 Delta、Gamma、Theta、Vega 和 IV。", "新浪财经", {"option_code": field("string", "期权合约代码。")}, lambda a: source.sina_option_greeks(a["option_code"]), required=("option_code",)),
    _spec("get_investor_questions", "获取互动易投资者问答。", "巨潮互动易", {"code": CODE, "limit": LIMIT, "page": field("integer", "页码。", default=1, minimum=1, maximum=10)}, lambda a: source.cninfo_irm(a["code"], a["limit"], a["page"]), required=("code",), normalizes_stock_code=True),
    _spec("get_hot_rank", "获取同花顺或东方财富人气榜。", "同花顺/东方财富", {"provider": field("string", "榜单来源。", default="ths", enum=["ths", "eastmoney"]), "period": field("string", "同花顺时间窗。", default="hour", enum=["hour", "day"]), "limit": LIMIT}, lambda a: source.ths_hot_list(a["period"]) if a["provider"] == "ths" else source.em_hot_rank(a["limit"])),
    _spec("get_hot_concepts", "获取个股热门概念命中和热度。", "东方财富", {"code": CODE}, lambda a: source.em_hot_concept(a["code"]), required=("code",), normalizes_stock_code=True),
    _spec("get_full_valuation", "获取单股估值全景：市值、PE、PB、预测 EPS 和 PEG。", "腾讯财经/同花顺", {"code": CODE}, lambda a: source.full_valuation(a["code"]), required=("code",), normalizes_stock_code=True),
    _spec("calculate_valuation_metric", "计算前向 PE、PEG 或 PE 消化时间。", "本地计算", {"metric": field("string", "计算指标。", enum=["forward_pe", "peg", "pe_digestion"]), "value1": field("number", "当前价格或 PE。"), "value2": field("number", "预测 EPS 或 CAGR。"), "target_pe": field("number", "目标 PE。", default=30, minimum=1, maximum=200)}, _valuation_metric, required=("metric", "value1", "value2")),
    _spec("get_dragon_tiger_backup", "在主源不可用时获取沪深交易所官方龙虎榜备胎。", "上交所/深交所", {"trade_date": DATE}, lambda a: source.dragon_tiger_backup(a["trade_date"]), required=("trade_date",)),
    _spec("get_fund_flow_backup", "在主源不可用时获取新浪日度资金流备胎。", "新浪财经", {"code": CODE, "days": field("integer", "查询天数。", default=60, minimum=1, maximum=120)}, lambda a: source.fund_flow_backup(a["code"], a["days"]), required=("code",), normalizes_stock_code=True),
    _spec("get_announcements_backup", "在主源不可用时获取交易所/东方财富公告备胎。", "深交所/东方财富", {"code": CODE, "limit": LIMIT}, lambda a: source.announcements_backup(a["code"], a["limit"]), required=("code",), normalizes_stock_code=True),
]

TOOLS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


def tool_definitions() -> list[dict[str, Any]]:
    return [spec.definition() for spec in TOOL_SPECS]


def run_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = TOOLS_BY_NAME.get(name)
    if not spec:
        return {"tool": name, "status": "rejected", "error": "工具不在允许列表中", "updatedAt": datetime.now(timezone.utc).isoformat()}
    try:
        validated = validate_arguments(spec, arguments)
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(spec.handler, validated)
            result = future.result(timeout=spec.timeout_seconds)
        finally:
            # HTTP clients in the source module have their own timeouts. Do not
            # keep this request waiting when a tool has already timed out.
            executor.shutdown(wait=False, cancel_futures=True)
        return {"tool": spec.name, "status": "success", "source": spec.source_name, "updatedAt": datetime.now(timezone.utc).isoformat(), "data": _bounded_result(result)}
    except FutureTimeout:
        return {"tool": spec.name, "status": "timeout", "source": spec.source_name, "error": f"调用超过 {spec.timeout_seconds} 秒", "updatedAt": datetime.now(timezone.utc).isoformat()}
    except (ValueError, KeyError) as error:
        if isinstance(error, json.JSONDecodeError):
            return {"tool": spec.name, "status": "error", "source": spec.source_name, "error": "数据源返回格式异常，请稍后重试", "updatedAt": datetime.now(timezone.utc).isoformat()}
        return {"tool": spec.name, "status": "invalid_arguments", "source": spec.source_name, "error": str(error), "updatedAt": datetime.now(timezone.utc).isoformat()}
    except Exception:
        return {"tool": spec.name, "status": "error", "source": spec.source_name, "error": "数据源暂时不可用，请稍后重试", "updatedAt": datetime.now(timezone.utc).isoformat()}
