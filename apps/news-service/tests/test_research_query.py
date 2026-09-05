import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assistant import agent_core
from assistant import intent
from assistant.research_query import (
    DATABASE_NAME,
    ResearchQueryService,
    _SafeSQLiteExecutor,
)
from mcp_router.objects import MCPExecutionRequest


class ResearchQueryTests(unittest.TestCase):
    def test_industry_summary_uses_schema_query_and_readonly_sql(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ResearchQueryService(Path(temp_dir) / "snapshot.db")
            result = service.query("统计各行业资讯数量")

        self.assertTrue(result["ok"])
        self.assertEqual(result["route"], "text2sql")
        self.assertTrue(result["sql"].lstrip().lower().startswith("select"))
        self.assertTrue(result["rows"])
        self.assertIn("industry_name", result["schema_context"])

    def test_unsupported_question_does_not_generate_freeform_sql(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ResearchQueryService(Path(temp_dir) / "snapshot.db")
            result = service.query("帮我预测下周涨跌")

        self.assertFalse(result["ok"])
        self.assertEqual(result["sql"], "")
        self.assertIn("当前投研快照支持", result["answer"])

    def test_common_total_and_daily_trend_queries_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ResearchQueryService(Path(temp_dir) / "snapshot.db")
            total = service.query("资讯总量是多少")
            trend = service.query("统计最近7天每天的资讯数量")

        self.assertTrue(total["ok"])
        self.assertIn("COUNT(*)", total["sql"])
        self.assertTrue(trend["ok"])
        self.assertIn("GROUP BY 日期", trend["sql"])

    def test_latest_details_include_summary_and_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ResearchQueryService(Path(temp_dir) / "snapshot.db").query("列出最新资讯明细")

        self.assertTrue(result["ok"])
        self.assertIn("摘要", result["columns"])
        self.assertIn("原文链接", result["columns"])

    def test_safe_executor_blocks_write_and_unknown_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "research.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY, title TEXT)")
            conn.execute("INSERT INTO articles(title) VALUES ('test')")
            conn.commit()
            conn.close()

            executor = _SafeSQLiteExecutor(DATABASE_NAME, db_path, {"articles"})
            write = executor.execute(MCPExecutionRequest(DATABASE_NAME, "DELETE FROM articles"))
            unknown = executor.execute(MCPExecutionRequest(DATABASE_NAME, "SELECT * FROM secrets"))
            read = executor.execute(MCPExecutionRequest(DATABASE_NAME, "SELECT title FROM articles"))

        self.assertFalse(write.success)
        self.assertFalse(unknown.success)
        self.assertTrue(read.success)
        self.assertEqual(read.rows, [{"title": "test"}])

    def test_agent_routes_statistics_question_to_research_tool(self):
        plan = agent_core.make_plan("统计各行业资讯数量", intent.INTENT_NEWS_QUERY, None)

        self.assertEqual(plan[0]["tool"], "query_research_data")

    def test_quick_safety_rejects_before_intent_model(self):
        with patch.object(agent_core.intent, "recognize") as recognize:
            result = agent_core.prepare("明天应该买什么股票", [], [], [])

        recognize.assert_not_called()
        self.assertTrue(result["terminal"])
        self.assertEqual(result["agent"]["safety"]["reason"], "trading_advice")


if __name__ == "__main__":
    unittest.main()
