"""Controlled autonomous-agent orchestration for the investment assistant.

This module keeps the current deterministic financial guardrails, but moves
assistant routing out of the FastAPI handlers into an explicit agent pipeline:

Safety precheck -> planner -> tool executor -> critic -> synthesizer -> output
guardrail.

The planner is intentionally conservative and rule-assisted. It returns a
tool plan that can later be replaced by an LLM planner without changing the
route layer or the tool contracts.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from . import assistant_core
from . import fundamentals
from . import intent
from . import market_history
from . import market_tools
from . import query_rewriter
from . import research_query
from . import research_tools


TECHNICAL_QUERY_RE = re.compile(r"MACD|KDJ|均线|布林|K线|历史|走势|RSI|量比|成交量", re.IGNORECASE)
FUNDAMENTAL_QUERY_RE = re.compile(
    r"PE|市盈率|PB|市净率|ROE|负债率|市值|财报|营收|净利润|毛利率|净利率|现金流|基本面",
    re.IGNORECASE,
)
FUTURE_TRADING_RE = re.compile(
    r"(明天|明日|后天|下周|下个月|未来|接下来|短期|近期).*(走势|方向|涨|跌|空间|目标|买|卖|持有|加仓|减仓|操作|胜率|概率)"
)
TRADING_ADVICE_RE = re.compile(
    r"("
    r"买入|卖出|持有|加仓|减仓|建仓|清仓|满仓|空仓|抄底|逃顶|止盈|止损|"
    r"目标价|看到\s*\d+|仓位|几成仓|能不能买|该不该买|要不要买|要不要卖|"
    r"继续拿着|继续持有|给.*建议|推荐.*股票"
    r")"
)
NON_FINANCE_RE = re.compile(r"天气|做饭|烹饪|菜谱|食谱|游戏|娱乐|明星|电影|综艺|编程|代码|程序|开发")
OUTPUT_BLOCK_RE = re.compile(
    r"(建议|可以|适合|考虑)?\s*(买入|卖出|持有|加仓|减仓|建仓|清仓|抄底|逃顶)|"
    r"目标价|止盈|止损|仓位|明天.*(涨|跌)|下周.*(涨|跌)"
)


REJECT_ANSWER = (
    "这个问题超出了我的服务范围。我不提供未来涨跌预测、目标价、具体买卖或仓位建议。"
    "我可以改为帮你整理已有行情事实、基本面线索、相关资讯和需要继续跟踪的风险指标。"
)


@dataclass
class ToolSpec:
    name: str
    description: str
    risk: str
    handler: Callable[[dict[str, Any], dict[str, Any]], Any]
    auto: bool = True


def article_payload(article: dict, include_reason: bool = True) -> dict:
    return {
        "title": article.get("title", ""),
        "zh": article.get("zh", ""),
        "source": article.get("source", ""),
        "url": article.get("url", ""),
        "article_key": article.get("article_key", ""),
        "industry_key": article.get("industry_key", ""),
        "industry_name": article.get("industry_name", ""),
        "subindustry_name": article.get("subindustry_name", ""),
        "summary": article.get("summary", ""),
        "time": article.get("time", ""),
        "reason": article.get("reason", "") if include_reason else "",
    }


def add_watchlist_memories(memories: list[dict], watch_items: list[dict]) -> list[dict]:
    result = list(memories or [])
    result.extend(
        {
            "memory_type": "watchlist",
            "title": item.get("name") or item.get("symbol", ""),
            "content": "自选跟踪：" + item.get("symbol", ""),
            "tags": [item.get("symbol", "")],
        }
        for item in (watch_items or [])
    )
    return result


def safety_precheck(message: str, detected_intent: str) -> dict:
    """Fast safety gate before any tool or LLM work."""
    if detected_intent == intent.INTENT_REJECT:
        return {"allowed": False, "reason": "intent_reject", "answer": REJECT_ANSWER}
    if NON_FINANCE_RE.search(message):
        return {"allowed": False, "reason": "non_finance", "answer": REJECT_ANSWER}
    if FUTURE_TRADING_RE.search(message) or TRADING_ADVICE_RE.search(message):
        if not any(re.search(pattern, message) for pattern in intent._CURRENT_QUOTE_PATTERNS):
            return {"allowed": False, "reason": "trading_advice", "answer": REJECT_ANSWER}
    return {"allowed": True, "reason": "", "answer": ""}


def quick_safety_precheck(message: str) -> dict:
    """Reject obvious unsafe requests before invoking intent classification."""
    if NON_FINANCE_RE.search(message):
        return {"allowed": False, "reason": "non_finance", "answer": REJECT_ANSWER}
    if FUTURE_TRADING_RE.search(message) or TRADING_ADVICE_RE.search(message):
        if not any(re.search(pattern, message) for pattern in intent._CURRENT_QUOTE_PATTERNS):
            return {"allowed": False, "reason": "trading_advice", "answer": REJECT_ANSWER}
    return {"allowed": True, "reason": "", "answer": ""}


def _stock_symbol_for_message(message: str) -> str | None:
    symbols = market_tools.symbols_for_message(message)
    return next(
        (
            symbol
            for symbol in symbols
            if re.fullmatch(r"(?:sh|sz)\d{6}", symbol, re.IGNORECASE)
        ),
        None,
    )


def _screen_symbols_for_message(message: str, watch_items: list[dict]) -> list[str]:
    symbols = research_tools.extract_symbols(message)
    if symbols:
        return symbols
    return [item.get("symbol") for item in (watch_items or []) if item.get("symbol")]


def _screen_for_message(message: str, watch_items: list[dict]) -> dict:
    conditions = research_tools.parse_screen_conditions(message)
    symbols = _screen_symbols_for_message(message, watch_items)
    if not conditions:
        return {
            "error": "没有识别到筛选条件。可以说：低 PE、高 ROE、营收增长超过 20%。",
            "conditions": {},
            "candidates": 0,
            "matched": [],
            "all": [],
            "warnings": [],
        }
    if not symbols:
        return {
            "error": "没有候选股票。请先加入自选，或在问题中写出股票代码。",
            "conditions": conditions,
            "candidates": 0,
            "matched": [],
            "all": [],
            "warnings": [],
        }
    return research_tools.screen_stocks(symbols, conditions)


def _research_context_for_message(message: str) -> dict | None:
    stock_symbol = _stock_symbol_for_message(message)
    if not stock_symbol:
        return None
    context: dict[str, Any] = {"symbol": stock_symbol}
    if TECHNICAL_QUERY_RE.search(message):
        try:
            history = market_history.get_history(stock_symbol, 120)
            context.update({"days": history["days"], "latest": history["latest"]})
        except (ValueError, RuntimeError, OSError) as error:
            context["error"] = "技术指标暂时不可用：" + str(error)
    if FUNDAMENTAL_QUERY_RE.search(message):
        try:
            context["fundamentals"] = fundamentals.get_fundamentals(stock_symbol)
        except (ValueError, RuntimeError, OSError) as error:
            context["error"] = "财务指标暂时不可用：" + str(error)
    return context if len(context) > 1 else None


def _handle_get_market_quotes(args: dict, state: dict) -> list[dict]:
    return market_tools.get_market_quotes(args["message"])


def _handle_get_research_context(args: dict, state: dict) -> dict | None:
    return _research_context_for_message(args["message"])


def _handle_search_articles(args: dict, state: dict) -> list[dict]:
    return query_rewriter.recommend_with_rewrite(
        args["message"],
        state.get("memories") or [],
        args.get("industry_key"),
    )


def _handle_screen_stocks(args: dict, state: dict) -> dict:
    return _screen_for_message(args["message"], state.get("watch_items") or [])


def _handle_query_research_data(args: dict, state: dict) -> dict:
    return research_query.get_service().query(args["message"])


TOOLS: dict[str, ToolSpec] = {
    "get_market_quotes": ToolSpec(
        "get_market_quotes",
        "获取和用户问题相关的实时行情事实",
        "low",
        _handle_get_market_quotes,
    ),
    "get_research_context": ToolSpec(
        "get_research_context",
        "获取个股技术指标或财务快照证据",
        "medium",
        _handle_get_research_context,
    ),
    "search_articles": ToolSpec(
        "search_articles",
        "检索当前资讯缓存中的候选文章",
        "low",
        _handle_search_articles,
    ),
    "screen_stocks": ToolSpec(
        "screen_stocks",
        "按用户明确给出的条件筛选候选股票",
        "high",
        _handle_screen_stocks,
    ),
    "query_research_data": ToolSpec(
        "query_research_data",
        "通过 Schema 检索和只读 SQL 查询分析本地投研快照",
        "medium",
        _handle_query_research_data,
    ),
}


def make_plan(message: str, detected_intent: str, industry_key: str | None) -> list[dict]:
    """Build a conservative tool plan from user intent and observable terms."""
    steps = []
    if research_tools.is_screen_query(message):
        return [
            {
                "tool": "screen_stocks",
                "args": {"message": message},
                "reason": "用户要求按明确条件筛选候选股票",
            }
        ]

    if research_query.is_data_query(message):
        return [
            {
                "tool": "query_research_data",
                "args": {"message": message},
                "reason": "问题需要对本地投研快照进行结构化统计或明细查询",
            }
        ]

    if market_tools.symbols_for_message(message):
        steps.append(
            {
                "tool": "get_market_quotes",
                "args": {"message": message},
                "reason": "问题包含可解析行情标的或行情事实词",
            }
        )

    if _stock_symbol_for_message(message) and (
        TECHNICAL_QUERY_RE.search(message) or FUNDAMENTAL_QUERY_RE.search(message)
    ):
        steps.append(
            {
                "tool": "get_research_context",
                "args": {"message": message},
                "reason": "问题需要个股技术或基本面证据",
            }
        )

    if detected_intent == intent.INTENT_NEWS_QUERY or not market_tools.is_market_only_query(message):
        steps.append(
            {
                "tool": "search_articles",
                "args": {"message": message, "industry_key": industry_key},
                "reason": "检索资讯候选，供回答引用或降级展示",
            }
        )

    return steps


def execute_plan(plan: list[dict], state: dict) -> dict:
    observations = []
    values = {
        "market_quotes": [],
        "research_context": None,
        "research_data": None,
        "candidates": [],
        "screen": None,
    }
    for step in plan[:5]:
        tool_name = step.get("tool", "")
        spec = TOOLS.get(tool_name)
        started = time.perf_counter()
        if spec is None or not spec.auto:
            observations.append({
                "tool": tool_name,
                "status": "blocked",
                "reason": "工具不存在或不允许自动调用",
            })
            continue
        try:
            output = spec.handler(step.get("args") or {}, state)
            status = "ok"
            error = ""
        except (ValueError, RuntimeError, OSError, TypeError) as exc:
            output = None
            status = "failed"
            error = str(exc)
        observations.append({
            "tool": tool_name,
            "risk": spec.risk,
            "status": status,
            "reason": step.get("reason", ""),
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "error": error,
        })
        if status != "ok":
            continue
        if tool_name == "get_market_quotes":
            values["market_quotes"] = output or []
        elif tool_name == "get_research_context":
            values["research_context"] = output
        elif tool_name == "query_research_data":
            values["research_data"] = output
        elif tool_name == "search_articles":
            values["candidates"] = output or []
        elif tool_name == "screen_stocks":
            values["screen"] = output
    values["observations"] = observations
    return values


def critique(values: dict, message: str) -> dict:
    missing = []
    research_context = values.get("research_context")
    research_data = values.get("research_data")
    if FUNDAMENTAL_QUERY_RE.search(message) and not (
        isinstance(research_context, dict) and research_context.get("fundamentals")
    ):
        missing.append("缺少可用财务快照或完整多期财务趋势数据")
    if "连续" in message or "三个季度" in message or "趋势" in message:
        missing.append("当前工具主要提供最新快照，无法严谨证明连续多期变化")
    if market_tools.symbols_for_message(message) and not values.get("market_quotes"):
        missing.append("实时行情暂时不可用")
    if research_data is not None and not research_data.get("ok"):
        missing.append("结构化投研查询未成功")
    return {
        "enough": not missing,
        "missing": list(dict.fromkeys(missing)),
    }


def guardrail_answer(answer: str) -> tuple[str, bool]:
    """Block trading-advice leakage in the final answer."""
    text = str(answer or "")
    if OUTPUT_BLOCK_RE.search(text):
        return (
            "我不能给出买入、卖出、持有、仓位或目标价建议。"
            "基于当前证据，我可以帮你整理事实、风险点和后续需要跟踪的指标；"
            "请结合正式公告、财报和持牌机构意见独立判断。",
            True,
        )
    return text, False


FOCUS_TEXT_FIELDS = (
    "kind",
    "title",
    "raw_title",
    "source",
    "url",
    "article_key",
    "time",
    "industry_name",
    "subindustry_name",
)
FOCUS_MAX_LEN = 300


def sanitize_focus(focus: Any) -> dict | None:
    """Keep only known short text fields from the client-supplied focus context.

    The dashboard sends the article/digest item the user clicked "问助手" on.
    It is untrusted input, so drop unknown keys and clamp lengths before it
    reaches the prompt.
    """
    if not isinstance(focus, dict):
        return None
    cleaned = {}
    for field in FOCUS_TEXT_FIELDS:
        value = focus.get(field)
        if not isinstance(value, str):
            continue
        value = value.strip()[:FOCUS_MAX_LEN]
        if value:
            cleaned[field] = value
    return cleaned if cleaned.get("title") else None


def focus_search_message(message: str, focus: dict | None) -> str:
    """Bias article retrieval toward the focused item's own title."""
    if not focus:
        return message
    title = focus.get("title", "")
    return f"{message} {title}".strip() if title else message


def prepare(
    message: str,
    memories: list[dict],
    session_history: list[dict],
    watch_items: list[dict],
    industry_key: str | None = None,
    focus: dict | None = None,
) -> dict:
    """Run safety, planning, tool execution and evidence critique."""
    memories = add_watchlist_memories(memories, watch_items)
    quick_safety = quick_safety_precheck(message)
    if not quick_safety["allowed"]:
        return {
            "ok": True,
            "terminal": True,
            "answer": quick_safety["answer"],
            "articles": [],
            "memory_suggestions": [],
            "market": [],
            "market_report": "",
            "research_data": None,
            "research_report": "",
            "llm_available": True,
            "intent": intent.INTENT_REJECT,
            "agent": {
                "mode": "controlled_autonomous",
                "safety": quick_safety,
                "plan": [],
                "observations": [],
                "critic": {"enough": False, "missing": ["快速安全预检拒绝"]},
            },
        }
    detected_intent = intent.recognize(message)
    safety = safety_precheck(message, detected_intent)
    if not safety["allowed"]:
        return {
            "ok": True,
            "terminal": True,
            "answer": safety["answer"],
            "articles": [],
            "memory_suggestions": [],
            "market": [],
            "market_report": "",
            "research_data": None,
            "research_report": "",
            "llm_available": True,
            "intent": detected_intent,
            "agent": {
                "mode": "controlled_autonomous",
                "safety": safety,
                "plan": [],
                "observations": [],
                "critic": {"enough": False, "missing": ["安全预判拒绝"]},
            },
        }

    focus = sanitize_focus(focus)
    plan = make_plan(message, detected_intent, industry_key)
    for step in plan:
        # 追问某条资讯时，用它的标题一起做检索，避免只按原问题的短语召回。
        if step.get("tool") == "search_articles":
            step["args"]["message"] = focus_search_message(message, focus)
    values = execute_plan(
        plan,
        {
            "memories": memories,
            "session_history": session_history,
            "watch_items": watch_items,
        },
    )
    market_quotes = values.get("market_quotes") or []
    market_report = market_tools.format_market_quotes(market_quotes)
    research_data = values.get("research_data")
    research_report = (
        research_query.format_query_result(research_data)
        if research_data
        else ""
    )
    critic = critique(values, message)

    if values.get("screen") is not None:
        screen_result = values["screen"]
        answer = screen_result.get("error") or research_tools.format_screen_report(screen_result)
        return {
            "ok": True,
            "terminal": True,
            "answer": answer,
            "articles": [],
            "memory_suggestions": [],
            "market": [],
            "market_report": "",
            "research_data": research_data,
            "research_report": research_report,
            "screen": screen_result,
            "llm_available": False,
            "intent": detected_intent,
            "agent": {
                "mode": "controlled_autonomous",
                "safety": safety,
                "plan": plan,
                "observations": values["observations"],
                "critic": critic,
            },
        }

    if market_quotes and market_tools.is_market_only_query(message):
        return {
            "ok": True,
            "terminal": True,
            "answer": market_report,
            "articles": [],
            "memory_suggestions": [],
            "market": market_quotes,
            "market_report": market_report,
            "research_data": research_data,
            "research_report": research_report,
            "llm_available": False,
            "intent": detected_intent,
            "agent": {
                "mode": "controlled_autonomous",
                "safety": safety,
                "plan": plan,
                "observations": values["observations"],
                "critic": critic,
            },
        }

    return {
        "ok": True,
        "terminal": False,
        "message": message,
        "memories": memories,
        "session_history": session_history,
        "candidates": values.get("candidates") or [],
        "market": market_quotes,
        "market_report": market_report,
        "research_context": values.get("research_context"),
        "research_data": research_data,
        "research_report": research_report,
        "focus": focus,
        "intent": detected_intent,
        "agent": {
            "mode": "controlled_autonomous",
            "safety": safety,
            "plan": plan,
            "observations": values["observations"],
            "critic": critic,
        },
    }


def run(
    message: str,
    memories: list[dict],
    session_history: list[dict],
    watch_items: list[dict],
    industry_key: str | None = None,
    focus: dict | None = None,
) -> dict:
    prepared = prepare(message, memories, session_history, watch_items, industry_key, focus)
    if prepared.get("terminal"):
        return prepared

    llm_ok, answer, articles, suggestions = assistant_core.chat(
        message,
        prepared["memories"],
        prepared["candidates"],
        prepared["session_history"],
        None,
        prepared["market"],
        prepared["research_context"],
        prepared.get("focus"),
        prepared.get("research_data"),
    )

    if not llm_ok:
        fallback_answer = (
            prepared["market_report"]
            if prepared["market_report"]
            else prepared.get("research_report")
            if prepared.get("research_report")
            else (
                f"AI 解释暂不可用（{answer}），以下为相关资讯："
                if prepared["candidates"]
                else "暂未找到相关资讯，可以尝试换个关键词或先刷新数据。"
            )
        )
        return {
            "ok": True,
            "answer": fallback_answer,
            "articles": [article_payload(a, include_reason=False) for a in prepared["candidates"]],
            "market": prepared["market"],
            "market_report": prepared["market_report"],
            "research_data": prepared.get("research_data"),
            "research_report": prepared.get("research_report", ""),
            "memory_suggestions": [],
            "llm_available": False,
            "intent": prepared["intent"],
            "agent": prepared["agent"],
        }

    guarded_answer, blocked = guardrail_answer(answer)
    final_answer = (
        f"{prepared['market_report']}\n\n{guarded_answer}"
        if prepared["market_report"] and guarded_answer != prepared["market_report"]
        else guarded_answer
    )
    agent = dict(prepared["agent"])
    agent["output_guardrail"] = {"blocked": blocked}
    return {
        "ok": True,
        "answer": final_answer,
        "articles": [article_payload(a) for a in articles],
        "market": prepared["market"],
        "market_report": prepared["market_report"],
        "research_data": prepared.get("research_data"),
        "research_report": prepared.get("research_report", ""),
        "memory_suggestions": suggestions,
        "llm_available": True,
        "intent": prepared["intent"],
        "agent": agent,
    }
