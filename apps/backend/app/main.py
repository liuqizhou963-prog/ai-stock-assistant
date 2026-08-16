import hashlib
import html
import json
import math
import os
import re
import sqlite3
import threading
import time
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Any, Generator, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from app.tools.a_stock_tools import run_tool, tool_definitions

ROOT_DIR = Path(os.getenv("DESKTOP_AGENT_ROOT", Path(__file__).resolve().parents[3])).resolve()
CONFIG_DIR = Path(os.getenv("DESKTOP_AGENT_CONFIG_DIR", ROOT_DIR / "config")).resolve()
STATE_DIR = Path(os.getenv("DESKTOP_AGENT_STATE_DIR", ROOT_DIR / "state")).resolve()
DATABASE_PATH = STATE_DIR / "news.db"
APP_DATABASE_PATH = STATE_DIR / "app.db"
TAXONOMY_PATH = CONFIG_DIR / "news-taxonomy.json"
SOURCES_PATH = CONFIG_DIR / "news-sources.json"

# Lower values win when several providers report the same event. Official
# disclosures remain available while syndication feeds serve as a fallback.
SOURCE_PRIORITY_BY_CATEGORY = {
    "交易所公告": 10,
    "公司公告": 10,
    "宏观政策": 10,
    "宏观数据": 10,
    "行业研报": 20,
    "个股研报": 20,
    "个股资讯": 30,
    "全球市场": 40,
    "实时快讯": 40,
    "财经资讯": 50,
}
SIMILAR_NEWS_WINDOW_SECONDS = 8 * 60 * 60
SIMILAR_NEWS_MIN_RATIO = 0.86

app = FastAPI(title="Desktop Agent Backend")
app.add_middleware(
    CORSMiddleware,
    # The API only binds to loopback, but the renderer may use any Vite port in
    # development or the file:// origin after Electron is packaged.
    allow_origin_regex=r"^(null|file://|http://localhost:\d+|http://127\.0\.0\.1:\d+)$",
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


class ConversationCreate(BaseModel):
    title: str = "未命名研究对话"


class MessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: str


ChatProvider = Literal["deepseek", "openai", "claude"]


class ChatRequest(BaseModel):
    content: str
    model: ChatProvider = "deepseek"


class PreferenceCreate(BaseModel):
    label: str
    value: str


class PreferenceUpdate(BaseModel):
    label: str
    value: str


class WatchlistCreate(BaseModel):
    code: str
    name: str = ""


class WorkbenchQuery(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}


class StrategyRule(BaseModel):
    field: Literal["open", "high", "low", "close", "price", "volume", "ma5", "ma10", "ma20", "volume_ma5"]
    operator: Literal["gt", "gte", "lt", "lte", "cross_up", "cross_down"]
    value: float | None = None
    compare_field: Literal["open", "high", "low", "close", "price", "volume", "ma5", "ma10", "ma20", "volume_ma5"] | None = None


class BacktestRequest(BaseModel):
    code: str
    strategy_name: str = "自定义策略"
    period: Literal["day", "week", "month"] = "day"
    limit: int = 360
    rules: list[StrategyRule]
    exit_rule: StrategyRule | None = None
    exit_after_bars: int = 10
    initial_capital: float = 100000
    position_pct: float = 0.95
    commission_rate: float = 0.00025
    stamp_duty_rate: float = 0.001
    slippage_rate: float = 0.005
    take_profit_pct: float | None = None
    stop_loss_pct: float | None = None


class BacktestReportRequest(BaseModel):
    backtest: BacktestRequest


class NewsReadUpdate(BaseModel):
    is_read: bool = True


class NewsSubscriptionCreate(BaseModel):
    keyword: str


class DataManagementUpdate(BaseModel):
    automatic_backup: Literal["off", "daily", "weekly"]


class AlertCreate(BaseModel):
    code: str
    name: str = ""
    field: str = "price"
    operator: Literal["gt", "gte", "lt", "lte"] = "gte"
    value: float
    enabled: bool = True


class StrategyCreate(BaseModel):
    name: str
    type: Literal["selection", "timing", "risk", "review", "custom"] = "custom"
    code: str
    field: Literal["price", "pct"] = "price"
    operator: Literal["gt", "gte", "lt", "lte"] = "gte"
    value: float = 0
    mode: Literal["weighted", "veto", "consensus"] = "weighted"
    weight: float = 1
    conditions: list["ManagedStrategyCondition"] = []
    schedule_mode: Literal["manual", "interval", "time-point", "condition"] = "manual"
    interval_seconds: int = 300
    schedule_at: str = ""
    analysis_prompt: str = ""
    actions: list[str] = []
    source: Literal["user", "agent", "builtin"] = "user"


class StrategyUpdate(BaseModel):
    status: Literal["active", "paused"]


class ManagedStrategyCondition(BaseModel):
    field: Literal["price", "pct", "volume", "ma5", "ma10", "ma20"] = "price"
    operator: Literal["gt", "gte", "lt", "lte", "cross_up", "cross_down"] = "gte"
    value: float | None = None
    compare_field: Literal["price", "pct", "volume", "ma5", "ma10", "ma20"] | None = None


class StrategyDraftRequest(BaseModel):
    prompt: str
    model: ChatProvider = "deepseek"


class ResearchNoteUpsert(BaseModel):
    code: str
    title: str = ""
    thesis: str = ""
    risks: str = ""
    key_metrics: str = ""
    reminders: str = ""


class InvestmentDecisionCreate(BaseModel):
    code: str
    action: Literal["buy", "sell", "hold", "review"] = "review"
    shares: int | None = None
    price: float | None = None
    rationale: str
    target_or_stop: str = ""
    review: str = ""


class StrategyVersionCreate(BaseModel):
    strategy_id: str | None = None
    strategy_name: str
    version: str
    change_summary: str
    rationale: str = ""
    backtest_summary: str = ""


class ResearchReportGenerate(BaseModel):
    code: str
    report_type: Literal["fundamental", "technical", "event"] = "fundamental"
    news_id: int | None = None
    model: ChatProvider = "deepseek"


WORKBENCH_CACHE_TTL_SECONDS = 45
WORKBENCH_CACHE_MAX_ITEMS = 128
_workbench_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _workbench_cache_key(tool: str, arguments: dict[str, Any]) -> str:
    return json.dumps({"tool": tool, "arguments": arguments}, ensure_ascii=False, sort_keys=True, default=str)


def _workbench_fallback(tool: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if tool == "get_kline" and arguments.get("period", "day") == "day":
        return "get_kline_with_ma", {"code": arguments["code"]}
    if tool == "get_finance_snapshot":
        return "get_financial_statements", {"code": arguments["code"], "report_type": "lrb", "periods": 8}
    if tool == "get_announcements":
        return "get_announcements_backup", {"code": arguments["code"], "limit": arguments.get("limit", 20)}
    if tool == "get_fund_flow_history":
        return "get_fund_flow_backup", {"code": arguments["code"], "days": 60}
    if tool == "get_industry_comparison":
        return "get_board_fund_flow", {"board_type": "industry", "period": "today", "top_n": arguments.get("top_n", 20)}
    return None


def resilient_workbench_query(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    cache_key = _workbench_cache_key(tool, arguments)
    cached = _workbench_cache.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < WORKBENCH_CACHE_TTL_SECONDS:
        result = dict(cached[1])
        result["cacheHit"] = True
        return result

    primary = run_tool(tool, arguments)
    primary["attempts"] = 1
    if primary.get("status") == "success":
        _workbench_cache[cache_key] = (now, primary)
        if len(_workbench_cache) > WORKBENCH_CACHE_MAX_ITEMS:
            oldest_key = min(_workbench_cache, key=lambda key: _workbench_cache[key][0])
            _workbench_cache.pop(oldest_key, None)
        return primary

    if primary.get("status") == "error":
        retry = run_tool(tool, arguments)
        primary["attempts"] = 2
        if retry.get("status") == "success":
            retry["attempts"] = 2
            _workbench_cache[cache_key] = (time.monotonic(), retry)
            return retry
        primary["retryStatus"] = retry.get("status")

    fallback = _workbench_fallback(tool, arguments)
    if fallback:
        fallback_tool, fallback_arguments = fallback
        fallback_result = run_tool(fallback_tool, fallback_arguments)
        fallback_result["requestedTool"] = tool
        fallback_result["fallbackUsed"] = True
        fallback_result["attempts"] = int(primary.get("attempts", 1)) + 1
        if fallback_result.get("status") == "success":
            _workbench_cache[cache_key] = (time.monotonic(), fallback_result)
        return fallback_result
    return primary


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def taxonomy_data() -> dict[str, Any]:
    return load_json(TAXONOMY_PATH)


def deepseek_api_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def openai_api_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


def claude_api_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("CLAUDE_API_KEY", "").strip()


def provider_system_message(preferences: list[dict[str, Any]]) -> str:
    preference_text = "\n".join(f"- {item['label']}：{item['value']}" for item in preferences)
    system_message = """你是一位拥有 10 年 A 股投资经验的分析师，专注于基本面和量化研究。

【回答规范】
1. 每个结论必须标注数据来源和时间；没有可核实数据时，明确说明数据缺口。
2. 每次回答必须包含风险提示，并区分事实、推断与不确定性。
3. 禁止使用“建议买入”“推荐卖出”“目标价”等表述，不提供交易、仓位或收益承诺。
4. 只提供信息分析和研究框架，不替用户做投资决策。

【默认回答结构】
- 核心观点：一句话总结，并标注判断依据的时间范围。
- 数据依据：列出关键数据、来源和截至时间。
- 风险因素：列出主要风险与仍需验证的信息。
- 参考信息：可选，列出相关公告、资讯或研报。

回答使用中文；财务数据必须标注报告期，行情和资讯必须标注截至时间。"""
    if preference_text:
        system_message += f"\n用户长期偏好：\n{preference_text}"
    return system_message


PROVIDER_META: dict[str, dict[str, str]] = {
    "deepseek": {"label": "DeepSeek", "key": "DEEPSEEK_API_KEY"},
    "openai": {"label": "OpenAI", "key": "OPENAI_API_KEY"},
    "claude": {"label": "Claude", "key": "ANTHROPIC_API_KEY / CLAUDE_API_KEY"},
}


MAX_AGENT_TOOL_CALLS = 6


def deepseek_response(messages: list[dict[str, str]], preferences: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    api_key = deepseek_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="DeepSeek 尚未配置")
    provider_messages: list[dict[str, Any]] = [{"role": "system", "content": provider_system_message(preferences)}, *messages]
    traces: list[dict[str, Any]] = []
    for _ in range(MAX_AGENT_TOOL_CALLS):
        request_body = json.dumps(
            {
                "model": "deepseek-chat",
                "messages": provider_messages,
                "temperature": 0.3,
                "tools": tool_definitions(),
                "tool_choice": "auto",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            "https://api.deepseek.com/chat/completions",
            data=request_body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            raise HTTPException(status_code=502, detail="DeepSeek 请求失败，请稍后重试") from None
        message = payload.get("choices", [{}])[0].get("message", {})
        calls = message.get("tool_calls") or []
        if not calls:
            content = message.get("content", "")
            if not isinstance(content, str) or not content.strip():
                raise HTTPException(status_code=502, detail="DeepSeek 未返回可用回答")
            return content.strip(), traces
        provider_messages.append(
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": calls,
            }
        )
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name", "")
            raw_arguments = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                arguments = None
            if arguments is None:
                trace = {"tool": name, "status": "invalid_arguments", "error": "模型返回的工具参数不是合法 JSON", "updatedAt": now_iso()}
            else:
                trace = run_tool(name, arguments)
            trace["arguments"] = arguments
            traces.append(trace)
            provider_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", str(uuid.uuid4())),
                    "content": json.dumps(trace, ensure_ascii=False, default=str),
                }
            )
    return "工具调用次数已达到本轮上限，以上结果可能不完整，请缩小查询范围后重试。", traces


def deepseek_stream_response(messages: list[dict[str, str]], preferences: list[dict[str, Any]]) -> Generator[str, None, tuple[str, list[dict[str, Any]]]]:
    api_key = deepseek_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="DeepSeek 尚未配置")
    provider_messages: list[dict[str, Any]] = [{"role": "system", "content": provider_system_message(preferences)}, *messages]
    traces: list[dict[str, Any]] = []
    for _ in range(MAX_AGENT_TOOL_CALLS):
        request_body = json.dumps(
            {
                "model": "deepseek-chat",
                "messages": provider_messages,
                "temperature": 0.3,
                "stream": True,
                "tools": tool_definitions(),
                "tool_choice": "auto",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            "https://api.deepseek.com/chat/completions",
            data=request_body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                content_parts: list[str] = []
                tool_calls: dict[int, dict[str, Any]] = {}
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    body = line[6:]
                    if body == "[DONE]":
                        break
                    payload = json.loads(body)
                    delta = payload.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content")
                    if isinstance(text, str) and text:
                        content_parts.append(text)
                        if not tool_calls:
                            yield text
                    for part in delta.get("tool_calls") or []:
                        index = int(part.get("index", 0))
                        call = tool_calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        call["id"] = part.get("id") or call["id"]
                        function = part.get("function") or {}
                        call["function"]["name"] += function.get("name") or ""
                        call["function"]["arguments"] += function.get("arguments") or ""
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=502, detail="DeepSeek 流式请求失败，请稍后重试") from None

        content = "".join(content_parts).strip()
        if not tool_calls:
            if not content:
                raise HTTPException(status_code=502, detail="DeepSeek 未返回可用回答")
            return content, traces
        calls = [tool_calls[index] for index in sorted(tool_calls)]
        provider_messages.append({"role": "assistant", "content": content or None, "tool_calls": calls})
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name", "")
            raw_arguments = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                arguments = None
            if arguments is None:
                trace = {"tool": name, "status": "invalid_arguments", "error": "模型返回的工具参数不是合法 JSON", "updatedAt": now_iso()}
            else:
                trace = run_tool(name, arguments)
            trace["arguments"] = arguments
            traces.append(trace)
            provider_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or str(uuid.uuid4()),
                    "content": json.dumps(trace, ensure_ascii=False, default=str),
                }
            )
    return "工具调用次数已达到本轮上限，以上结果可能不完整，请缩小查询范围后重试。", traces


def openai_response(messages: list[dict[str, str]], preferences: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    api_key = openai_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="OpenAI 尚未配置")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    provider_messages: list[dict[str, Any]] = [{"role": "system", "content": provider_system_message(preferences)}, *messages]
    traces: list[dict[str, Any]] = []
    for _ in range(MAX_AGENT_TOOL_CALLS):
        request_body = json.dumps(
            {
                "model": model,
                "messages": provider_messages,
                "temperature": 0.3,
                "tools": tool_definitions(),
                "tool_choice": "auto",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            "https://api.openai.com/v1/chat/completions",
            data=request_body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            raise HTTPException(status_code=502, detail="OpenAI 请求失败，请稍后重试") from None
        message = payload.get("choices", [{}])[0].get("message", {})
        calls = message.get("tool_calls") or []
        if not calls:
            content = message.get("content", "")
            if not isinstance(content, str) or not content.strip():
                raise HTTPException(status_code=502, detail="OpenAI 未返回可用回答")
            return content.strip(), traces
        provider_messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name", "")
            raw_arguments = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                arguments = None
            trace = {"tool": name, "status": "invalid_arguments", "error": "模型返回的工具参数不是合法 JSON", "updatedAt": now_iso()} if arguments is None else run_tool(name, arguments)
            trace["arguments"] = arguments
            traces.append(trace)
            provider_messages.append({"role": "tool", "tool_call_id": call.get("id", str(uuid.uuid4())), "content": json.dumps(trace, ensure_ascii=False, default=str)})
    return "工具调用次数已达到本轮上限，以上结果可能不完整，请缩小查询范围后重试。", traces


def claude_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": definition["function"]["name"],
            "description": definition["function"]["description"],
            "input_schema": definition["function"]["parameters"],
        }
        for definition in tool_definitions()
    ]


def claude_response(messages: list[dict[str, str]], preferences: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    api_key = claude_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="Claude 尚未配置")
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest").strip() or "claude-3-5-haiku-latest"
    provider_messages: list[dict[str, Any]] = [{"role": message["role"], "content": message["content"]} for message in messages if message["role"] in {"user", "assistant"}]
    traces: list[dict[str, Any]] = []
    for _ in range(MAX_AGENT_TOOL_CALLS):
        request_body = json.dumps(
            {
                "model": model,
                "max_tokens": 2048,
                "temperature": 0.3,
                "system": provider_system_message(preferences),
                "messages": provider_messages,
                "tools": claude_tools(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            "https://api.anthropic.com/v1/messages",
            data=request_body,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            raise HTTPException(status_code=502, detail="Claude 请求失败，请稍后重试") from None
        content_blocks = payload.get("content") or []
        text_parts = [block.get("text", "") for block in content_blocks if block.get("type") == "text"]
        tool_blocks = [block for block in content_blocks if block.get("type") == "tool_use"]
        if not tool_blocks:
            content = "\n".join(part for part in text_parts if part).strip()
            if not content:
                raise HTTPException(status_code=502, detail="Claude 未返回可用回答")
            return content, traces
        provider_messages.append({"role": "assistant", "content": content_blocks})
        tool_results = []
        for block in tool_blocks:
            arguments = block.get("input") if isinstance(block.get("input"), dict) else None
            name = str(block.get("name", ""))
            trace = {"tool": name, "status": "invalid_arguments", "error": "模型返回的工具参数不是合法 JSON", "updatedAt": now_iso()} if arguments is None else run_tool(name, arguments)
            trace["arguments"] = arguments
            traces.append(trace)
            tool_results.append({"type": "tool_result", "tool_use_id": block.get("id", str(uuid.uuid4())), "content": json.dumps(trace, ensure_ascii=False, default=str)})
        provider_messages.append({"role": "user", "content": tool_results})
    return "工具调用次数已达到本轮上限，以上结果可能不完整，请缩小查询范围后重试。", traces


def provider_response(model: ChatProvider, messages: list[dict[str, str]], preferences: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    if model == "openai":
        return openai_response(messages, preferences)
    if model == "claude":
        return claude_response(messages, preferences)
    return deepseek_response(messages, preferences)


def provider_stream_response(model: ChatProvider, messages: list[dict[str, str]], preferences: list[dict[str, Any]]) -> Generator[str, None, tuple[str, list[dict[str, Any]]]]:
    if model == "deepseek":
        response_stream = deepseek_stream_response(messages, preferences)
        while True:
            try:
                yield next(response_stream)
            except StopIteration as complete:
                return complete.value
    answer, traces = provider_response(model, messages, preferences)
    for index in range(0, len(answer), 120):
        yield answer[index:index + 120]
    return answer, traces


def database() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            primary_sector TEXT NOT NULL DEFAULT '宏观与市场',
            industry TEXT NOT NULL DEFAULT '',
            topics TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_health (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            last_checked_at TEXT,
            last_success_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            item_count INTEGER NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS news_read (
            news_id INTEGER PRIMARY KEY,
            is_read INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(news_id) REFERENCES news(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS news_subscriptions (
            id TEXT PRIMARY KEY,
            keyword TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def app_database() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(APP_DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            preview TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tool_calls (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            assistant_message_id TEXT,
            tool_name TEXT NOT NULL,
            status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            arguments_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS price_alerts (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            field TEXT NOT NULL DEFAULT 'price',
            operator TEXT NOT NULL DEFAULT 'gte',
            value REAL NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            triggered_at TEXT,
            last_checked_at TEXT,
            last_value REAL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS strategies (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
            code TEXT NOT NULL, field TEXT NOT NULL, operator TEXT NOT NULL,
            value REAL NOT NULL, mode TEXT NOT NULL DEFAULT 'weighted',
            weight REAL NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active',
            last_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            conditions_json TEXT NOT NULL DEFAULT '[]',
            schedule_mode TEXT NOT NULL DEFAULT 'manual',
            interval_seconds INTEGER NOT NULL DEFAULT 300,
            schedule_at TEXT NOT NULL DEFAULT '',
            analysis_prompt TEXT NOT NULL DEFAULT '',
            actions_json TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT 'user',
            last_triggered_at TEXT,
            last_scheduled_for TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_runs (
            id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, matched INTEGER NOT NULL,
            observed_value REAL, source TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            FOREIGN KEY(strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_decisions (
            id TEXT PRIMARY KEY, mode TEXT NOT NULL, rating REAL NOT NULL,
            conclusion TEXT NOT NULL, tree_json TEXT NOT NULL, created_at TEXT NOT NULL,
            trigger_source TEXT NOT NULL DEFAULT 'manual', risks_json TEXT NOT NULL DEFAULT '[]',
            catalysts_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS research_notes (
            code TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            thesis TEXT NOT NULL DEFAULT '',
            risks TEXT NOT NULL DEFAULT '',
            key_metrics TEXT NOT NULL DEFAULT '',
            reminders TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS investment_decisions (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            action TEXT NOT NULL,
            shares INTEGER,
            price REAL,
            rationale TEXT NOT NULL,
            target_or_stop TEXT NOT NULL DEFAULT '',
            review TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS strategy_versions (
            id TEXT PRIMARY KEY,
            strategy_id TEXT,
            strategy_name TEXT NOT NULL,
            version TEXT NOT NULL,
            change_summary TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            backtest_summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS research_reports (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            report_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    tool_call_columns = {row["name"] for row in connection.execute("PRAGMA table_info(agent_tool_calls)")}
    if "assistant_message_id" not in tool_call_columns:
        connection.execute("ALTER TABLE agent_tool_calls ADD COLUMN assistant_message_id TEXT")
    strategy_columns = {row["name"] for row in connection.execute("PRAGMA table_info(strategies)")}
    strategy_migrations = {
        "conditions_json": "TEXT NOT NULL DEFAULT '[]'",
        "schedule_mode": "TEXT NOT NULL DEFAULT 'manual'",
        "interval_seconds": "INTEGER NOT NULL DEFAULT 300",
        "schedule_at": "TEXT NOT NULL DEFAULT ''",
        "analysis_prompt": "TEXT NOT NULL DEFAULT ''",
        "actions_json": "TEXT NOT NULL DEFAULT '[]'",
        "source": "TEXT NOT NULL DEFAULT 'user'",
        "last_triggered_at": "TEXT",
        "last_scheduled_for": "TEXT",
    }
    for column, definition in strategy_migrations.items():
        if column not in strategy_columns:
            connection.execute(f"ALTER TABLE strategies ADD COLUMN {column} {definition}")
    decision_columns = {row["name"] for row in connection.execute("PRAGMA table_info(strategy_decisions)")}
    for column, definition in {
        "trigger_source": "TEXT NOT NULL DEFAULT 'manual'",
        "risks_json": "TEXT NOT NULL DEFAULT '[]'",
        "catalysts_json": "TEXT NOT NULL DEFAULT '[]'",
    }.items():
        if column not in decision_columns:
            connection.execute(f"ALTER TABLE strategy_decisions ADD COLUMN {column} {definition}")
    connection.commit()
    return connection


def setting_value(key: str, default: str = "") -> str:
    connection = app_database()
    try:
        row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default
    finally:
        connection.close()


def save_setting(key: str, value: str) -> None:
    connection = app_database()
    try:
        connection.execute(
            """
            INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now_iso()),
        )
        connection.commit()
    finally:
        connection.close()


def state_files(include_backups: bool = True) -> list[Path]:
    if not STATE_DIR.exists():
        return []
    excluded_directories = {"exports"}
    if not include_backups:
        excluded_directories.add("backups")
    return [
        path
        for path in STATE_DIR.rglob("*")
        if path.is_file() and not any(part in excluded_directories for part in path.relative_to(STATE_DIR).parts)
    ]


def state_size_bytes() -> int:
    return sum(path.stat().st_size for path in state_files() if path.exists())


def create_state_archive(destination: Path) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in state_files(include_backups=False):
            if path.resolve() == destination.resolve():
                continue
            archive.write(path, Path("state") / path.relative_to(STATE_DIR))
    return destination


def data_management_view() -> dict[str, Any]:
    files = state_files()
    backups = [path for path in files if "backups" in path.relative_to(STATE_DIR).parts]
    return {
        "storagePath": str(STATE_DIR),
        "totalBytes": state_size_bytes(),
        "fileCount": len(files),
        "automaticBackup": setting_value("automatic_backup", "off"),
        "lastBackupAt": setting_value("last_backup_at") or None,
        "backupCount": len(backups),
    }


def maybe_create_scheduled_backup() -> None:
    frequency = setting_value("automatic_backup", "off")
    if frequency not in {"daily", "weekly"}:
        return
    last_backup = setting_value("last_backup_at")
    interval = timedelta(days=1 if frequency == "daily" else 7)
    if last_backup:
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(last_backup) < interval:
                return
        except ValueError:
            pass
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = STATE_DIR / "backups" / f"ai-research-backup-{timestamp}.zip"
    create_state_archive(archive_path)
    save_setting("last_backup_at", now_iso())


def clear_local_history() -> None:
    news_connection = database()
    try:
        news_connection.execute("DELETE FROM news_read")
        news_connection.execute("DELETE FROM news_subscriptions")
        news_connection.execute("DELETE FROM news")
        news_connection.execute("DELETE FROM source_health")
        news_connection.commit()
    finally:
        news_connection.close()
    app_connection = app_database()
    try:
        for table in ("agent_tool_calls", "conversations", "preferences", "watchlist", "price_alerts", "strategy_runs", "strategy_decisions", "strategies"):
            app_connection.execute(f"DELETE FROM {table}")
        app_connection.commit()
    finally:
        app_connection.close()


def required_text(value: str, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{field_name}不能为空")
    if len(normalized) > max_length:
        raise HTTPException(status_code=422, detail=f"{field_name}不能超过{max_length}个字符")
    return normalized


def clean_text(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detail_text(*values: Any) -> str:
    parts = []
    for value in values:
        if not value:
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        parts.append(clean_text(str(value)))
    return " ".join(part for part in parts if part)


def classify(title: str, summary: str) -> tuple[str, str, list[str]]:
    text = f"{title} {summary}".lower()
    data = taxonomy_data()
    industry = ""
    primary_sector = "宏观与市场"
    for sector in data["primarySectors"]:
        for candidate in sector.get("industries", []):
            if candidate.lower() in text:
                primary_sector = sector["name"]
                industry = candidate
                break
        if industry:
            break
    for topic in data["themes"]:
        if topic.lower() in text:
            if not industry and topic in {"AI", "芯片", "算力", "消费电子"}:
                primary_sector = "科技与传媒"
            break
    topics = [topic for topic in data["themes"] if topic.lower() in text]
    if any(word in text for word in ("政策", "利率", "汇率", "央行", "市场")):
        primary_sector = "宏观与市场"
    return primary_sector, industry, topics


def news_item(title: str, summary: str, url: str, published: str, source: dict[str, Any]) -> dict[str, Any]:
    primary_sector, industry, topics = classify(title, summary)
    fingerprint = hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()
    return {
        "fingerprint": fingerprint,
        "title": title,
        "summary": summary[:500],
        "url": url,
        "source_id": source["id"],
        "source_name": source["name"],
        "published_at": published or None,
        "fetched_at": now_iso(),
        "primary_sector": primary_sector,
        "industry": industry,
        "topics": topics,
    }


def unique_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_fingerprint = {item["fingerprint"]: item for item in items}
    return list(by_fingerprint.values())


def parsed_news_time(item: dict[str, Any]) -> datetime | None:
    value = item.get("published_at") or item.get("fetched_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def normalized_headline(title: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", clean_text(title).lower())


def is_same_news_event(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_time = parsed_news_time(left)
    right_time = parsed_news_time(right)
    if not left_time or not right_time:
        return False
    if abs((left_time - right_time).total_seconds()) > SIMILAR_NEWS_WINDOW_SECONDS:
        return False
    left_title = normalized_headline(left["title"])
    right_title = normalized_headline(right["title"])
    if len(left_title) < 8 or len(right_title) < 8:
        return False
    if left_title == right_title:
        return True
    return SequenceMatcher(None, left_title, right_title).ratio() >= SIMILAR_NEWS_MIN_RATIO


def source_priorities() -> dict[str, int]:
    return {
        source["id"]: SOURCE_PRIORITY_BY_CATEGORY.get(source.get("category", ""), 50)
        for source in load_json(SOURCES_PATH).get("sources", [])
    }


def deduplicate_news_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priorities = source_priorities()
    ordered = sorted(
        items,
        key=lambda item: (
            priorities.get(item["source_id"], 50),
            -(parsed_news_time(item).timestamp() if parsed_news_time(item) else 0),
        ),
    )
    kept: list[dict[str, Any]] = []
    for item in ordered:
        if not any(is_same_news_event(item, existing) for existing in kept):
            kept.append(item)
    return sorted(
        kept,
        key=lambda item: parsed_news_time(item).timestamp() if parsed_news_time(item) else 0,
        reverse=True,
    )


def parse_feed(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(payload)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{*}entry")
    results = []
    for item in items[:50]:
        def value(*names: str) -> str:
            for name in names:
                child = item.find(name)
                if child is None:
                    child = item.find(f"{{*}}{name}")
                if child is not None and child.text:
                    return clean_text(child.text)
            return ""

        title = value("title")
        link = value("link", "guid")
        if not link:
            link_node = item.find("{*}link")
            link = link_node.attrib.get("href", "") if link_node is not None else ""
        summary = value("description", "summary", "content")
        published = value("pubDate", "published", "updated")
        if not title or not link:
            continue
        results.append(news_item(title, summary, link, published, source))
    return results


def parse_cls(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    results = []
    for item in data.get("data", {}).get("roll_data", [])[:100]:
        title = clean_text(item.get("title") or item.get("brief") or item.get("content"))
        summary = clean_text(item.get("content") or item.get("brief"))
        article_id = item.get("id")
        if not title or not article_id:
            continue
        published = ""
        if item.get("ctime"):
            published = datetime.fromtimestamp(item["ctime"], timezone.utc).isoformat()
        results.append(news_item(title, summary, f"https://www.cls.cn/detail/{article_id}", published, source))
    return results


def parse_eastmoney(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    results = []
    for item in data.get("data", {}).get("fastNewsList", [])[:100]:
        title = clean_text(item.get("title"))
        summary = clean_text(item.get("summary"))
        if not title:
            continue
        code = item.get("code", "")
        results.append(news_item(title, summary, f"https://kuaixun.eastmoney.com/news/{code}", item.get("showTime", ""), source))
    return results


def parse_jsonp(payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8")
    start = text.find("(")
    end = text.rfind(")")
    return json.loads(text[start + 1:end] if start >= 0 and end > start else text)


def parse_eastmoney_stock_news(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = parse_jsonp(payload)
    articles = data.get("result", {}).get("cmsArticleWebOld", []) or []
    return [
        news_item(
            clean_text(article.get("title")),
            clean_text(article.get("content")),
            article.get("url", ""),
            article.get("date", ""),
            source,
        )
        for article in articles[:100]
        if article.get("title") and article.get("url")
    ]


def parse_eastmoney_reports(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    results = []
    for report in (data.get("data") or [])[:100]:
        title = clean_text(report.get("title"))
        info_code = report.get("infoCode", "")
        if not title or not info_code:
            continue
        details = [
            report.get("stockName", ""),
            report.get("stockCode", ""),
            report.get("industryName", "") or report.get("indvInduName", ""),
            report.get("orgSName", ""),
        ]
        results.append(
            news_item(
                title,
                " | ".join(value for value in details if value),
                f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf",
                report.get("publishDate", ""),
                source,
            )
        )
    return results


def parse_cninfo(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    results = []
    for announcement in (data.get("announcements") or [])[:100]:
        title = clean_text(announcement.get("announcementTitle"))
        announcement_id = announcement.get("announcementId", "")
        if not title or not announcement_id:
            continue
        timestamp = announcement.get("announcementTime")
        published = datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat() if timestamp else ""
        summary = detail_text(announcement.get("secName", ""), announcement.get("secCode", ""))
        results.append(
            news_item(
                title,
                summary,
                f"https://www.cninfo.com.cn/new/disclosure/detail?annoId={announcement_id}",
                published,
                source,
            )
        )
    return results


def parse_sse(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    rows = data.get("pageHelp", {}).get("data") or data.get("result") or []
    results = []
    for announcement in rows[:100]:
        title = clean_text(announcement.get("TITLE"))
        relative_url = announcement.get("URL", "")
        if not title or not relative_url:
            continue
        summary = detail_text(announcement.get("SECURITY_NAME", ""), announcement.get("SECURITY_CODE", ""))
        results.append(news_item(title, summary, urljoin("https://www.sse.com.cn", relative_url), announcement.get("SSEDATE", ""), source))
    return results


def parse_szse(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    data = json.loads(payload.decode("utf-8"))
    rows = data.get("data") or []
    results = []
    for announcement in rows[:100]:
        title = clean_text(announcement.get("title"))
        attachment = announcement.get("attachPath", "")
        if not title or not attachment:
            continue
        summary = detail_text(announcement.get("secName", ""), announcement.get("secCode", ""))
        results.append(
            news_item(
                title,
                summary,
                urljoin("https://disc.static.szse.cn/download/", attachment),
                announcement.get("publishTime", ""),
                source,
            )
        )
    return results


def decoded_html(payload: bytes, source: dict[str, Any]) -> str:
    if source["format"] == "10jqka":
        return payload.decode("gb18030", errors="replace")
    return payload.decode("utf-8", errors="replace")


def parse_pbc(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    text = decoded_html(payload, source)
    pattern = re.compile(
        r'<a\s+[^>]*href="(?P<url>[^"]+)"[^>]*title="(?P<title>[^"]+)"[^>]*>.*?</a>.*?<span[^>]*>(?P<published>\d{4}-\d{2}-\d{2})</span>',
        re.S,
    )
    return [
        news_item(clean_text(match["title"]), "", urljoin(source["url"], match["url"]), match["published"], source)
        for match in list(pattern.finditer(text))[:100]
    ]


def parse_stats(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    text = decoded_html(payload, source)
    pattern = re.compile(r'<a[^>]+href="(?P<url>[^"]+)"[^>]+title=[\'"](?P<title>[^\'"]+)[\'"]', re.S)
    return [
        news_item(clean_text(match["title"]), "", urljoin(source["url"], match["url"]), "", source)
        for match in list(pattern.finditer(text))[:100]
        if "t20" in match["url"]
    ]


def parse_sina(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    text = decoded_html(payload, source)
    pattern = re.compile(r'<li><a\s+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a><span>\((?P<published>[^)]+)\)</span>', re.S)
    return [
        news_item(clean_text(match["title"]), "", match["url"], clean_text(match["published"]), source)
        for match in list(pattern.finditer(text))[:100]
    ]


def parse_10jqka(payload: bytes, source: dict[str, Any]) -> list[dict[str, Any]]:
    text = decoded_html(payload, source)
    pattern = re.compile(r'<a\s+[^>]*title="(?P<title>[^"]+)"\s+href="(?P<url>[^"]+)"[^>]*class="news-link"', re.S)
    return [
        news_item(clean_text(match["title"]), "", match["url"], "", source)
        for match in list(pattern.finditer(text))[:100]
    ]


def fetch_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source["format"] == "cls":
        params = {"appName": "CailianpressWeb", "os": "web", "sv": "7.7.5", "last_time": "", "refresh_type": "1", "rn": "50"}
        query = urlencode(sorted(params.items()))
        sign = hashlib.md5(hashlib.sha1(query.encode("utf-8")).hexdigest().encode("utf-8")).hexdigest()
        request = Request(f"{source['url']}?{query}&sign={sign}", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cls.cn/"})
        with urlopen(request, timeout=10) as response:
            return parse_cls(response.read(), source)
    if source["format"] == "eastmoney":
        params = {"client": "web", "biz": "web_724", "fastColumn": "102", "sortEnd": "", "pageSize": "100", "req_trace": str(uuid.uuid4())}
        request = Request(f"{source['url']}?{urlencode(params)}", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://kuaixun.eastmoney.com/"})
        with urlopen(request, timeout=10) as response:
            return parse_eastmoney(response.read(), source)
    if source["format"] == "eastmoney-stock-news":
        search = {
            "uid": "",
            "keyword": "A股",
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default", "pageIndex": 1, "pageSize": 100, "preTag": "", "postTag": ""}},
        }
        request = Request(f"{source['url']}?{urlencode({'cb': 'desktopAgentNews', 'param': json.dumps(search, ensure_ascii=False, separators=(',', ':'))})}", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://so.eastmoney.com/"})
        with urlopen(request, timeout=15) as response:
            return parse_eastmoney_stock_news(response.read(), source)
    if source["format"] == "eastmoney-report":
        params = {"industryCode": "*", "pageSize": "100", "industry": "*", "rating": "*", "ratingChange": "*", "beginTime": "2020-01-01", "endTime": "2030-01-01", "pageNo": "1", "fields": "", "qType": source["qType"], "orgCode": "", "code": "", "rcode": ""}
        request = Request(f"{source['url']}?{urlencode(params)}", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
        with urlopen(request, timeout=15) as response:
            return parse_eastmoney_reports(response.read(), source)
    if source["format"] == "cninfo":
        form = {"stock": "", "tabName": "fulltext", "pageSize": "100", "pageNum": "1", "column": "", "category": "", "plate": "", "seDate": "", "searchkey": "", "secid": "", "sortName": "", "sortType": "", "isHLtitle": "true"}
        request = Request(source["url"], data=urlencode(form).encode("utf-8"), headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/new/disclosure", "Origin": "https://www.cninfo.com.cn", "Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(request, timeout=15) as response:
            return parse_cninfo(response.read(), source)
    if source["format"] == "sse":
        params = {"isPagination": "true", "productId": "", "securityType": "0101,120100,020100,020200,120200", "reportType": "ALL", "reportType2": "", "beginDate": "", "endDate": "", "pageHelp.pageSize": "100", "pageHelp.pageNo": "1", "pageHelp.beginPage": "1", "pageHelp.cacheSize": "1", "pageHelp.endPage": "1"}
        request = Request(f"{source['url']}?{urlencode(params)}", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/", "Accept": "application/json"})
        with urlopen(request, timeout=15) as response:
            return parse_sse(response.read(), source)
    if source["format"] == "szse":
        body = json.dumps({"channelCode": ["listedNotice_disc"], "pageSize": 100, "pageNum": 1, "stock": []}).encode("utf-8")
        request = Request(source["url"], data=body, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.szse.cn/disclosure/listed/notice/index.html", "Content-Type": "application/json", "Accept": "application/json"})
        with urlopen(request, timeout=15) as response:
            return parse_szse(response.read(), source)
    request = Request(source["url"], headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"})
    with urlopen(request, timeout=10) as response:
        payload = response.read()
    parsers = {"pbc": parse_pbc, "stats": parse_stats, "sina": parse_sina, "10jqka": parse_10jqka}
    return parsers[source["format"]](payload, source)


def refresh_sources() -> dict[str, Any]:
    sources = load_json(SOURCES_PATH).get("sources", [])
    connection = database()
    inserted = 0
    source_results = []
    for source in sources:
        checked_at = now_iso()
        status = "pending" if source.get("format") == "pending" or not source.get("enabled", True) else "ok"
        detail = "数据源待接入" if status == "pending" else ""
        items: list[dict[str, Any]] = []
        try:
            if status == "pending":
                raise LookupError(detail)
            items = unique_items(fetch_source(source))
            for item in items:
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO news
                    (fingerprint, title, summary, url, source_id, source_name, published_at, fetched_at, primary_sector, industry, topics)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item["fingerprint"], item["title"], item["summary"], item["url"], item["source_id"], item["source_name"], item["published_at"], item["fetched_at"], item["primary_sector"], item["industry"], json.dumps(item["topics"], ensure_ascii=False)),
                )
                inserted += cursor.rowcount
        except LookupError:
            pass
        except (OSError, URLError, ElementTree.ParseError, TimeoutError, TypeError, ValueError, json.JSONDecodeError) as error:
            status = "error"
            detail = str(error)[:240]
        connection.execute(
            """INSERT INTO source_health (source_id, source_name, last_checked_at, last_success_at, status, item_count, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET last_checked_at=excluded.last_checked_at,
            last_success_at=CASE WHEN excluded.status='ok' THEN excluded.last_checked_at ELSE source_health.last_success_at END,
            status=excluded.status, item_count=excluded.item_count, detail=excluded.detail""",
            (source["id"], source["name"], checked_at, checked_at if status == "ok" else None, status, len(items), detail),
        )
        source_results.append({"id": source["id"], "name": source["name"], "status": status, "itemCount": len(items), "detail": detail})
    connection.commit()
    connection.close()
    return {"inserted": inserted, "sources": source_results, "refreshedAt": now_iso()}


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "desktop-agent-backend", "status": "ok"}


@app.get("/agent/data-management")
def get_data_management() -> dict[str, Any]:
    """Expose only local state metadata; no investment data leaves loopback."""
    return data_management_view()


@app.put("/agent/data-management")
def update_data_management(payload: DataManagementUpdate) -> dict[str, Any]:
    save_setting("automatic_backup", payload.automatic_backup)
    return data_management_view()


@app.get("/agent/data-management/export")
def export_local_data() -> FileResponse:
    descriptor, temporary_name = tempfile.mkstemp(prefix="ai-research-data-", suffix=".zip")
    os.close(descriptor)
    archive_path = Path(temporary_name)
    try:
        create_state_archive(archive_path)
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="本地数据导出失败") from None
    filename = f"ai-research-local-data-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@app.post("/agent/data-management/clear")
def clear_data_management_history() -> dict[str, Any]:
    clear_local_history()
    return {"status": "cleared", **data_management_view()}


@app.get("/providers/deepseek")
def deepseek_provider_status() -> dict[str, Any]:
    return {"provider": "deepseek", "configured": bool(deepseek_api_key()), "keySource": "environment" if deepseek_api_key() else None}


@app.get("/providers")
def provider_statuses() -> list[dict[str, Any]]:
    keys = {"deepseek": deepseek_api_key(), "openai": openai_api_key(), "claude": claude_api_key()}
    return [
        {
            "provider": provider,
            "label": meta["label"],
            "configured": bool(keys[provider]),
            "keyName": meta["key"],
            "keySource": "environment" if keys[provider] else None,
        }
        for provider, meta in PROVIDER_META.items()
    ]


@app.get("/agent/tools")
def agent_tools() -> list[dict[str, Any]]:
    return [
        {"name": definition["function"]["name"], "description": definition["function"]["description"]}
        for definition in tool_definitions()
    ]


@app.get("/agent/conversations")
def agent_conversations() -> list[dict[str, Any]]:
    connection = app_database()
    try:
        rows = connection.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC, created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.post("/agent/conversations")
def create_agent_conversation(payload: ConversationCreate) -> dict[str, Any]:
    title = required_text(payload.title, "会话标题", 80)
    timestamp = now_iso()
    conversation = {
        "id": str(uuid.uuid4()),
        "title": title,
        "preview": "等待你的第一个问题",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    connection = app_database()
    try:
        connection.execute(
            """
            INSERT INTO conversations (id, title, preview, created_at, updated_at)
            VALUES (:id, :title, :preview, :created_at, :updated_at)
            """,
            conversation,
        )
        connection.commit()
        return conversation
    finally:
        connection.close()


@app.delete("/agent/conversations/{conversation_id}")
def delete_agent_conversation(conversation_id: str) -> dict[str, str]:
    connection = app_database()
    try:
        result = connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
        connection.commit()
        return {"status": "deleted", "id": conversation_id}
    finally:
        connection.close()


@app.get("/agent/conversations/{conversation_id}/messages")
def agent_conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    connection = app_database()
    try:
        exists = connection.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="会话不存在")
        rows = connection.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.get("/agent/conversations/{conversation_id}/tool-calls")
def agent_conversation_tool_calls(conversation_id: str) -> list[dict[str, Any]]:
    connection = app_database()
    try:
        exists = connection.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="会话不存在")
        rows = connection.execute(
            "SELECT * FROM agent_tool_calls WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        assistant_rows = connection.execute(
            """
            SELECT id, created_at FROM conversation_messages
            WHERE conversation_id = ? AND role = 'assistant'
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["arguments"] = json.loads(item.pop("arguments_json"))
            item["result"] = json.loads(item.pop("result_json"))
            if not item.get("assistant_message_id"):
                following_assistant = next(
                    (assistant for assistant in assistant_rows if assistant["created_at"] >= item["created_at"]),
                    None,
                )
                if following_assistant:
                    item["assistant_message_id"] = following_assistant["id"]
            result.append(item)
        return result
    finally:
        connection.close()


@app.post("/agent/conversations/{conversation_id}/messages")
def create_agent_message(conversation_id: str, payload: MessageCreate) -> dict[str, Any]:
    content = required_text(payload.content, "消息内容", 4000)
    timestamp = now_iso()
    message = {
        "id": str(uuid.uuid4()),
        "conversation_id": conversation_id,
        "role": payload.role,
        "content": content,
        "created_at": timestamp,
    }
    connection = app_database()
    try:
        exists = connection.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="会话不存在")
        connection.execute(
            """
            INSERT INTO conversation_messages (id, conversation_id, role, content, created_at)
            VALUES (:id, :conversation_id, :role, :content, :created_at)
            """,
            message,
        )
        connection.execute(
            "UPDATE conversations SET preview = ?, updated_at = ? WHERE id = ?",
            (content[:120], timestamp, conversation_id),
        )
        connection.commit()
        return message
    finally:
        connection.close()


def store_agent_response(conversation_id: str, answer: str, tool_traces: list[dict[str, Any]]) -> dict[str, Any]:
    # Keep the visible answer within the app's research-only boundary even if a provider omits it.
    answer = re.sub(r"(?:建议|推荐|可以|应当)(?:立即)?(买入|卖出|加仓|减仓)", r"可进一步核查\1相关公开数据", answer)
    if "风险提示" not in answer:
        answer = f"{answer}\n\n风险提示：以上内容仅用于公开信息整理与研究，不构成投资建议。"
    assistant_timestamp = now_iso()
    assistant_message = {
        "id": str(uuid.uuid4()),
        "conversation_id": conversation_id,
        "role": "assistant",
        "content": answer,
        "created_at": assistant_timestamp,
    }
    connection = app_database()
    try:
        for trace in tool_traces:
            connection.execute(
                """
                INSERT INTO agent_tool_calls
                (id, conversation_id, assistant_message_id, tool_name, status, source, arguments_json, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    conversation_id,
                    assistant_message["id"],
                    str(trace.get("tool", "")),
                    str(trace.get("status", "error")),
                    str(trace.get("source", "")),
                    json.dumps(trace.get("arguments"), ensure_ascii=False, default=str),
                    json.dumps(trace, ensure_ascii=False, default=str),
                    trace.get("updatedAt", assistant_timestamp),
                ),
            )
        connection.execute(
            """
            INSERT INTO conversation_messages (id, conversation_id, role, content, created_at)
            VALUES (:id, :conversation_id, :role, :content, :created_at)
            """,
            assistant_message,
        )
        connection.execute(
            "UPDATE conversations SET preview = ?, updated_at = ? WHERE id = ?",
            (answer[:120], assistant_timestamp, conversation_id),
        )
        connection.commit()
        return assistant_message
    finally:
        connection.close()


def stream_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/agent/conversations/{conversation_id}/chat")
def chat_with_agent(conversation_id: str, payload: ChatRequest) -> dict[str, Any]:
    content = required_text(payload.content, "消息内容", 4000)
    user_timestamp = now_iso()
    user_message = {
        "id": str(uuid.uuid4()),
        "conversation_id": conversation_id,
        "role": "user",
        "content": content,
        "created_at": user_timestamp,
    }
    connection = app_database()
    try:
        exists = connection.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="会话不存在")
        connection.execute(
            """
            INSERT INTO conversation_messages (id, conversation_id, role, content, created_at)
            VALUES (:id, :conversation_id, :role, :content, :created_at)
            """,
            user_message,
        )
        connection.execute(
            "UPDATE conversations SET preview = ?, updated_at = ? WHERE id = ?",
            (content[:120], user_timestamp, conversation_id),
        )
        connection.commit()
        history_rows = connection.execute(
            """
            SELECT role, content FROM conversation_messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT 30
            """,
            (conversation_id,),
        ).fetchall()
        preference_rows = connection.execute(
            "SELECT label, value FROM preferences ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        connection.close()

    history = [dict(row) for row in reversed(history_rows)]
    answer, tool_traces = provider_response(payload.model, history, [dict(row) for row in preference_rows])
    assistant_message = store_agent_response(conversation_id, answer, tool_traces)
    return {"userMessage": user_message, "assistantMessage": assistant_message, "toolCalls": tool_traces}


@app.post("/agent/conversations/{conversation_id}/chat/stream")
def stream_chat_with_agent(conversation_id: str, payload: ChatRequest) -> StreamingResponse:
    content = required_text(payload.content, "消息内容", 4000)
    user_timestamp = now_iso()
    user_message = {
        "id": str(uuid.uuid4()),
        "conversation_id": conversation_id,
        "role": "user",
        "content": content,
        "created_at": user_timestamp,
    }
    connection = app_database()
    try:
        exists = connection.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="会话不存在")
        connection.execute(
            """
            INSERT INTO conversation_messages (id, conversation_id, role, content, created_at)
            VALUES (:id, :conversation_id, :role, :content, :created_at)
            """,
            user_message,
        )
        connection.execute(
            "UPDATE conversations SET preview = ?, updated_at = ? WHERE id = ?",
            (content[:120], user_timestamp, conversation_id),
        )
        connection.commit()
        history_rows = connection.execute(
            """
            SELECT role, content FROM conversation_messages
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT 30
            """,
            (conversation_id,),
        ).fetchall()
        preference_rows = connection.execute("SELECT label, value FROM preferences ORDER BY updated_at DESC").fetchall()
    finally:
        connection.close()

    history = [dict(row) for row in reversed(history_rows)]
    preferences = [dict(row) for row in preference_rows]

    def event_stream() -> Generator[str, None, None]:
        try:
            response_stream = provider_stream_response(payload.model, history, preferences)
            while True:
                try:
                    yield stream_event({"type": "delta", "content": next(response_stream)})
                except StopIteration as complete:
                    answer, tool_traces = complete.value
                    assistant_message = store_agent_response(conversation_id, answer, tool_traces)
                    yield stream_event({"type": "done", "userMessage": user_message, "assistantMessage": assistant_message})
                    return
        except HTTPException as error:
            yield stream_event({"type": "error", "message": str(error.detail)})
        except Exception:
            yield stream_event({"type": "error", "message": "流式回答中断，请稍后重试"})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/agent/preferences")
def agent_preferences() -> list[dict[str, Any]]:
    connection = app_database()
    try:
        rows = connection.execute("SELECT * FROM preferences ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.post("/agent/preferences")
def create_agent_preference(payload: PreferenceCreate) -> dict[str, Any]:
    preference = {
        "id": str(uuid.uuid4()),
        "label": required_text(payload.label, "偏好名称", 40),
        "value": required_text(payload.value, "偏好内容", 500),
        "updated_at": now_iso(),
    }
    connection = app_database()
    try:
        connection.execute(
            "INSERT INTO preferences (id, label, value, updated_at) VALUES (:id, :label, :value, :updated_at)",
            preference,
        )
        connection.commit()
        return preference
    finally:
        connection.close()


@app.put("/agent/preferences/{preference_id}")
def update_agent_preference(preference_id: str, payload: PreferenceUpdate) -> dict[str, Any]:
    preference = {
        "id": preference_id,
        "label": required_text(payload.label, "偏好名称", 40),
        "value": required_text(payload.value, "偏好内容", 500),
        "updated_at": now_iso(),
    }
    connection = app_database()
    try:
        result = connection.execute(
            """
            UPDATE preferences
            SET label = :label, value = :value, updated_at = :updated_at
            WHERE id = :id
            """,
            preference,
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="偏好不存在")
        connection.commit()
        return preference
    finally:
        connection.close()


@app.delete("/agent/preferences/{preference_id}")
def delete_agent_preference(preference_id: str) -> dict[str, str]:
    connection = app_database()
    try:
        result = connection.execute("DELETE FROM preferences WHERE id = ?", (preference_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="偏好不存在")
        connection.commit()
        return {"status": "deleted", "id": preference_id}
    finally:
        connection.close()


def normalize_watchlist_code(value: str) -> str:
    code = required_text(value, "股票代码", 12).lower()
    if not re.fullmatch(r"(?:sh|sz|bj)?\d{6}", code):
        raise HTTPException(status_code=422, detail="股票代码必须是六位 A 股代码")
    return code[-6:]


@app.get("/agent/watchlist")
def agent_watchlist() -> list[dict[str, Any]]:
    connection = app_database()
    try:
        rows = connection.execute("SELECT * FROM watchlist ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.post("/agent/watchlist")
def create_watchlist_item(payload: WatchlistCreate) -> dict[str, Any]:
    item = {"id": str(uuid.uuid4()), "code": normalize_watchlist_code(payload.code), "name": clean_text(payload.name)[:80], "created_at": now_iso()}
    connection = app_database()
    try:
        try:
            connection.execute("INSERT INTO watchlist (id, code, name, created_at) VALUES (:id, :code, :name, :created_at)", item)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="这只股票已经在自选股中") from None
        connection.commit()
        return item
    finally:
        connection.close()


@app.delete("/agent/watchlist/{watchlist_id}")
def delete_watchlist_item(watchlist_id: str) -> dict[str, str]:
    connection = app_database()
    try:
        result = connection.execute("DELETE FROM watchlist WHERE id = ?", (watchlist_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="自选股不存在")
        connection.commit()
        return {"status": "deleted", "id": watchlist_id}
    finally:
        connection.close()


def records_from_data(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data]
    return []


def numeric_value(row: dict[str, Any], keys: list[str]) -> float | None:
    for key, value in row.items():
        normalized = str(key).lower()
        if not any(candidate.lower() in normalized for candidate in keys):
            continue
        if value is None or value == "":
            continue
        try:
            return float(str(value).replace("%", "").replace(",", ""))
        except ValueError:
            continue
    return None


def text_value(row: dict[str, Any], keys: list[str]) -> str:
    for key, value in row.items():
        normalized = str(key).lower()
        if any(candidate.lower() in normalized for candidate in keys) and value not in (None, ""):
            return str(value)
    return ""


def operator_match(left: float, operator: str, right: float, previous: float | None = None) -> bool:
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    if operator == "cross_up":
        return previous is not None and previous < right <= left
    if operator == "cross_down":
        return previous is not None and previous > right >= left
    return False


def rule_value(row: dict[str, Any], field: str) -> float | None:
    aliases = {
        "open": ["open", "开盘"],
        "high": ["high", "最高"],
        "low": ["low", "最低"],
        "close": ["close", "收盘", "最新"],
        "price": ["price", "现价", "最新"],
        "volume": ["volume", "成交量"],
        "volume_ma5": ["volume_ma5", "volumema5", "成交量均值", "量MA5"],
        "amount": ["amount", "成交额"],
        "ma5": ["ma5", "MA5"],
        "ma10": ["ma10", "MA10"],
        "ma20": ["ma20", "MA20"],
        "pct": ["涨跌幅", "percent", "pct", "涨幅"],
    }
    return numeric_value(row, aliases.get(field.lower(), [field]))


def prepare_backtest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add deterministic moving averages so rules do not depend on provider fields."""
    prepared: list[dict[str, Any]] = []
    closes: list[float] = []
    volumes: list[float] = []
    for row in rows:
        current = dict(row)
        close = rule_value(current, "close")
        volume = rule_value(current, "volume")
        closes.append(float(close) if close is not None else float("nan"))
        volumes.append(float(volume) if volume is not None else float("nan"))
        for period, field in ((5, "ma5"), (10, "ma10"), (20, "ma20")):
            window = [value for value in closes[-period:] if math.isfinite(value)]
            if len(window) == period:
                current[field] = sum(window) / period
        volume_window = [value for value in volumes[-5:] if math.isfinite(value)]
        if len(volume_window) == 5:
            current["volume_ma5"] = sum(volume_window) / 5
        prepared.append(current)
    return prepared


def matches_backtest_rule(row: dict[str, Any], previous_row: dict[str, Any] | None, rule: StrategyRule) -> bool:
    left = rule_value(row, rule.field)
    previous_left = rule_value(previous_row, rule.field) if previous_row else None
    right = rule_value(row, rule.compare_field) if rule.compare_field else rule.value
    previous_right = rule_value(previous_row, rule.compare_field) if rule.compare_field and previous_row else rule.value
    if left is None or right is None:
        return False
    if rule.operator == "cross_up":
        return previous_left is not None and previous_right is not None and previous_left < previous_right <= left
    if rule.operator == "cross_down":
        return previous_left is not None and previous_right is not None and previous_left > previous_right >= left
    return operator_match(float(left), rule.operator, float(right))


class Backtester:
    """Single-position A-share backtester with cash accounting and market costs."""

    def __init__(self, payload: BacktestRequest) -> None:
        self.payload = payload
        self.commission_rate = max(0, min(payload.commission_rate, 0.02))
        self.stamp_duty_rate = max(0, min(payload.stamp_duty_rate, 0.02))
        self.slippage_rate = max(0, min(payload.slippage_rate, 0.02))
        self.position_pct = max(0.05, min(payload.position_pct, 1.0))
        self.initial_capital = max(10_000, payload.initial_capital)
        self.cash = self.initial_capital
        self.position: dict[str, Any] | None = None
        self.trades: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []

    def _open_position(self, row: dict[str, Any], index: int, close: float) -> None:
        execution_price = close * (1 + self.slippage_rate)
        per_share_cost = execution_price * (1 + self.commission_rate)
        shares = int((self.cash * self.position_pct / per_share_cost) // 100) * 100
        if shares < 100:
            return
        total_cost = shares * per_share_cost
        self.cash -= total_cost
        self.position = {
            "entryIndex": index,
            "entryTime": text_value(row, ["日期", "date", "datetime", "time"]),
            "entryPrice": round(execution_price, 4),
            "shares": shares,
            "cost": total_cost,
            "entryCommission": shares * execution_price * self.commission_rate,
        }

    def _close_position(self, row: dict[str, Any], index: int, reason: str) -> None:
        if self.position is None:
            return
        close = rule_value(row, "close") or float(self.position["entryPrice"])
        exit_price = close * (1 - self.slippage_rate)
        gross_revenue = int(self.position["shares"]) * exit_price
        exit_commission = gross_revenue * self.commission_rate
        stamp_duty = gross_revenue * self.stamp_duty_rate
        net_revenue = gross_revenue - exit_commission - stamp_duty
        self.cash += net_revenue
        profit = net_revenue - float(self.position["cost"])
        trade = {
            **self.position,
            "exitIndex": index,
            "exitTime": text_value(row, ["日期", "date", "datetime", "time"]),
            "exitPrice": round(exit_price, 4),
            "exitCommission": round(exit_commission, 2),
            "stampDuty": round(stamp_duty, 2),
            "profit": round(profit, 2),
            "returnPct": round(profit / float(self.position["cost"]) * 100, 2) if self.position["cost"] else 0,
            "holdingBars": index - int(self.position["entryIndex"]),
            "exitReason": reason,
        }
        self.trades.append(trade)
        self.position = None

    def _equity(self, close: float) -> float:
        return self.cash + (int(self.position["shares"]) * close if self.position else 0)

    def run(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        for index, row in enumerate(rows):
            close = rule_value(row, "close")
            if close is None:
                continue
            previous_row = rows[index - 1] if index else None
            if self.position is not None:
                entry_price = float(self.position["entryPrice"])
                change_pct = (close - entry_price) / entry_price * 100 if entry_price else 0
                held = index - int(self.position["entryIndex"])
                if self.payload.stop_loss_pct is not None and change_pct <= -abs(self.payload.stop_loss_pct):
                    self._close_position(row, index, "止损")
                elif self.payload.take_profit_pct is not None and change_pct >= abs(self.payload.take_profit_pct):
                    self._close_position(row, index, "止盈")
                elif self.payload.exit_rule and matches_backtest_rule(row, previous_row, self.payload.exit_rule):
                    self._close_position(row, index, "退出条件")
                elif held >= self.payload.exit_after_bars:
                    self._close_position(row, index, "持仓到期")
            if self.position is None and all(matches_backtest_rule(row, previous_row, rule) for rule in self.payload.rules):
                self._open_position(row, index, float(close))
            self.equity_curve.append({"time": text_value(row, ["日期", "date", "datetime", "time"]), "equity": round(self._equity(float(close)), 2), "drawdownPct": 0})
        if self.position is not None and rows:
            self._close_position(rows[-1], len(rows) - 1, "样本结束")
            if self.equity_curve:
                self.equity_curve[-1]["equity"] = round(self.cash, 2)
        peak = self.initial_capital
        max_drawdown = 0.0
        daily_returns: list[float] = []
        previous_equity = self.initial_capital
        for point in self.equity_curve:
            equity = float(point["equity"])
            peak = max(peak, equity)
            drawdown = (equity / peak - 1) * 100 if peak else 0
            point["drawdownPct"] = round(drawdown, 2)
            max_drawdown = min(max_drawdown, drawdown)
            if previous_equity:
                daily_returns.append(equity / previous_equity - 1)
            previous_equity = equity
        wins = [trade for trade in self.trades if float(trade["profit"]) > 0]
        losses = [trade for trade in self.trades if float(trade["profit"]) < 0]
        mean_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0
        variance = sum((value - mean_return) ** 2 for value in daily_returns) / len(daily_returns) if daily_returns else 0
        volatility = math.sqrt(variance)
        daily_risk_free = (1.03 ** (1 / 252)) - 1
        sharpe = ((mean_return - daily_risk_free) / volatility * math.sqrt(252)) if volatility else 0
        gain = sum(float(item["profit"]) for item in wins)
        loss = abs(sum(float(item["profit"]) for item in losses))
        total_return = (self.cash / self.initial_capital - 1) * 100
        periods = max(len(self.equity_curve), 1)
        annualized = ((self.cash / self.initial_capital) ** (252 / periods) - 1) * 100 if self.cash > 0 else -100.0
        return {
            "trades": self.trades,
            "equityCurve": self.equity_curve,
            "summary": {
                "bars": len(self.equity_curve),
                "trades": len(self.trades),
                "winRate": round(len(wins) / len(self.trades) * 100, 2) if self.trades else 0,
                "totalReturnPct": round(total_return, 2),
                "annualizedReturnPct": round(annualized, 2),
                "maxDrawdownPct": round(max_drawdown, 2),
                "sharpeRatio": round(sharpe, 2),
                "profitLossRatio": round(gain / loss, 2) if loss else (None if not gain else "∞"),
                "averageHoldingBars": round(sum(int(trade["holdingBars"]) for trade in self.trades) / len(self.trades), 1) if self.trades else 0,
                "finalEquity": round(self.cash, 2),
            },
        }


def benchmark_return(payload: BacktestRequest) -> float | None:
    benchmark = resilient_workbench_query("get_kline", {"code": "000300", "period": payload.period, "limit": payload.limit})
    if benchmark.get("status") != "success":
        return None
    rows = prepare_backtest_rows(records_from_data(benchmark.get("data")))
    closes = [rule_value(row, "close") for row in rows]
    values = [float(value) for value in closes if value is not None]
    return round((values[-1] / values[0] - 1) * 100, 2) if len(values) >= 2 and values[0] else None


def execute_backtest(payload: BacktestRequest) -> dict[str, Any]:
    code = normalize_watchlist_code(payload.code)
    if payload.limit < 40 or payload.limit > 1200:
        raise HTTPException(status_code=422, detail="回测 K 线数量必须在 40 到 1200 之间")
    if not payload.rules:
        raise HTTPException(status_code=422, detail="至少需要一个入场条件")
    if any(rule.value is None and rule.compare_field is None for rule in payload.rules):
        raise HTTPException(status_code=422, detail="每个入场条件都需要比较对象或阈值")
    kline = resilient_workbench_query("get_kline", {"code": code, "period": payload.period, "limit": payload.limit})
    if kline.get("status") != "success":
        return {"status": "error", "code": code, "error": kline.get("error", "K 线数据暂时不可用"), "source": kline.get("source"), "updatedAt": now_iso()}
    rows = prepare_backtest_rows(records_from_data(kline.get("data")))
    if len(rows) < 40:
        return {"status": "error", "code": code, "error": "可用 K 线不足，至少需要 40 个周期", "source": kline.get("source"), "updatedAt": now_iso()}
    result = Backtester(payload).run(rows)
    benchmark = benchmark_return(payload)
    summary = result["summary"]
    summary["benchmarkReturnPct"] = benchmark
    summary["excessReturnPct"] = round(float(summary["totalReturnPct"]) - benchmark, 2) if benchmark is not None else None
    return {
        "status": "success",
        "code": code,
        "strategyName": payload.strategy_name.strip()[:60] or "自定义策略",
        "source": kline.get("source"),
        "updatedAt": now_iso(),
        "summary": summary,
        "assumptions": {
            "initialCapital": payload.initial_capital,
            "positionPct": payload.position_pct,
            "commissionRate": max(0, min(payload.commission_rate, 0.02)),
            "stampDutyRate": max(0, min(payload.stamp_duty_rate, 0.02)),
            "slippageRate": max(0, min(payload.slippage_rate, 0.02)),
            "takeProfitPct": payload.take_profit_pct,
            "stopLossPct": payload.stop_loss_pct,
            "maxHoldingBars": payload.exit_after_bars,
        },
        **result,
    }


@app.post("/agent/strategy/backtest")
def backtest_strategy(payload: BacktestRequest) -> dict[str, Any]:
    return execute_backtest(payload)


def backtest_report_pdf(result: dict[str, Any]) -> bytes:
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=17 * mm, bottomMargin=17 * mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("BacktestTitle", parent=styles["Title"], fontName="STSong-Light", fontSize=18, leading=25, textColor=colors.HexColor("#123047"))
    heading = ParagraphStyle("BacktestHeading", parent=styles["Heading2"], fontName="STSong-Light", fontSize=12, leading=18, textColor=colors.HexColor("#0f766e"), spaceBefore=9, spaceAfter=5)
    body = ParagraphStyle("BacktestBody", parent=styles["BodyText"], fontName="STSong-Light", fontSize=9, leading=14, textColor=colors.HexColor("#334155"))
    story = [Paragraph(f"回测报告：{result.get('strategyName', '自定义策略')}", title), Spacer(1, 4 * mm)]
    summary = result.get("summary") or {}
    assumptions = result.get("assumptions") or {}
    story.append(Paragraph(f"标的：{result.get('code', '—')}　生成时间：{format_date_for_report(result.get('updatedAt'))}　数据源：{result.get('source') or '本地数据服务'}", body))
    story.append(Paragraph("核心指标", heading))
    metrics = [
        ["总收益率", f"{summary.get('totalReturnPct', 0)}%", "年化收益率", f"{summary.get('annualizedReturnPct', 0)}%"],
        ["最大回撤", f"{summary.get('maxDrawdownPct', 0)}%", "夏普比率", str(summary.get('sharpeRatio', 0))],
        ["沪深 300", f"{summary.get('benchmarkReturnPct')}%" if summary.get('benchmarkReturnPct') is not None else "暂无", "超额收益", f"{summary.get('excessReturnPct')}%" if summary.get('excessReturnPct') is not None else "暂无"],
        ["交易次数", str(summary.get('trades', 0)), "胜率", f"{summary.get('winRate', 0)}%"],
        ["盈亏比", str(summary.get('profitLossRatio') or "—"), "平均持仓", f"{summary.get('averageHoldingBars', 0)} 个周期"],
    ]
    metric_table = Table(metrics, colWidths=[28 * mm, 45 * mm, 28 * mm, 45 * mm])
    metric_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")), ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#64748b")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story += [metric_table, Paragraph("回测假设", heading), Paragraph(f"初始资金 {assumptions.get('initialCapital', 0):,.0f} 元；仓位 {assumptions.get('positionPct', 0) * 100:.0f}%；佣金 {assumptions.get('commissionRate', 0) * 100:.3f}%；印花税 {assumptions.get('stampDutyRate', 0) * 100:.3f}%；滑点 {assumptions.get('slippageRate', 0) * 100:.2f}%；最大持仓 {assumptions.get('maxHoldingBars', 0)} 个周期。", body), Paragraph("交易明细", heading)]
    trade_rows = [["买入日期", "买入价", "卖出日期", "卖出价", "收益", "退出原因"]]
    for trade in (result.get("trades") or [])[:30]:
        trade_rows.append([str(trade.get("entryTime") or "—"), str(trade.get("entryPrice") or "—"), str(trade.get("exitTime") or "—"), str(trade.get("exitPrice") or "—"), f"{trade.get('returnPct', 0)}%", str(trade.get("exitReason") or "—")])
    trade_table = Table(trade_rows, repeatRows=1, colWidths=[31 * mm, 24 * mm, 31 * mm, 24 * mm, 20 * mm, 31 * mm])
    trade_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123047")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [trade_table, Spacer(1, 6 * mm), Paragraph("风险提示：回测基于历史数据，已计入设定的佣金、印花税和滑点，但不代表未来表现，也不构成投资建议。", body)]
    document.build(story)
    return buffer.getvalue()


def format_date_for_report(value: Any) -> str:
    return str(value or now_iso()).replace("T", " ")[:19]


@app.post("/agent/strategy/backtest/report")
def download_backtest_report(payload: BacktestReportRequest) -> StreamingResponse:
    result = execute_backtest(payload.backtest)
    if result.get("status") != "success":
        raise HTTPException(status_code=422, detail=result.get("error", "无法生成回测报告"))
    filename = f"backtest-report-{result['code']}.pdf"
    return StreamingResponse(iter([backtest_report_pdf(result)]), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def research_note_view(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return dict(row)


@app.get("/agent/research/notes/{code}")
def get_research_note(code: str) -> dict[str, Any] | None:
    connection = app_database()
    try:
        row = connection.execute("SELECT * FROM research_notes WHERE code = ?", (normalize_watchlist_code(code),)).fetchone()
        return research_note_view(row) if row else None
    finally:
        connection.close()


@app.put("/agent/research/notes")
def save_research_note(payload: ResearchNoteUpsert) -> dict[str, Any]:
    timestamp = now_iso()
    note = {
        "code": normalize_watchlist_code(payload.code),
        "title": clean_text(payload.title)[:80],
        "thesis": clean_text(payload.thesis)[:4000],
        "risks": clean_text(payload.risks)[:3000],
        "key_metrics": clean_text(payload.key_metrics)[:3000],
        "reminders": clean_text(payload.reminders)[:3000],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    connection = app_database()
    try:
        connection.execute(
            """
            INSERT INTO research_notes (code, title, thesis, risks, key_metrics, reminders, created_at, updated_at)
            VALUES (:code, :title, :thesis, :risks, :key_metrics, :reminders, :created_at, :updated_at)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title, thesis = excluded.thesis, risks = excluded.risks,
                key_metrics = excluded.key_metrics, reminders = excluded.reminders,
                updated_at = excluded.updated_at
            """,
            note,
        )
        connection.commit()
        row = connection.execute("SELECT * FROM research_notes WHERE code = ?", (note["code"],)).fetchone()
        return research_note_view(row)
    finally:
        connection.close()


@app.get("/agent/research/decisions")
def list_investment_decisions(code: str = Query(..., min_length=6, max_length=8)) -> list[dict[str, Any]]:
    connection = app_database()
    try:
        rows = connection.execute(
            "SELECT * FROM investment_decisions WHERE code = ? ORDER BY created_at DESC",
            (normalize_watchlist_code(code),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.post("/agent/research/decisions")
def create_investment_decision(payload: InvestmentDecisionCreate) -> dict[str, Any]:
    decision = {
        "id": str(uuid.uuid4()),
        "code": normalize_watchlist_code(payload.code),
        "action": payload.action,
        "shares": max(0, payload.shares or 0) or None,
        "price": max(0, payload.price or 0) or None,
        "rationale": required_text(payload.rationale, "决策依据", 3000),
        "target_or_stop": clean_text(payload.target_or_stop)[:1000],
        "review": clean_text(payload.review)[:2000],
        "created_at": now_iso(),
    }
    connection = app_database()
    try:
        connection.execute(
            """INSERT INTO investment_decisions
            (id, code, action, shares, price, rationale, target_or_stop, review, created_at)
            VALUES (:id, :code, :action, :shares, :price, :rationale, :target_or_stop, :review, :created_at)""",
            decision,
        )
        connection.commit()
        return decision
    finally:
        connection.close()


@app.get("/agent/research/strategy-versions")
def list_strategy_versions(strategy_id: str | None = None) -> list[dict[str, Any]]:
    connection = app_database()
    try:
        if strategy_id:
            rows = connection.execute(
                "SELECT * FROM strategy_versions WHERE strategy_id = ? ORDER BY created_at DESC",
                (strategy_id,),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM strategy_versions ORDER BY created_at DESC LIMIT 60").fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.post("/agent/research/strategy-versions")
def create_strategy_version(payload: StrategyVersionCreate) -> dict[str, Any]:
    item = {
        "id": str(uuid.uuid4()),
        "strategy_id": payload.strategy_id or None,
        "strategy_name": required_text(payload.strategy_name, "策略名称", 80),
        "version": required_text(payload.version, "版本号", 30),
        "change_summary": required_text(payload.change_summary, "变更内容", 2000),
        "rationale": clean_text(payload.rationale)[:2000],
        "backtest_summary": clean_text(payload.backtest_summary)[:2000],
        "created_at": now_iso(),
    }
    connection = app_database()
    try:
        connection.execute(
            """INSERT INTO strategy_versions
            (id, strategy_id, strategy_name, version, change_summary, rationale, backtest_summary, created_at)
            VALUES (:id, :strategy_id, :strategy_name, :version, :change_summary, :rationale, :backtest_summary, :created_at)""",
            item,
        )
        connection.commit()
        return item
    finally:
        connection.close()


def compact_report_source(result: dict[str, Any], label: str) -> str:
    if result.get("status") != "success":
        return f"{label}：暂不可用（{result.get('error', '数据源未返回')}）"
    rows = records_from_data(result.get("data"))[:3]
    sample = json.dumps(rows, ensure_ascii=False, default=str)[:1800]
    return f"{label}（{result.get('source') or '本地数据服务'}）：{sample}"


def deterministic_research_report(code: str, report_type: str, sources: list[str], generated_at: str) -> str:
    type_name = {"fundamental": "基本面深度分析", "technical": "技术面趋势判断", "event": "事件影响评估"}[report_type]
    return f"""# {code} 股票研究报告

生成时间：{format_date_for_report(generated_at)}
报告类型：{type_name}

## 一、基本信息
- 标的代码：{code}
- 数据范围：行情、财务快照、K 线与公告研报（以各数据源返回时间为准）

## 二、核心观点
- 本报告基于本机可获得的数据生成，需结合最新公告与财报继续验证。
- 仅用于研究记录，不构成买卖建议或收益承诺。

## 三、财务与经营观察
- 关注营收、利润、现金流和估值指标的趋势变化，并与历史区间交叉验证。

## 四、技术面与交易观察
- 关注均线位置、成交量变化、关键支撑与压力区域；历史走势不代表未来表现。

## 五、资讯与后续验证
- 跟踪公告、业绩预告、机构调研和行业政策的新增信息。
- 对异常波动、数据缺失及来源延迟保持审慎。

## 六、风险提示
- 市场波动、公司基本面变化、数据时效性和模型误差均可能导致结论失效。

## 数据摘要
{chr(10).join(f'- {source}' for source in sources)}
"""


def research_report_pdf(report: dict[str, Any]) -> bytes:
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=17 * mm, bottomMargin=17 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ResearchReportTitle", parent=styles["Title"], fontName="STSong-Light", fontSize=17, leading=24, textColor=colors.HexColor("#123047"))
    body_style = ParagraphStyle("ResearchReportBody", parent=styles["BodyText"], fontName="STSong-Light", fontSize=9, leading=14, textColor=colors.HexColor("#334155"), spaceAfter=5)
    story: list[Any] = [Paragraph(html.escape(str(report.get("title") or "股票研究报告")), title_style), Spacer(1, 4 * mm)]
    for raw_line in str(report.get("content") or "").replace("\r", "").split("\n"):
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 2 * mm))
            continue
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            heading = ParagraphStyle("ResearchHeading", parent=body_style, fontSize=12, leading=18, textColor=colors.HexColor("#0f766e"), spaceBefore=7, spaceAfter=3)
            story.append(Paragraph(html.escape(line[3:]), heading))
        else:
            story.append(Paragraph(html.escape(line).replace("- ", "• ", 1), body_style))
    document.build(story)
    return buffer.getvalue()


@app.get("/agent/research/reports")
def list_research_reports(code: str = Query(..., min_length=6, max_length=8)) -> list[dict[str, Any]]:
    connection = app_database()
    try:
        rows = connection.execute(
            "SELECT * FROM research_reports WHERE code = ? ORDER BY created_at DESC",
            (normalize_watchlist_code(code),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.post("/agent/research/reports/generate")
def generate_research_report(payload: ResearchReportGenerate) -> dict[str, Any]:
    code = normalize_watchlist_code(payload.code)
    query_specs = [
        ("行情", "get_market_quote", {"codes": [code]}),
        ("财务快照", "get_finance_snapshot", {"code": code}),
        ("日线", "get_kline", {"code": code, "period": "day", "limit": 120}),
        ("公告研报", "get_stock_reports", {"code": code, "max_pages": 1}),
    ]
    sources: list[str] = []
    for label, tool, arguments in query_specs:
        try:
            sources.append(compact_report_source(resilient_workbench_query(tool, arguments), label))
        except Exception as error:
            sources.append(f"{label}：读取失败（{str(error)[:120]}）")
    if payload.news_id is not None:
        connection = database()
        try:
            news = connection.execute("SELECT title, summary, source_name, published_at FROM news WHERE id = ?", (payload.news_id,)).fetchone()
        finally:
            connection.close()
        if news:
            sources.append(f"关联资讯（{news['source_name']}）：{news['title']} {news['summary'][:600]}")
    timestamp = now_iso()
    type_name = {"fundamental": "基本面深度分析", "technical": "技术面趋势判断", "event": "事件影响评估"}[payload.report_type]
    prompt = f"""请基于以下本地数据为 A 股 {code} 编写《{type_name}》研究报告。严格使用 Markdown，包含：基本信息、核心观点、财务与经营观察、技术面与交易观察、资讯与后续验证、风险提示。只做研究分析，不给出买卖建议、目标价或仓位建议；对数据缺失和时效性明确提示。\n\n{chr(10).join(sources)}"""
    try:
        content, _ = provider_response(payload.model, [{"role": "user", "content": prompt}], [])
        if len(content.strip()) < 80:
            raise ValueError("AI 返回内容不足")
    except Exception:
        content = deterministic_research_report(code, payload.report_type, sources, timestamp)
    report = {
        "id": str(uuid.uuid4()),
        "code": code,
        "report_type": payload.report_type,
        "title": f"{code} {type_name}",
        "content": content.strip(),
        "source_summary": "\n".join(sources),
        "created_at": timestamp,
    }
    connection = app_database()
    try:
        connection.execute(
            """INSERT INTO research_reports (id, code, report_type, title, content, source_summary, created_at)
            VALUES (:id, :code, :report_type, :title, :content, :source_summary, :created_at)""",
            report,
        )
        connection.commit()
        return report
    finally:
        connection.close()


@app.get("/agent/research/reports/{report_id}/pdf")
def download_research_report(report_id: str) -> StreamingResponse:
    connection = app_database()
    try:
        row = connection.execute("SELECT * FROM research_reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="研究报告不存在")
        report = dict(row)
    finally:
        connection.close()
    return StreamingResponse(
        iter([research_report_pdf(report)]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="research-report-{report["code"]}.pdf"'},
    )


def _json_list(value: Any, fallback: list[Any] | None = None) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else (fallback or [])
        except json.JSONDecodeError:
            return fallback or []
    return fallback or []


def normalize_strategy_conditions(payload: StrategyCreate) -> list[dict[str, Any]]:
    conditions = [condition.model_dump(exclude_none=True) for condition in payload.conditions]
    if conditions:
        return conditions
    return [{"field": payload.field, "operator": payload.operator, "value": payload.value}]


def strategy_view(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["weight"] = float(item["weight"])
    item["interval_seconds"] = max(60, int(item.get("interval_seconds") or 300))
    item["conditions"] = _json_list(item.get("conditions_json"), [{"field": item["field"], "operator": item["operator"], "value": item["value"]}])
    item["actions"] = [str(action) for action in _json_list(item.get("actions_json")) if str(action).strip()]
    item["schedule"] = {
        "mode": item.get("schedule_mode") or "manual",
        "intervalSeconds": item["interval_seconds"],
        "at": item.get("schedule_at") or "",
    }
    return item


def _condition_result(condition: dict[str, Any], row: dict[str, Any], previous_row: dict[str, Any] | None) -> dict[str, Any]:
    field = str(condition.get("field") or "price")
    operator = str(condition.get("operator") or "gte")
    current = rule_value(row, field)
    previous = rule_value(previous_row, field) if previous_row else None
    compare_field = condition.get("compare_field")
    threshold = float(condition["value"]) if condition.get("value") is not None else None
    current_right = rule_value(row, str(compare_field)) if compare_field else threshold
    previous_right = rule_value(previous_row, str(compare_field)) if compare_field and previous_row else threshold
    if current is None or current_right is None:
        matched = False
    elif operator == "cross_up":
        matched = previous is not None and previous_right is not None and previous < previous_right <= current
    elif operator == "cross_down":
        matched = previous is not None and previous_right is not None and previous > previous_right >= current
    else:
        matched = operator_match(float(current), operator, float(current_right))
    detail_right = compare_field or threshold
    return {
        "field": field,
        "operator": operator,
        "value": detail_right,
        "observedValue": current,
        "matched": matched,
        "detail": f"{field} {operator} {detail_right}",
    }


def evaluate_strategy(strategy: dict[str, Any]) -> dict[str, Any]:
    conditions = strategy.get("conditions") or [{"field": strategy["field"], "operator": strategy["operator"], "value": strategy["value"]}]
    quote = resilient_workbench_query("get_market_quote", {"codes": [strategy["code"]]})
    quote_rows = records_from_data(quote.get("data")) if quote.get("status") == "success" else []
    needs_kline = any(condition.get("field") not in {"price", "pct"} or condition.get("compare_field") not in {None, "price", "pct"} for condition in conditions)
    kline = resilient_workbench_query("get_kline", {"code": strategy["code"], "period": "day", "limit": 120}) if needs_kline else None
    rows = records_from_data(kline.get("data")) if kline and kline.get("status") == "success" else quote_rows
    current_row = rows[-1] if rows else (quote_rows[0] if quote_rows else {})
    previous_row = rows[-2] if len(rows) > 1 else None
    condition_results = [_condition_result(condition, current_row, previous_row) for condition in conditions]
    matched = bool(condition_results) and all(item["matched"] for item in condition_results)
    sources = [source for source in [quote.get("source"), kline.get("source") if kline else None] if source]
    result = {
        "strategyId": strategy["id"],
        "name": strategy["name"],
        "code": strategy["code"],
        "matched": matched,
        "observedValue": condition_results[0]["observedValue"] if condition_results else None,
        "source": ", ".join(dict.fromkeys(sources)),
        "detail": " 且 ".join(item["detail"] for item in condition_results),
        "status": "success" if quote.get("status") == "success" or (kline and kline.get("status") == "success") else "error",
        "conditions": condition_results,
        "schedule": strategy.get("schedule"),
        "actions": strategy.get("actions", []),
    }
    connection = app_database()
    try:
        timestamp = now_iso()
        connection.execute("INSERT INTO strategy_runs (id, strategy_id, matched, observed_value, source, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), strategy["id"], 1 if matched else 0, result["observedValue"], result["source"], result["detail"], timestamp))
        connection.execute("UPDATE strategies SET last_run_at = ?, last_triggered_at = CASE WHEN ? = 1 THEN ? ELSE last_triggered_at END, updated_at = ? WHERE id = ?", (timestamp, 1 if matched else 0, timestamp, timestamp, strategy["id"]))
        connection.commit()
    finally:
        connection.close()
    return result


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.S | re.I)
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _operator_from_text(text: str) -> str:
    if re.search(r"(上穿|突破|高于|大于|超过|涨到|不少于|>=|≥)", text):
        return "cross_up" if "上穿" in text else "gte" if "不少于" in text or "≥" in text else "gt"
    if re.search(r"(下穿|跌破|低于|小于|不高于|<=|≤)", text):
        return "cross_down" if "下穿" in text else "lte" if "不高于" in text or "≤" in text else "lt"
    return "gte"


def deterministic_strategy_draft(prompt: str) -> dict[str, Any]:
    code_match = re.search(r"(?:sh|sz|bj)?(\d{6})", prompt, re.I)
    if not code_match:
        raise HTTPException(status_code=422, detail="自然语言策略中没有找到六位股票代码")
    code = code_match.group(1)
    conditions: list[dict[str, Any]] = []
    segments = re.split(r"(?:且|并且|同时|以及|，|,|;|；)", prompt)
    field_words = {"pct": r"涨跌幅|涨幅|跌幅|百分比", "volume": r"成交量|放量|缩量", "ma5": r"MA5", "ma10": r"MA10", "ma20": r"MA20", "price": r"价格|股价|收盘|现价"}
    for segment in segments:
        field_match = next(((key, re.search(pattern, segment, re.I)) for key, pattern in field_words.items() if re.search(pattern, segment, re.I)), None)
        if not field_match:
            continue
        field, matched_field = field_match
        ma_fields = re.findall(r"MA(?:5|10|20)", segment, re.I)
        compare = ma_fields[1] if len(ma_fields) > 1 else None
        number_match = re.search(r"-?\d+(?:\.\d+)?", segment[matched_field.end() :])
        if not number_match and not compare:
            continue
        condition: dict[str, Any] = {"field": field, "operator": _operator_from_text(segment)}
        if compare and condition["operator"] in {"cross_up", "cross_down"}:
            condition["compare_field"] = compare.lower()
        elif number_match:
            condition["value"] = float(number_match.group(0))
        else:
            continue
        conditions.append(condition)
    if not conditions:
        raise HTTPException(status_code=422, detail="没有识别出可执行条件，例如：600519 价格高于 1500 且涨跌幅大于 2%")
    interval_match = re.search(r"每\s*(\d+)\s*(秒|分钟|分|小时)", prompt)
    schedule_mode = "condition" if re.search(r"触发|一旦|当行情|满足条件", prompt) else "manual"
    interval_seconds = 300
    if interval_match:
        amount = int(interval_match.group(1))
        interval_seconds = amount * ({"秒": 1, "分钟": 60, "分": 60, "小时": 3600}[interval_match.group(2)])
        schedule_mode = "interval"
    time_match = re.search(r"每天[^\d]*(\d{1,2})[:点时](\d{2})?", prompt)
    schedule_at = ""
    if time_match:
        schedule_mode = "time-point"
        schedule_at = f"{int(time_match.group(1)):02d}:{int(time_match.group(2) or 0):02d}"
    strategy_type = "risk" if re.search(r"风控|风险|止损", prompt) else "timing" if re.search(r"择时|尾盘|开盘|金叉|死叉", prompt) else "selection"
    actions = ["记录决策"]
    if re.search(r"提醒|通知", prompt):
        actions.append("生成提醒记录")
    if re.search(r"复盘", prompt):
        actions.append("加入复盘队列")
    return {"name": prompt[:24], "type": strategy_type, "code": code, "conditions": conditions, "mode": "weighted", "weight": 1, "schedule_mode": schedule_mode, "interval_seconds": max(60, min(interval_seconds, 86400)), "schedule_at": schedule_at, "analysis_prompt": prompt, "actions": actions, "source": "agent"}


def draft_strategy_from_prompt(prompt: str, model: ChatProvider) -> dict[str, Any]:
    clean_prompt = required_text(prompt, "策略描述", 500)
    schema_prompt = f"请把下面的股票策略描述转换为严格 JSON，不要输出 Markdown、解释或工具调用。JSON 字段必须为 name,type,code,conditions,mode,weight,schedule_mode,interval_seconds,schedule_at,analysis_prompt,actions,source；conditions 是 field/operator/value/compare_field 数组，field 只能是 price,pct,volume,ma5,ma10,ma20，operator 只能是 gt,gte,lt,lte,cross_up,cross_down；schedule_mode 只能是 manual,interval,time-point,condition。描述：{clean_prompt}"
    try:
        answer, _ = provider_response(model, [{"role": "user", "content": schema_prompt}], [])
        parsed = _extract_json_object(answer)
        if parsed and parsed.get("code") and parsed.get("conditions"):
            parsed["analysis_prompt"] = clean_prompt
            parsed["source"] = "agent"
            return parsed
    except HTTPException:
        pass
    return deterministic_strategy_draft(clean_prompt)


@app.get("/agent/strategies")
def list_strategies() -> list[dict[str, Any]]:
    connection = app_database()
    try:
        rows = connection.execute("SELECT * FROM strategies ORDER BY updated_at DESC").fetchall()
        return [strategy_view(row) for row in rows]
    finally:
        connection.close()


@app.post("/agent/strategies")
def create_strategy(payload: StrategyCreate) -> dict[str, Any]:
    timestamp = now_iso()
    conditions = normalize_strategy_conditions(payload)
    first_condition = conditions[0]
    if payload.schedule_mode == "time-point" and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", payload.schedule_at):
        raise HTTPException(status_code=422, detail="定时策略需要填写 HH:MM 格式的运行时间")
    strategy = {
        "id": str(uuid.uuid4()), "name": required_text(payload.name, "策略名称", 60), "type": payload.type,
        "code": normalize_watchlist_code(payload.code), "field": first_condition["field"], "operator": first_condition["operator"],
        "value": float(first_condition.get("value") or 0), "mode": payload.mode, "weight": max(0.1, min(payload.weight, 10)),
        "status": "active", "conditions_json": json.dumps(conditions, ensure_ascii=False), "schedule_mode": payload.schedule_mode,
        "interval_seconds": max(60, min(payload.interval_seconds, 86400)), "schedule_at": payload.schedule_at,
        "analysis_prompt": clean_text(payload.analysis_prompt)[:500], "actions_json": json.dumps([clean_text(action)[:80] for action in payload.actions if clean_text(action)], ensure_ascii=False),
        "source": payload.source, "created_at": timestamp, "updated_at": timestamp,
    }
    connection = app_database()
    try:
        connection.execute(
            """
            INSERT INTO strategies
            (id, name, type, code, field, operator, value, mode, weight, status, conditions_json, schedule_mode,
             interval_seconds, schedule_at, analysis_prompt, actions_json, source, created_at, updated_at)
            VALUES
            (:id, :name, :type, :code, :field, :operator, :value, :mode, :weight, :status, :conditions_json, :schedule_mode,
             :interval_seconds, :schedule_at, :analysis_prompt, :actions_json, :source, :created_at, :updated_at)
            """,
            strategy,
        )
        connection.commit()
        return strategy_view(strategy)
    finally:
        connection.close()


@app.post("/agent/strategies/draft")
def draft_strategy(payload: StrategyDraftRequest) -> dict[str, Any]:
    draft = draft_strategy_from_prompt(payload.prompt, payload.model)
    try:
        validated = StrategyCreate.model_validate(draft)
    except Exception:
        fallback = deterministic_strategy_draft(payload.prompt)
        validated = StrategyCreate.model_validate(fallback)
    return {
        "draft": {
            "name": validated.name, "type": validated.type, "code": normalize_watchlist_code(validated.code),
            "conditions": [condition.model_dump(exclude_none=True) for condition in validated.conditions], "mode": validated.mode,
            "weight": validated.weight, "schedule_mode": validated.schedule_mode, "interval_seconds": validated.interval_seconds,
            "schedule_at": validated.schedule_at, "analysis_prompt": validated.analysis_prompt, "actions": validated.actions, "source": validated.source,
        }
    }


@app.patch("/agent/strategies/{strategy_id}")
def update_strategy(strategy_id: str, payload: StrategyUpdate) -> dict[str, Any]:
    connection = app_database()
    try:
        result = connection.execute("UPDATE strategies SET status = ?, updated_at = ? WHERE id = ?", (payload.status, now_iso(), strategy_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="策略不存在")
        connection.commit()
        return strategy_view(connection.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone())
    finally:
        connection.close()


@app.delete("/agent/strategies/{strategy_id}")
def delete_strategy(strategy_id: str) -> dict[str, str]:
    connection = app_database()
    try:
        result = connection.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="策略不存在")
        connection.commit()
        return {"status": "deleted", "id": strategy_id}
    finally:
        connection.close()


@app.post("/agent/strategies/{strategy_id}/run")
def run_strategy(strategy_id: str) -> dict[str, Any]:
    connection = app_database()
    try:
        row = connection.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="策略不存在")
        strategy = strategy_view(row)
    finally:
        connection.close()
    return evaluate_strategy(strategy)


def build_strategy_decision(trigger_source: str = "manual") -> dict[str, Any]:
    connection = app_database()
    try:
        strategies = [strategy_view(row) for row in connection.execute("SELECT * FROM strategies WHERE status = 'active' ORDER BY created_at").fetchall()]
    finally:
        connection.close()
    if not strategies:
        raise HTTPException(status_code=422, detail="请先创建并启用至少一条策略")
    results = [evaluate_strategy(strategy) for strategy in strategies]
    modes = {strategy["mode"] for strategy in strategies}
    mode = "veto" if "veto" in modes else "consensus" if modes == {"consensus"} else "weighted"
    matched_weight = sum(strategy["weight"] for strategy, result in zip(strategies, results) if result["matched"])
    total_weight = sum(strategy["weight"] for strategy in strategies)
    rating = round(matched_weight / total_weight * 100) if total_weight else 0
    if mode == "veto" and any(strategy["type"] == "risk" and result["matched"] for strategy, result in zip(strategies, results)):
        conclusion = "风险策略命中，当前结论为谨慎观察"
        rating = 0
    elif mode == "consensus":
        conclusion = "全部条件一致" if all(result["matched"] for result in results) else "条件未形成一致，继续观察"
    else:
        conclusion = "多策略条件形成较高一致" if rating >= 60 else "多策略条件尚未形成一致，继续观察"
    tree = [{"step": f"{result['name']} · {result['code']}", "result": f"{'命中' if result['matched'] else '未命中'}：{result['detail']}"} for result in results]
    risks = [f"{result['name']} 的风控条件命中" for strategy, result in zip(strategies, results) if strategy["type"] == "risk" and result["matched"]]
    catalysts = [f"{result['name']} 条件命中" for strategy, result in zip(strategies, results) if strategy["type"] != "risk" and result["matched"]]
    decision = {"id": str(uuid.uuid4()), "mode": mode, "rating": rating, "conclusion": conclusion, "tree": tree, "risks": risks, "catalysts": catalysts, "triggerSource": trigger_source, "createdAt": now_iso(), "subDecisions": results}
    connection = app_database()
    try:
        connection.execute(
            "INSERT INTO strategy_decisions (id, mode, rating, conclusion, tree_json, trigger_source, risks_json, catalysts_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (decision["id"], mode, rating, conclusion, json.dumps(tree, ensure_ascii=False), trigger_source, json.dumps(risks, ensure_ascii=False), json.dumps(catalysts, ensure_ascii=False), decision["createdAt"]),
        )
        connection.commit()
    finally:
        connection.close()
    return decision


@app.post("/agent/strategies/decision")
def decide_strategies() -> dict[str, Any]:
    return build_strategy_decision("manual")


_strategy_scheduler_stop = threading.Event()
_strategy_scheduler_lock = threading.Lock()


def strategy_is_due(strategy: dict[str, Any], local_now: datetime) -> tuple[bool, str | None]:
    schedule = strategy.get("schedule") or {}
    mode = schedule.get("mode", "manual")
    if mode == "manual":
        return False, None
    if mode == "time-point":
        at = schedule.get("at") or ""
        run_key = f"{local_now.date().isoformat()}T{at}"
        return bool(at and local_now.strftime("%H:%M") >= at and strategy.get("last_scheduled_for") != run_key), run_key
    last_run = strategy.get("last_run_at")
    if not last_run:
        return True, None
    try:
        elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(str(last_run))
        return elapsed >= timedelta(seconds=int(schedule.get("intervalSeconds") or 300)), None
    except ValueError:
        return True, None


def run_strategy_scheduler_once() -> int:
    if not _strategy_scheduler_lock.acquire(blocking=False):
        return 0
    try:
        connection = app_database()
        try:
            strategies = [strategy_view(row) for row in connection.execute("SELECT * FROM strategies WHERE status = 'active' ORDER BY created_at").fetchall()]
        finally:
            connection.close()
        triggered = 0
        for strategy in strategies:
            due, run_key = strategy_is_due(strategy, datetime.now())
            if not due:
                continue
            result = evaluate_strategy(strategy)
            if run_key:
                connection = app_database()
                try:
                    connection.execute("UPDATE strategies SET last_scheduled_for = ? WHERE id = ?", (run_key, strategy["id"]))
                    connection.commit()
                finally:
                    connection.close()
            if result["matched"]:
                triggered += 1
                build_strategy_decision("scheduler")
        return triggered
    finally:
        _strategy_scheduler_lock.release()


def strategy_scheduler_loop() -> None:
    while not _strategy_scheduler_stop.wait(15):
        try:
            run_strategy_scheduler_once()
            maybe_create_scheduled_backup()
        except Exception:
            # A temporary data-source error must not stop later strategy checks.
            continue


@app.on_event("startup")
def start_strategy_scheduler() -> None:
    _strategy_scheduler_stop.clear()
    try:
        maybe_create_scheduled_backup()
    except Exception:
        # Backup errors must not prevent local research data from opening.
        pass
    if not getattr(app.state, "strategy_scheduler", None):
        app.state.strategy_scheduler = threading.Thread(target=strategy_scheduler_loop, name="strategy-scheduler", daemon=True)
        app.state.strategy_scheduler.start()


@app.on_event("shutdown")
def stop_strategy_scheduler() -> None:
    _strategy_scheduler_stop.set()


@app.get("/agent/alerts")
def list_alerts() -> list[dict[str, Any]]:
    connection = app_database()
    try:
        rows = connection.execute("SELECT * FROM price_alerts ORDER BY created_at DESC").fetchall()
        return [{**dict(row), "enabled": bool(row["enabled"])} for row in rows]
    finally:
        connection.close()


@app.post("/agent/alerts")
def create_alert(payload: AlertCreate) -> dict[str, Any]:
    alert = {
        "id": str(uuid.uuid4()),
        "code": normalize_watchlist_code(payload.code),
        "name": clean_text(payload.name)[:80],
        "field": clean_text(payload.field)[:40] or "price",
        "operator": payload.operator,
        "value": payload.value,
        "enabled": 1 if payload.enabled else 0,
        "created_at": now_iso(),
    }
    connection = app_database()
    try:
        connection.execute(
            """
            INSERT INTO price_alerts (id, code, name, field, operator, value, enabled, created_at)
            VALUES (:id, :code, :name, :field, :operator, :value, :enabled, :created_at)
            """,
            alert,
        )
        connection.commit()
        return {**alert, "enabled": bool(alert["enabled"])}
    finally:
        connection.close()


@app.delete("/agent/alerts/{alert_id}")
def delete_alert(alert_id: str) -> dict[str, str]:
    connection = app_database()
    try:
        result = connection.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="提醒不存在")
        connection.commit()
        return {"status": "deleted", "id": alert_id}
    finally:
        connection.close()


@app.post("/agent/alerts/check")
def check_alerts() -> dict[str, Any]:
    connection = app_database()
    try:
        rows = connection.execute("SELECT * FROM price_alerts WHERE enabled = 1 ORDER BY created_at DESC").fetchall()
        results = []
        for row in rows:
            alert = dict(row)
            quote = resilient_workbench_query("get_market_quote", {"codes": [alert["code"]]})
            records = records_from_data(quote.get("data")) if quote.get("status") == "success" else []
            current = rule_value(records[0], alert["field"]) if records else None
            triggered = current is not None and operator_match(float(current), alert["operator"], float(alert["value"]))
            timestamp = now_iso()
            connection.execute(
                """
                UPDATE price_alerts
                SET last_checked_at = ?, last_value = ?, triggered_at = CASE WHEN ? THEN ? ELSE triggered_at END
                WHERE id = ?
                """,
                (timestamp, current, 1 if triggered else 0, timestamp, alert["id"]),
            )
            results.append({**alert, "enabled": bool(alert["enabled"]), "status": quote.get("status"), "source": quote.get("source"), "currentValue": current, "triggered": triggered, "checkedAt": timestamp, "error": quote.get("error")})
        connection.commit()
        return {"status": "success", "checked": len(results), "triggered": [item for item in results if item["triggered"]], "items": results}
    finally:
        connection.close()


@app.post("/agent/workbench/query")
def workbench_query(payload: WorkbenchQuery) -> dict[str, Any]:
    """Run one allow-listed stock-data tool for the visual workbench."""
    return resilient_workbench_query(payload.tool, payload.arguments)


@app.get("/taxonomy")
def taxonomy() -> dict[str, Any]:
    return taxonomy_data()


@app.get("/sources")
def sources() -> list[dict[str, Any]]:
    connection = database()
    configured = load_json(SOURCES_PATH).get("sources", [])
    rows = connection.execute("SELECT * FROM source_health ORDER BY source_name").fetchall()
    connection.close()
    by_id = {row["source_id"]: dict(row) for row in rows}
    now = datetime.now(timezone.utc)
    source_items = [
        by_id.get(
            source["id"],
            {
                "source_id": source["id"],
                "source_name": source["name"],
                "status": "pending",
                "item_count": 0,
                "detail": "数据源待接入",
                "last_checked_at": None,
            },
        )
        for source in configured
    ]
    for item in source_items:
        success_at = item.get("last_success_at") or item.get("last_checked_at")
        try:
            delay_minutes = max(0, round((now - datetime.fromisoformat(str(success_at).replace("Z", "+00:00"))).total_seconds() / 60)) if success_at else None
        except ValueError:
            delay_minutes = None
        item["last_success_at"] = item.get("last_success_at")
        item["delay_minutes"] = delay_minutes
        item["is_stale"] = item.get("status") == "ok" and (delay_minutes is None or delay_minutes > 120)
    return source_items


@app.get("/news")
def news(
    primary_sector: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    connection = database()
    configured_sources = load_json(SOURCES_PATH).get("sources", [])
    source_ids = [source["id"] for source in configured_sources]
    clauses = [f"source_id IN ({','.join('?' for _ in source_ids)})"] if source_ids else ["1 = 0"]
    params: list[Any] = list(source_ids)
    if primary_sector:
        clauses.append("primary_sector = ?")
        params.append(primary_sector)
    if industry:
        clauses.append("industry = ?")
        params.append(industry)
    if topic:
        clauses.append("topics LIKE ?")
        params.append(f'%"{topic}"%')
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"SELECT * FROM news {where} ORDER BY COALESCE(published_at, fetched_at) DESC",
        params,
    ).fetchall()
    latest = connection.execute("SELECT MAX(fetched_at) FROM news").fetchone()[0]
    read_rows = connection.execute("SELECT news_id, is_read FROM news_read").fetchall()
    subscriptions = [row["keyword"] for row in connection.execute("SELECT keyword FROM news_subscriptions ORDER BY created_at DESC").fetchall()]
    connection.close()
    read_by_id = {int(row["news_id"]): bool(row["is_read"]) for row in read_rows}
    all_items = []
    for row in rows:
        item = dict(row)
        item["topics"] = json.loads(item["topics"])
        item["is_read"] = read_by_id.get(int(item["id"]), False)
        article_text = f"{item['title']} {item['summary']}".lower()
        item["matched_subscriptions"] = [keyword for keyword in subscriptions if keyword.lower() in article_text]
        all_items.append(item)
    deduplicated_items = deduplicate_news_events(all_items)
    items = deduplicated_items[offset : offset + limit]
    return {
        "items": items,
        "count": len(items),
        "total": len(deduplicated_items),
        "offset": offset,
        "limit": limit,
        "updatedAt": latest,
    }


@app.post("/news/{news_id}/read")
def update_news_read(news_id: int, payload: NewsReadUpdate) -> dict[str, Any]:
    connection = database()
    try:
        exists = connection.execute("SELECT 1 FROM news WHERE id = ?", (news_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="资讯不存在")
        connection.execute(
            "INSERT INTO news_read (news_id, is_read, updated_at) VALUES (?, ?, ?) ON CONFLICT(news_id) DO UPDATE SET is_read = excluded.is_read, updated_at = excluded.updated_at",
            (news_id, 1 if payload.is_read else 0, now_iso()),
        )
        connection.commit()
        return {"news_id": news_id, "is_read": payload.is_read}
    finally:
        connection.close()


@app.get("/news/subscriptions")
def list_news_subscriptions() -> list[dict[str, Any]]:
    connection = database()
    try:
        return [dict(row) for row in connection.execute("SELECT * FROM news_subscriptions ORDER BY created_at DESC").fetchall()]
    finally:
        connection.close()


@app.post("/news/subscriptions")
def create_news_subscription(payload: NewsSubscriptionCreate) -> dict[str, Any]:
    keyword = required_text(payload.keyword, "订阅关键词", 60)
    subscription = {"id": str(uuid.uuid4()), "keyword": keyword, "created_at": now_iso()}
    connection = database()
    try:
        connection.execute("INSERT INTO news_subscriptions (id, keyword, created_at) VALUES (:id, :keyword, :created_at)", subscription)
        connection.commit()
        return subscription
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="该关键词已经订阅") from None
    finally:
        connection.close()


@app.delete("/news/subscriptions/{subscription_id}")
def delete_news_subscription(subscription_id: str) -> dict[str, str]:
    connection = database()
    try:
        cursor = connection.execute("DELETE FROM news_subscriptions WHERE id = ?", (subscription_id,))
        connection.commit()
        if not cursor.rowcount:
            raise HTTPException(status_code=404, detail="订阅不存在")
        return {"id": subscription_id, "status": "deleted"}
    finally:
        connection.close()


@app.post("/refresh")
def refresh() -> dict[str, Any]:
    return refresh_sources()
