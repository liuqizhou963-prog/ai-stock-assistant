from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .objects import MCPExecutionRequest, MCPExecutionResult


class SQLiteMCPExecutor:
    """
    SQLite MCP 执行器。

    这里模拟 MCP 路由到数据库 API 后的执行过程。
    为了 Demo 安全，只允许执行 SELECT / WITH 查询。
    """

    def __init__(
        self,
        database: str,
        db_path: str | Path,
        timeout: int = 30,
        readonly: bool = True,
    ):
        self.database = database
        self.db_path = str(db_path)
        self.timeout = timeout
        self.readonly = readonly

    def execute(self, request: MCPExecutionRequest) -> MCPExecutionResult:
        """
        执行 SQL。
        """
        if request.database != self.database:
            return MCPExecutionResult(
                database=request.database,
                sql=request.sql,
                success=False,
                error=f"数据库路由错误：当前执行器只处理 {self.database}",
            )

        sql = request.sql.strip()

        if self.readonly and not self._is_readonly_sql(sql):
            return MCPExecutionResult(
                database=request.database,
                sql=sql,
                success=False,
                error="只允许执行 SELECT / WITH 查询。",
            )

        try:
            conn = sqlite3.connect(self.db_path, timeout=self.timeout)
            conn.row_factory = sqlite3.Row

            rows = conn.execute(sql).fetchall()
            columns = list(rows[0].keys()) if rows else []

            result_rows: List[Dict[str, Any]] = [
                dict(row)
                for row in rows
            ]

            conn.close()

            return MCPExecutionResult(
                database=request.database,
                sql=sql,
                success=True,
                columns=columns,
                rows=result_rows,
                row_count=len(result_rows),
            )

        except Exception as exc:
            return MCPExecutionResult(
                database=request.database,
                sql=sql,
                success=False,
                error=str(exc),
            )

    def _is_readonly_sql(self, sql: str) -> bool:
        """
        判断是否为只读 SQL。
        """
        normalized = re.sub(r"\s+", " ", sql.strip()).lower()
        return normalized.startswith("select ") or normalized.startswith("with ")
