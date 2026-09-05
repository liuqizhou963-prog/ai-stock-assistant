import asyncio
import copy
import hmac
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from assistant import memory as _memory
from assistant import article_cache as _article_cache
from assistant import article_index as _article_index
from assistant import recommender as _recommender
from assistant import assistant_core as _assistant_core
from assistant import agent_core as _agent_core
from assistant import session_memory as _session_memory
from assistant import intent as _intent
from assistant import query_rewriter as _query_rewriter
from assistant import market_tools as _market_tools
from assistant import research_store as _research_store
from assistant import market_history as _market_history
from assistant import fundamentals as _fundamentals
from assistant import research_tools as _research_tools
from assistant import research_query as _research_query

BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")


ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "data.js")
DEFAULT_PORT = 8888
REFRESH_PATH = "/api/refresh"
REFRESH_TOKEN_ENV = "INVESTMENT_NEWS_REFRESH_TOKEN"
FETCH_TIMEOUT = 600
DIGEST_TIMEOUT = 1200
TAIL_LENGTH = 500
LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
BLOCKED_STATIC_FILES = {"/llm.config.json", "/sources.json"}

_refresh_lock = threading.Lock()
_result_cache_lock = threading.Lock()
_refresh_results = OrderedDict()
_refresh_job_lock = threading.Lock()
_active_refresh_request = None
_refresh_states = {}
MAX_CACHED_REFRESHES = 32
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
LOGGER = logging.getLogger("investment_news.server")
SECRET_PATTERN = re.compile(r"(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+)")
ALERT_CHECK_INTERVAL = 60
TECHNICAL_QUERY_RE = re.compile(r"MACD|KDJ|均线|布林|K线|历史|走势|RSI|量比|成交量", re.IGNORECASE)
FUNDAMENTAL_QUERY_RE = re.compile(
    r"PE|市盈率|PB|市净率|ROE|负债率|市值|财报|营收|净利润|毛利率|净利率|现金流",
    re.IGNORECASE,
)


def _research_context_for_message(message):
    symbols = _market_tools.symbols_for_message(message)
    stock_symbol = next(
        (symbol for symbol in symbols if re.fullmatch(r"(?:sh|sz)\d{6}", symbol, re.IGNORECASE)),
        None,
    )
    if not stock_symbol:
        return None
    context = {"symbol": stock_symbol}
    if TECHNICAL_QUERY_RE.search(message):
        try:
            history = _market_history.get_history(stock_symbol, 120)
            context.update({"days": history["days"], "latest": history["latest"]})
        except (ValueError, RuntimeError, OSError) as error:
            context["error"] = "技术指标暂时不可用：" + str(error)
    if FUNDAMENTAL_QUERY_RE.search(message):
        try:
            context["fundamentals"] = _fundamentals.get_fundamentals(stock_symbol)
        except (ValueError, RuntimeError, OSError) as error:
            context["error"] = "财务指标暂时不可用：" + str(error)
    return context if len(context) > 1 else None


def _screen_symbols_for_message(message, watch_items):
    symbols = _research_tools.extract_symbols(message)
    if symbols:
        return symbols
    return [item.get("symbol") for item in watch_items if item.get("symbol")]


def _screen_for_message(message, watch_items):
    conditions = _research_tools.parse_screen_conditions(message)
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
    return _research_tools.screen_stocks(symbols, conditions)


def child_env():
    # child_env（准备子进程环境）
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    return env


def new_run_id():
    # new_run_id（生成唯一运行编号）
    return uuid.uuid4().hex


def _now_iso():
    # _now_iso（生成日志时间）
    return datetime.now(BEIJING).isoformat(timespec="seconds")


def configure_logging():
    # configure_logging（配置单行 JSON 日志）
    if LOGGER.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def _redact(value):
    # _redact（删除日志和响应中的敏感值）
    text = str(value or "")

    for name, secret in os.environ.items():
        upper_name = name.upper()
        if any(word in upper_name for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            if secret:
                text = text.replace(secret, "[REDACTED]")

    return SECRET_PATTERN.sub("[REDACTED]", text)


def _log_event(run_id, stage, status, **fields):
    # _log_event（记录结构化运行事件）
    event = {
        "time": _now_iso(),
        "run_id": run_id,
        "stage": stage,
        "status": status,
    }
    event.update({key: _redact(value) for key, value in fields.items()})
    LOGGER.info(json.dumps(event, ensure_ascii=False, sort_keys=True))


def _tail(value):
    # _tail（只保留日志末尾，避免响应过大）
    return _redact(value)[-TAIL_LENGTH:]


def _finish_step(stage, status, started_at, started_clock, run_id, **fields):
    # _finish_step（补齐步骤状态和耗时）
    result = {
        "stage": stage,
        "status": status,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "duration_ms": round((time.perf_counter() - started_clock) * 1000),
    }
    result.update(fields)
    _log_event(
        run_id,
        stage,
        status,
        duration_ms=result["duration_ms"],
        error=result.get("error", ""),
    )
    return result


def _skipped_step(stage, error, run_id):
    # _skipped_step（创建被跳过的阶段结果）
    now = _now_iso()
    result = {
        "stage": stage,
        "status": "skipped",
        "started_at": now,
        "finished_at": now,
        "duration_ms": 0,
        "error": error,
    }
    _log_event(run_id, stage, "skipped", error=error, duration_ms=0)
    return result


def _finish_refresh(result, run_id, started_at, started_clock, request_id):
    # _finish_refresh（补齐刷新状态和耗时）
    result = dict(result)
    result.update({
        "run_id": run_id,
        "request_id": request_id,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "duration_ms": round((time.perf_counter() - started_clock) * 1000),
    })
    _log_event(
        run_id,
        result.get("stage", "refresh"),
        result.get("status", "unknown"),
        duration_ms=result["duration_ms"],
        error=result.get("error", ""),
    )
    return result


def _get_cached_result(request_id):
    # _get_cached_result（读取相同请求编号的历史结果）
    if not request_id:
        return None

    with _result_cache_lock:
        result = _refresh_results.get(request_id)
        if result is None:
            return None
        _refresh_results.move_to_end(request_id)
        cached = copy.deepcopy(result)

    cached["idempotent_replay"] = True
    return cached


def _cache_result(request_id, result):
    # _cache_result（缓存有限数量的最终刷新结果）
    if not request_id or result.get("status") == "busy":
        return

    with _result_cache_lock:
        _refresh_results[request_id] = copy.deepcopy(result)
        _refresh_results.move_to_end(request_id)
        while len(_refresh_results) > MAX_CACHED_REFRESHES:
            _refresh_results.popitem(last=False)


def _set_refresh_state(request_id, status, stage, **fields):
    """Keep lightweight progress state available while the worker is running."""
    if not request_id:
        return

    state = {
        "ok": status == "running",
        "status": status,
        "stage": stage,
        "request_id": request_id,
    }
    state.update(fields)
    with _refresh_job_lock:
        _refresh_states[request_id] = state


def _get_refresh_state(request_id):
    with _refresh_job_lock:
        state = _refresh_states.get(request_id)
        return copy.deepcopy(state) if state else None


def _claim_refresh_job(request_id):
    global _active_refresh_request

    with _refresh_job_lock:
        if _active_refresh_request == request_id:
            return "running"
        if _active_refresh_request:
            return "busy"
        _active_refresh_request = request_id
        _refresh_states[request_id] = {
            "ok": True,
            "status": "running",
            "stage": "queued",
            "request_id": request_id,
        }
        return "claimed"


def _release_refresh_job(request_id):
    global _active_refresh_request

    with _refresh_job_lock:
        if _active_refresh_request == request_id:
            _active_refresh_request = None


def _finish_and_cache(result, run_id, started_at, started_clock, request_id):
    # _finish_and_cache（完成刷新并缓存最终结果）
    result = _finish_refresh(
        result,
        run_id,
        started_at,
        started_clock,
        request_id,
    )
    _cache_result(request_id, result)
    return result


def _backup_data_file():
    # _backup_data_file（在刷新前保存上一次成功数据）
    if not os.path.exists(DATA_PATH):
        return None

    backup_path = DATA_PATH + ".refresh-backup"
    temporary_path = backup_path + ".candidate"
    shutil.copyfile(DATA_PATH, temporary_path)
    os.replace(temporary_path, backup_path)
    return backup_path


def _restore_data_file(backup_path):
    # _restore_data_file（失败时恢复上一次成功数据）
    if backup_path and os.path.exists(backup_path):
        os.replace(backup_path, DATA_PATH)


def _discard_data_backup(backup_path):
    # _discard_data_backup（成功后删除临时备份）
    if backup_path and os.path.exists(backup_path):
        os.unlink(backup_path)


def _run_step(stage, script_name, timeout, runner=subprocess.run, run_id=""):
    # _run_step（执行一个刷新阶段并返回结构化结果）
    command = [sys.executable, os.path.join(ROOT, "scripts", script_name)]
    started_at = _now_iso()
    started_clock = time.perf_counter()

    try:
        completed = runner(
            command,
            cwd=ROOT,
            env=child_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _finish_step(
            stage,
            "timeout",
            started_at,
            started_clock,
            run_id,
            returncode=None,
            stdout="",
            stderr="",
            error="{}阶段超时".format(stage),
        )
    except OSError as error:
        return _finish_step(
            stage,
            "failed",
            started_at,
            started_clock,
            run_id,
            returncode=None,
            stdout="",
            stderr="",
            error="{}阶段无法启动：{}".format(stage, error),
        )

    ok = completed.returncode == 0
    return _finish_step(
        stage,
        "succeeded" if ok else "failed",
        started_at,
        started_clock,
        run_id,
        returncode=completed.returncode,
        stdout=_tail(completed.stdout),
        stderr=_tail(completed.stderr),
        error="" if ok else (_tail(completed.stderr) or "{}阶段返回非零退出码".format(stage)),
    )


def run_refresh(runner=subprocess.run, request_id=None, progress=None):
    # run_refresh（按顺序执行一次完整刷新）
    request_id = request_id or new_run_id()
    cached = _get_cached_result(request_id)
    if cached is not None:
        return cached

    run_id = new_run_id()
    started_at = _now_iso()
    started_clock = time.perf_counter()

    if not _refresh_lock.acquire(blocking=False):
        return _finish_refresh({
            "status": "busy",
            "stage": "refresh",
            "ok": False,
            "error": "已有刷新任务正在运行",
        }, run_id, started_at, started_clock, request_id)

    backup_path = _backup_data_file()

    try:
        if progress:
            progress("fetch")
        fetch_result = _run_step(
            "fetch",
            "fetch.py",
            FETCH_TIMEOUT,
            runner,
            run_id,
        )

        if fetch_result["status"] != "succeeded":
            _restore_data_file(backup_path)
            return _finish_and_cache({
                "status": "failed",
                "stage": "fetch",
                "ok": False,
                "fetch": fetch_result,
                "digest": _skipped_step(
                    "digest",
                    "抓取失败，未进入摘要阶段",
                    run_id,
                ),
                "error": fetch_result["error"],
            }, run_id, started_at, started_clock, request_id)

        if progress:
            progress("digest")
        digest_result = _run_step(
            "digest",
            "digest.py",
            DIGEST_TIMEOUT,
            runner,
            run_id,
        )

        if digest_result["status"] != "succeeded":
            _restore_data_file(backup_path)
            return _finish_and_cache({
                "status": "failed",
                "stage": "digest",
                "ok": False,
                "fetch": fetch_result,
                "digest": digest_result,
                "error": digest_result["error"],
            }, run_id, started_at, started_clock, request_id)

        _discard_data_backup(backup_path)
        return _finish_and_cache({
            "status": "succeeded",
            "stage": "complete",
            "ok": True,
            "fetch": fetch_result,
            "digest": digest_result,
            "error": "",
        }, run_id, started_at, started_clock, request_id)
    except Exception as error:
        _restore_data_file(backup_path)
        return _finish_and_cache({
            "status": "failed",
            "stage": "refresh",
            "ok": False,
            "error": "刷新编排异常：{}".format(error),
        }, run_id, started_at, started_clock, request_id)
    finally:
        _refresh_lock.release()


def response_code(result):
    # response_code（把业务状态转换成 HTTP 状态码）
    if result.get("status") == "busy":
        return 409
    return 200 if result.get("ok") else 500


def is_authorized(client_ip, token):
    # is_authorized（判断请求来源或令牌是否有效）
    expected = os.environ.get(REFRESH_TOKEN_ENV, "")

    if expected:
        return bool(token) and hmac.compare_digest(token, expected)

    return client_ip in LOOPBACK_HOSTS


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

async def _check_price_alerts():
    alerts = await asyncio.to_thread(_research_store.list_alerts)
    active = [item for item in alerts if item.get("enabled")]
    if not active:
        return []
    quotes = await asyncio.to_thread(
        _market_tools.get_quotes_for_symbols,
        list({item["symbol"] for item in active}),
    )
    quote_map = {quote["symbol"]: quote for quote in quotes}
    triggered = []
    for alert in active:
        quote = quote_map.get(alert["symbol"])
        if not quote or quote.get("price") is None:
            continue
        hit = (
            quote["price"] >= alert["threshold"]
            if alert["condition"] == "above"
            else quote["price"] <= alert["threshold"]
        )
        if hit:
            await asyncio.to_thread(_research_store.mark_alert_triggered, alert["id"])
            triggered.append({"alert": alert, "quote": quote})
    return triggered


async def _alert_monitor():
    while True:
        try:
            triggered = await _check_price_alerts()
            if triggered:
                LOGGER.info("price alerts triggered: %s", len(triggered))
        except Exception:
            LOGGER.exception("background price alert check failed")
        await asyncio.sleep(ALERT_CHECK_INTERVAL)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # _lifespan（服务启动时初始化数据库，并加载文章缓存）
    from assistant.db import init_db
    await asyncio.to_thread(init_db)
    await asyncio.to_thread(_article_cache.reload_articles)
    alert_task = asyncio.create_task(_alert_monitor())
    try:
        yield
    finally:
        alert_task.cancel()
        try:
            await alert_task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=_lifespan, docs_url=None, redoc_url=None)


async def _run_refresh_job(request_id):
    """Run the long refresh outside the request/response connection."""
    def progress(stage):
        _set_refresh_state(request_id, "running", stage)

    try:
        result = await asyncio.to_thread(
            run_refresh,
            request_id=request_id,
            progress=progress,
        )
        _set_refresh_state(
            request_id,
            result.get("status", "failed"),
            result.get("stage", "refresh"),
            result=result,
        )
        if result.get("ok"):
            await asyncio.to_thread(_article_cache.reload_articles)
    except Exception as error:
        result = {
            "ok": False,
            "status": "failed",
            "stage": "refresh",
            "request_id": request_id,
            "error": "刷新后台任务异常：{}".format(error),
        }
        _set_refresh_state(
            request_id,
            "failed",
            "refresh",
            result=result,
        )
    finally:
        _release_refresh_job(request_id)


# -- 屏蔽敏感静态文件（必须在 StaticFiles 挂载之前注册）--

@app.get("/llm.config.json")
@app.get("/sources.json")
async def _blocked_static(_request: Request):
    raise HTTPException(status_code=404)


# -- 刷新接口 --

@app.post("/api/refresh")
async def api_refresh(
    request: Request,
    x_refresh_token: str = Header(default="", alias="x-refresh-token"),
    x_refresh_request: str = Header(default="", alias="x-refresh-request"),
):
    # api_refresh（触发一次数据刷新）
    client_ip = request.client.host
    if not is_authorized(client_ip, x_refresh_token):
        return JSONResponse(
            {"ok": False, "status": "unauthorized", "error": "刷新请求未通过校验"},
            status_code=403,
        )

    request_id = x_refresh_request.strip() or new_run_id()
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        return JSONResponse(
            {"ok": False, "status": "bad_request", "error": "刷新请求编号不合法"},
            status_code=400,
        )

    cached = _get_cached_result(request_id)
    if cached is not None:
        return JSONResponse(cached, status_code=response_code(cached))

    claim = _claim_refresh_job(request_id)
    if claim == "busy":
        return JSONResponse(
            {
                "ok": False,
                "status": "busy",
                "stage": "refresh",
                "request_id": request_id,
                "error": "已有刷新任务正在运行，请稍后再试",
            },
            status_code=409,
        )

    if claim == "running":
        return JSONResponse(
            _get_refresh_state(request_id),
            status_code=202,
        )

    asyncio.create_task(_run_refresh_job(request_id))
    return JSONResponse(
        {
            "ok": True,
            "status": "running",
            "stage": "queued",
            "request_id": request_id,
        },
        status_code=202,
    )


@app.get("/api/refresh/status/{request_id}")
async def api_refresh_status(request_id: str):
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        return JSONResponse(
            {"ok": False, "status": "bad_request", "error": "刷新请求编号不合法"},
            status_code=400,
        )

    cached = _get_cached_result(request_id)
    if cached is not None:
        return JSONResponse(cached, status_code=response_code(cached))

    state = _get_refresh_state(request_id)
    if state is not None:
        return JSONResponse(state, status_code=202)

    return JSONResponse(
        {"ok": False, "status": "not_found", "error": "刷新任务不存在或已过期"},
        status_code=404,
    )


@app.get("/api/refresh")
async def api_refresh_get():
    # api_refresh_get（不允许 GET 刷新）
    raise HTTPException(status_code=405)


# -- 个人咨询助手接口（桩，待 assistant 模块实现后填充）--

def _sse(event: str, payload: dict) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


@app.post("/api/assistant/chat/stream")
async def api_assistant_chat_stream(request: Request):
    """Stream assistant answer tokens as Server-Sent Events."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "请求格式错误"}, status_code=400)

    message = str(body.get("message", "")).strip()
    industry_key = body.get("industry_key") or None
    focus = body.get("focus")
    conv_id = str(body.get("conv_id") or uuid.uuid4().hex)
    if not message:
        return JSONResponse({"ok": False, "error": "message 不能为空"}, status_code=400)

    async def event_stream():
        memories, session_history = await asyncio.gather(
            asyncio.to_thread(_memory.list_memories),
            asyncio.to_thread(_session_memory.get_history, conv_id),
        )
        watch_items = await asyncio.to_thread(_research_store.list_watchlist)
        prepared = await asyncio.to_thread(
            _agent_core.prepare,
            message,
            memories,
            session_history,
            watch_items,
            industry_key,
            focus,
        )
        market_quotes = prepared.get("market", [])
        market_summary = prepared.get("market_report", "")
        yield _sse(
            "meta",
            {
                "ok": True,
                "intent": prepared.get("intent"),
                "market": market_quotes,
                "market_report": market_summary,
                "research_data": prepared.get("research_data"),
                "agent": prepared.get("agent", {}),
            },
        )

        if market_summary:
            yield _sse("market_report", {
                "markdown": market_summary,
                "quotes": market_quotes,
            })

        if prepared.get("terminal"):
            answer = prepared.get("answer", "")
            yield _sse("token", {"text": answer})
            yield _sse("done", {
                "ok": True,
                "articles": prepared.get("articles", []),
                "memory_suggestions": prepared.get("memory_suggestions", []),
                "market_report": market_summary,
                "research_data": prepared.get("research_data"),
                "screen": prepared.get("screen"),
                "agent": prepared.get("agent", {}),
            })
            asyncio.create_task(
                asyncio.to_thread(
                    _session_memory.add_messages, conv_id, message, answer
                )
            )
            return

        candidates = prepared.get("candidates", [])
        if any(step.get("tool") == "search_articles" for step in prepared.get("agent", {}).get("plan", [])):
            yield _sse("status", {"text": "正在检索相关资讯"})

        yield _sse("status", {"text": "正在生成回答"})
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        answer_parts = []

        def push(item):
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def run_stream():
            try:
                for delta in _assistant_core.stream_chat(
                    message,
                    prepared["memories"],
                    candidates,
                    session_history,
                    None,
                    market_quotes,
                    prepared.get("research_context"),
                    prepared.get("focus"),
                    prepared.get("research_data"),
                ):
                    push(("token", delta))
                push(("done", None))
            except Exception as error:
                push(("error", str(error)))

        asyncio.create_task(asyncio.to_thread(run_stream))
        while True:
            kind, value = await queue.get()
            if kind == "token":
                answer_parts.append(value)
            elif kind == "error":
                fallback = market_summary or prepared.get("research_report", "")
                if fallback:
                    answer_parts = [fallback]
                    yield _sse("token", {"text": fallback})
                    yield _sse("done", {
                        "ok": True,
                        "articles": [],
                        "memory_suggestions": [],
                        "market_report": market_summary,
                        "research_data": prepared.get("research_data"),
                    })
                else:
                    yield _sse("error", {"message": "AI 回答暂时不可用，请稍后重试"})
                return
            else:
                break

        answer = "".join(answer_parts).strip()
        answer, blocked = _agent_core.guardrail_answer(answer)
        if answer:
            yield _sse("token", {"text": answer})
        if answer:
            asyncio.create_task(
                asyncio.to_thread(
                    _session_memory.add_messages, conv_id, message, answer
                )
            )

        articles = []
        for article in candidates[:5]:
            articles.append(_agent_core.article_payload(article))
        yield _sse("done", {
            "ok": True,
            "articles": articles,
            "memory_suggestions": [],
            "market_report": market_summary,
            "research_data": prepared.get("research_data"),
            "agent": {**prepared.get("agent", {}), "output_guardrail": {"blocked": blocked}},
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/api/assistant/chat")
async def api_assistant_chat(request: Request):
    # api_assistant_chat（受控自主 Agent：安全预判 + 计划 + 工具 + 审查 + LLM）
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "请求格式错误"}, status_code=400)

    message     = str(body.get("message", "")).strip()
    industry_key = body.get("industry_key") or None
    focus       = body.get("focus")
    conv_id     = str(body.get("conv_id") or uuid.uuid4().hex)

    if not message:
        return JSONResponse({"ok": False, "error": "message 不能为空"}, status_code=400)

    # 并行加载：长期记忆 + 会话历史
    memories, session_history = await asyncio.gather(
        asyncio.to_thread(_memory.list_memories),
        asyncio.to_thread(_session_memory.get_history, conv_id),
    )
    watch_items = await asyncio.to_thread(_research_store.list_watchlist)
    result = await asyncio.to_thread(
        _agent_core.run,
        message,
        memories,
        session_history,
        watch_items,
        industry_key,
        focus,
    )
    result["conv_id"] = conv_id

    if result.get("terminal") or not result.get("llm_available", True):
        asyncio.create_task(
            asyncio.to_thread(
                _session_memory.add_messages, conv_id, message, result.get("answer", "")
            )
        )
        result.pop("terminal", None)
        return JSONResponse(result)

    # 写入会话工作记忆（fire-and-forget，不阻塞响应）
    asyncio.create_task(
        asyncio.to_thread(_session_memory.add_messages, conv_id, message, result.get("answer", ""))
    )
    return JSONResponse(result)


@app.post("/api/memory/save")
async def api_memory_save(request: Request):
    # api_memory_save（保存长期记忆）
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "请求格式错误"}, status_code=400)

    memory_type = str(body.get("memory_type", "preference")).strip()
    title = str(body.get("title", "")).strip()
    content = str(body.get("content", "")).strip()
    tags = body.get("tags", [])

    if not title or not content:
        return JSONResponse(
            {"ok": False, "error": "title 和 content 不能为空"}, status_code=400
        )

    mem_id = await asyncio.to_thread(_memory.save_memory, memory_type, title, content, tags)
    return JSONResponse({"ok": True, "id": mem_id})


@app.get("/api/memory")
async def api_memory_list():
    # api_memory_list（查看当前记忆列表）
    items = await asyncio.to_thread(_memory.list_memories)
    return JSONResponse({"ok": True, "items": items})


@app.delete("/api/memory/{memory_id}")
async def api_memory_delete(memory_id: int):
    # api_memory_delete（删除指定记忆）
    await asyncio.to_thread(_memory.delete_memory, memory_id)
    return JSONResponse({"ok": True})


@app.post("/api/articles/sync")
async def api_articles_sync():
    # api_articles_sync（手动重新从 data.js 加载文章进内存缓存）
    n = await asyncio.to_thread(_article_cache.reload_articles)
    return JSONResponse({"ok": True, "loaded": n})


@app.post("/api/articles/save")
async def api_articles_save(request: Request):
    # api_articles_save（收藏一篇文章，写入 saved_articles + memories 表；规划 §7.6 §10.3）
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "请求格式错误"}, status_code=400)

    url          = str(body.get("url", "")).strip()
    title        = str(body.get("title", "")).strip()
    source       = str(body.get("source", "")).strip()
    industry_key = str(body.get("industry_key", "")).strip()
    note         = str(body.get("note", "")).strip()
    tags         = body.get("tags", [])

    if not title:
        return JSONResponse({"ok": False, "error": "title 不能为空"}, status_code=400)

    # article_key 可由前端传入（已有时复用），也可服务端生成
    article_key = str(body.get("article_key") or "").strip()
    if not article_key:
        article_key = _article_index.make_article_key(url, source, title)

    await asyncio.to_thread(
        _article_index.save_article,
        article_key, url, title, source, industry_key, note, tags,
    )
    return JSONResponse({"ok": True})


# -- 研究台：行情、历史指标、自选股与提醒 --

@app.get("/api/market/quote")
async def api_market_quote(symbol: str = ""):
    symbol = symbol.strip()
    if not symbol:
        return JSONResponse({"ok": False, "error": "symbol 不能为空"}, status_code=400)
    quotes = await asyncio.to_thread(_market_tools.get_quotes_for_symbols, [symbol])
    if not quotes:
        return JSONResponse({"ok": False, "error": "暂时没有找到该行情"}, status_code=404)
    return JSONResponse({"ok": True, "quote": quotes[0]})


@app.get("/api/market/history")
async def api_market_history(symbol: str = "", days: int = 120, chart: int = 0, scale: int = 240):
    if not symbol.strip():
        return JSONResponse({"ok": False, "error": "symbol 不能为空"}, status_code=400)
    try:
        history = await asyncio.to_thread(_market_history.get_history, symbol, days, scale)
        if chart:
            history["chart"] = await asyncio.to_thread(_market_history.make_chart, history)
        return JSONResponse({"ok": True, **history})
    except (ValueError, RuntimeError, OSError) as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)


@app.get("/api/market/fundamentals")
async def api_market_fundamentals(symbol: str = ""):
    symbol = symbol.strip()
    if not symbol:
        return JSONResponse({"ok": False, "error": "symbol 不能为空"}, status_code=400)
    try:
        symbol = _market_tools.normalize_symbol(symbol)
        data = await asyncio.to_thread(_fundamentals.get_fundamentals, symbol)
        return JSONResponse({"ok": True, "fundamentals": data})
    except (ValueError, RuntimeError, OSError) as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=503)


@app.get("/api/research/compare")
async def api_research_compare(symbols: str = ""):
    """Compare the submitted stock sample with transparent peer medians."""
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    if not requested:
        watch_items = await asyncio.to_thread(_research_store.list_watchlist)
        requested = [item.get("symbol") for item in watch_items if item.get("symbol")]
    if not requested:
        return JSONResponse({"ok": False, "error": "请先提供股票代码或加入自选"}, status_code=400)
    try:
        snapshots = await asyncio.gather(*[
            asyncio.to_thread(_fundamentals.get_fundamentals, symbol)
            for symbol in requested[:30]
        ])
    except (ValueError, RuntimeError, OSError) as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=503)
    result = await asyncio.to_thread(_research_tools.compare_snapshots, snapshots)
    result["report"] = _research_tools.format_compare_report(result)
    return JSONResponse({"ok": True, **result})


@app.post("/api/research/screen")
async def api_research_screen(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "请求格式错误"}, status_code=400)
    message = str(body.get("message", "")).strip()
    symbols = body.get("symbols") or _research_tools.extract_symbols(message)
    conditions = body.get("conditions") or _research_tools.parse_screen_conditions(message)
    if not conditions:
        return JSONResponse({"ok": False, "error": "没有识别到筛选条件"}, status_code=400)
    if not symbols:
        watch_items = await asyncio.to_thread(_research_store.list_watchlist)
        symbols = [item.get("symbol") for item in watch_items if item.get("symbol")]
    if not symbols:
        return JSONResponse({"ok": False, "error": "没有候选股票，请先加入自选或提供代码"}, status_code=400)
    result = await asyncio.to_thread(_research_tools.screen_stocks, symbols, conditions)
    result["report"] = _research_tools.format_screen_report(result)
    return JSONResponse({"ok": True, **result})


@app.post("/api/research/query")
async def api_research_query(request: Request):
    """Run a safe AskData-style Text2SQL query over the local news snapshot."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "请求格式错误"}, status_code=400)
    message = str(body.get("message", "")).strip()
    if not message:
        return JSONResponse({"ok": False, "error": "message 不能为空"}, status_code=400)
    result = await asyncio.to_thread(_research_query.get_service().query, message)
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


@app.get("/api/watchlist")
async def api_watchlist_list():
    items = await asyncio.to_thread(_research_store.list_watchlist)
    symbols = [item["symbol"] for item in items]
    quotes = await asyncio.to_thread(_market_tools.get_quotes_for_symbols, symbols)
    quote_map = {quote["symbol"]: quote for quote in quotes}
    for item in items:
        item["quote"] = quote_map.get(item["symbol"])
    return JSONResponse({"ok": True, "items": items})


@app.post("/api/watchlist")
async def api_watchlist_save(request: Request):
    try:
        body = await request.json()
        symbol = _market_tools.normalize_symbol(body.get("symbol", ""))
        quotes = await asyncio.to_thread(_market_tools.get_quotes_for_symbols, [symbol])
        if not quotes:
            return JSONResponse({"ok": False, "error": "找不到该行情代码"}, status_code=400)
        await asyncio.to_thread(
            _research_store.save_watch,
            symbol,
            body.get("name") or quotes[0].get("name", ""),
            body.get("asset_type", "stock"),
            body.get("note", ""),
        )
        return JSONResponse({"ok": True})
    except (ValueError, TypeError) as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)


@app.delete("/api/watchlist/{watch_id}")
async def api_watchlist_delete(watch_id: int):
    await asyncio.to_thread(_research_store.delete_watch, watch_id)
    return JSONResponse({"ok": True})


@app.get("/api/alerts")
async def api_alerts_list():
    return JSONResponse({"ok": True, "items": await asyncio.to_thread(_research_store.list_alerts)})


@app.post("/api/alerts")
async def api_alert_save(request: Request):
    try:
        body = await request.json()
        symbol = _market_tools.normalize_symbol(body.get("symbol", ""))
        quotes = await asyncio.to_thread(_market_tools.get_quotes_for_symbols, [symbol])
        if not quotes:
            return JSONResponse({"ok": False, "error": "找不到该行情代码"}, status_code=400)
        alert_id = await asyncio.to_thread(
            _research_store.save_alert,
            symbol,
            body.get("name") or quotes[0].get("name", ""),
            body.get("condition"),
            body.get("threshold"),
        )
        return JSONResponse({"ok": True, "id": alert_id})
    except (ValueError, TypeError) as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)


@app.delete("/api/alerts/{alert_id}")
async def api_alert_delete(alert_id: int):
    await asyncio.to_thread(_research_store.delete_alert, alert_id)
    return JSONResponse({"ok": True})


@app.post("/api/alerts/check")
async def api_alerts_check():
    return JSONResponse({"ok": True, "triggered": await _check_price_alerts()})


# -- 未匹配的 /api/ 路径统一返回 404，避免被 StaticFiles 捕获返回 405 --
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def api_catch_all(path: str):
    raise HTTPException(status_code=404)


# -- 静态文件（必须最后挂载，优先级低于上方所有路由）--
app.mount("/", StaticFiles(directory=ROOT, html=True), name="static")


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

def main():
    # main（启动本地服务）
    configure_logging()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    print("看板服务已启动：http://127.0.0.1:{}/index.html".format(port))
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)


if __name__ == "__main__":
    main()
