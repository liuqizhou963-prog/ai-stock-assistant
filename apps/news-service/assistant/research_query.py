"""AskData-inspired schema retrieval and safe read-only research queries."""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path

from mcp_router import MCPRouter, SQLiteMCPExecutor
from mcp_router.objects import MCPExecutionRequest, MCPExecutionResult
from schema_retrieval.graph_builder import build_schema_graph
from schema_retrieval.retriever import SchemaRetriever
from schema_retrieval.sqlite_loader import SQLiteSchemaLoader

from .research_snapshot import BUSINESS_META, DEFAULT_DB, ensure_snapshot


MAX_ROWS = 200
DATABASE_NAME = "research_snapshot"
_SERVICE = None
_SERVICE_LOCK = threading.Lock()


class _SafeSQLiteExecutor(SQLiteMCPExecutor):
    """Read-only executor with statement, table and row limits."""

    _FORBIDDEN = re.compile(
        r"\b(?:insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b",
        re.IGNORECASE,
    )
    _TABLE_RE = re.compile(r"\b(?:from|join)\s+[\"`]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)

    def __init__(self, database: str, db_path: str | Path, allowed_tables: set[str]):
        super().__init__(database=database, db_path=db_path, readonly=True)
        self.allowed_tables = allowed_tables

    def execute(self, request: MCPExecutionRequest) -> MCPExecutionResult:
        sql = str(request.sql or "").strip()
        error = self.validate_sql(sql)
        if error:
            return MCPExecutionResult(
                database=request.database, sql=sql, success=False, error=error
            )
        if request.database != self.database:
            return MCPExecutionResult(
                database=request.database, sql=sql, success=False,
                error=f"数据库路由错误：当前只允许访问 {self.database}",
            )

        conn = None
        started = time.perf_counter()
        try:
            conn = sqlite3.connect(
                f"file:{self.db_path}?mode=ro", uri=True, timeout=5
            )
            conn.execute("PRAGMA query_only=ON")
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(MAX_ROWS + 1)
            if len(rows) > MAX_ROWS:
                return MCPExecutionResult(
                    database=request.database, sql=sql, success=False,
                    error=f"查询结果超过 {MAX_ROWS} 行，请增加筛选条件或聚合维度",
                )
            columns = [item[0] for item in cursor.description or []]
            result_rows = [dict(zip(columns, row)) for row in rows]
            return MCPExecutionResult(
                database=request.database, sql=sql, success=True,
                columns=columns, rows=result_rows, row_count=len(result_rows),
            )
        except (sqlite3.Error, OSError) as error:
            return MCPExecutionResult(
                database=request.database, sql=sql, success=False, error=str(error)
            )
        finally:
            if conn is not None:
                conn.close()

    def validate_sql(self, sql: str) -> str:
        if not sql:
            return "SQL 不能为空"
        if "--" in sql or "/*" in sql or "*/" in sql:
            return "SQL 不允许包含注释"
        if sql.count(";") > 1:
            return "只允许执行单条 SQL"
        normalized = sql.rstrip(";").strip()
        if not re.match(r"^(?:select|with)\b", normalized, re.IGNORECASE):
            return "只允许执行 SELECT 或 WITH 查询"
        if self._FORBIDDEN.search(normalized):
            return "SQL 包含禁止执行的写入或管理操作"
        tables = {match.group(1).lower() for match in self._TABLE_RE.finditer(normalized)}
        unknown = tables - {name.lower() for name in self.allowed_tables}
        if unknown:
            return "SQL 引用了未授权的数据表：" + ", ".join(sorted(unknown))
        return ""


class ResearchQueryService:
    """Run a small, explainable Text2SQL flow over the local snapshot."""

    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.router = MCPRouter()
        self.retriever = None
        self.tables = {}
        self.columns = []
        self.relations = []
        self.executor = None
        self._ready = False
        self._lock = threading.Lock()

    def query(self, message: str) -> dict:
        self._ensure_ready()
        message = str(message or "").strip()
        hits = self.retriever.retrieve(message, top_k=12)
        graph = build_schema_graph(hits, self.tables, self.columns, self.relations)
        schema_context = graph.to_prompt_context()
        plan = self._plan(message)
        if plan.get("error"):
            return self._result(message, plan, schema_context, hits)

        execution = self.router.execute(
            MCPExecutionRequest(database=DATABASE_NAME, sql=plan["sql"])
        )
        result = self._result(message, plan, schema_context, hits, execution)
        result["answer"] = format_query_result(result)
        return result

    def _ensure_ready(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            ensure_snapshot(db_path=self.db_path)
            loader = SQLiteSchemaLoader(
                self.db_path, database_name=DATABASE_NAME, business_meta=BUSINESS_META
            )
            self.tables, self.columns, self.relations = loader.load()
            self.retriever = SchemaRetriever(self.tables, self.columns, self.relations)
            self.retriever.build()
            self.executor = _SafeSQLiteExecutor(
                DATABASE_NAME, self.db_path, set(self.tables)
            )
            self.router.register_executor(DATABASE_NAME, self.executor)
            self._ready = True

    def _plan(self, message: str) -> dict:
        normalized = message.lower()
        if any(word in message for word in ("总共有多少", "一共有多少", "资讯总量", "新闻总量", "文章总量")):
            return {
                "mode": "deterministic",
                "reason": "统计本地资讯快照总量",
                "sql": "SELECT COUNT(*) AS 资讯总量 FROM articles;",
            }
        if any(word in message for word in ("按天", "每日", "每天", "日趋势", "时间趋势")):
            days = _extract_days(message, default=7)
            cutoff = int(time.time()) - days * 86400
            return {
                "mode": "deterministic",
                "reason": f"按天统计最近 {days} 天资讯趋势",
                "sql": (
                    "SELECT date(timestamp, 'unixepoch', 'localtime') AS 日期, "
                    "COUNT(*) AS 资讯数量 FROM articles "
                    f"WHERE timestamp >= {cutoff} GROUP BY 日期 ORDER BY 日期;"
                ),
            }
        if "来源" in message and any(word in message for word in ("最多", "数量", "排行", "排名")):
            return {
                "mode": "deterministic",
                "reason": "按资讯来源聚合统计",
                "sql": "SELECT source AS 来源, COUNT(*) AS 资讯数量 FROM articles GROUP BY source ORDER BY 资讯数量 DESC LIMIT 20;",
            }
        if any(word in message for word in ("各行业", "行业分布", "行业数量", "每个行业")):
            return {
                "mode": "deterministic",
                "reason": "按行业聚合统计",
                "sql": "SELECT industry_name AS 行业, COUNT(*) AS 资讯数量 FROM articles GROUP BY industry_name ORDER BY 资讯数量 DESC;",
            }
        if any(word in message for word in ("最近", "近几天", "本周", "今日")) and any(
            word in message for word in ("多少", "数量", "几条", "统计")
        ):
            days = _extract_days(message)
            cutoff = int(time.time()) - days * 86400
            return {
                "mode": "deterministic",
                "reason": f"按时间窗口统计最近 {days} 天资讯",
                "sql": f"SELECT COUNT(*) AS 资讯数量 FROM articles WHERE timestamp >= {cutoff};",
            }

        industry = _find_industry(message)
        if industry and any(word in message for word in ("多少", "数量", "几条", "统计")):
            escaped = industry.replace("'", "''")
            return {
                "mode": "deterministic",
                "reason": f"统计行业 {industry} 的资讯数量",
                "sql": f"SELECT industry_name AS 行业, COUNT(*) AS 资讯数量 FROM articles WHERE industry_name = '{escaped}' GROUP BY industry_name;",
            }

        if any(word in normalized for word in ("列出", "展示", "明细", "最新")) and any(
            word in message for word in ("资讯", "新闻", "文章")
        ):
            return {
                "mode": "deterministic",
                "reason": "返回资讯明细、摘要并按发布时间倒序",
                "sql": "SELECT chinese_title AS 中文标题, title AS 原文标题, industry_name AS 行业, source AS 来源, published_at AS 发布时间, summary AS 摘要, url AS 原文链接 FROM articles ORDER BY timestamp DESC LIMIT 20;",
            }

        return {
            "error": "当前投研快照支持行业、来源、时间窗口和资讯明细统计；实时行情与财务指标请直接询问股票代码。",
            "mode": "deterministic",
            "reason": "未匹配到安全的结构化查询模板",
        }

    @staticmethod
    def _result(message, plan, schema_context, hits, execution=None) -> dict:
        if execution is None:
            return {
                "ok": False, "route": "text2sql", "query": message,
                "answer": plan.get("error", "无法生成查询"), "sql": "",
                "rows": [], "columns": [], "row_count": 0,
                "data_source": "research_snapshot", "schema_context": schema_context,
                "schema_hits": _serialize_hits(hits), "plan": plan,
                "execution": None,
            }
        return {
            "ok": execution.success, "route": "text2sql", "query": message,
            "answer": "", "sql": execution.sql, "rows": execution.rows,
            "columns": execution.columns, "row_count": execution.row_count,
            "data_source": "research_snapshot", "schema_context": schema_context,
            "schema_hits": _serialize_hits(hits), "plan": plan,
            "execution": execution.to_dict(),
        }


def get_service() -> ResearchQueryService:
    global _SERVICE
    if _SERVICE is None:
        with _SERVICE_LOCK:
            if _SERVICE is None:
                _SERVICE = ResearchQueryService()
    return _SERVICE


def is_data_query(message: str) -> bool:
    text = str(message or "")
    return bool(
        re.search(r"(统计|数量|总量|多少|多少条|几条|排行|排名|分布|汇总|按.+分组|列出.+明细|SQL|数据表)", text)
        and re.search(r"(资讯|新闻|文章|行业|来源|赛道|数据)", text)
    )


def format_query_result(result: dict) -> str:
    if not result.get("ok"):
        return result.get("answer") or (result.get("execution") or {}).get("error") or "投研数据查询失败。"
    rows = result.get("rows") or []
    columns = result.get("columns") or []
    lines = ["### 投研数据查询结果", "", f"数据源：本地投研快照；返回 {len(rows)} 条记录。", ""]
    if not rows:
        lines.append("查询成功，但没有符合条件的数据。")
        return "\n".join(lines)
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows[:MAX_ROWS]:
        lines.append("| " + " | ".join(_display(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def _serialize_hits(hits) -> list[dict]:
    return [
        {
            "table": hit.column.table_name,
            "column": hit.column.column_name,
            "description": hit.column.description,
            "score": round(hit.score, 4),
        }
        for hit in hits
    ]


def _display(value) -> str:
    if value is None:
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _extract_days(message: str, default: int = 1) -> int:
    match = re.search(r"(?:最近|近)(\d+)\s*天", message)
    if match:
        return max(1, min(int(match.group(1)), 365))
    if "本周" in message:
        return 7
    return default


def _find_industry(message: str) -> str | None:
    # Keep this list aligned with the configured investment sectors.
    for name in ("AI / 大模型", "半导体 / 芯片", "机器人 / 自动化", "汽车 / 新能源车", "能源 / 新能源", "生物医药 / 健康", "航天 / 太空", "网络安全", "科技 / 互联网", "消费电子 / 数码", "财经 / 宏观", "科学 / 前沿"):
        if name in message or name.split(" / ")[0] in message:
            return name
    return None
