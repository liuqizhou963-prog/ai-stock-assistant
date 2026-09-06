import unittest

from app.main import agent_context_text, research_run_snapshot


class AgentContextTests(unittest.TestCase):
    def test_formats_preferences_and_watchlist_for_agent(self):
        context = agent_context_text(
            [{"label": "研究周期", "value": "中长期"}],
            [{"code": "600000", "name": "浦发银行"}],
        )
        self.assertIn("研究周期：中长期", context)
        self.assertIn("600000 浦发银行", context)
        self.assertIn("仅用于研究上下文", context)

    def test_research_run_snapshot_is_reproducible_metadata(self):
        snapshot = research_run_snapshot(
            "deepseek",
            "查询 600000 最新行情",
            [{"role": "user", "content": "查询 600000 最新行情"}],
            [{"label": "研究周期", "value": "中长期"}],
            [{"code": "600000", "name": "浦发银行"}],
        )
        self.assertEqual(snapshot["model"], "deepseek")
        self.assertEqual(snapshot["query"], "查询 600000 最新行情")
        self.assertEqual(len(snapshot["systemPromptHash"]), 64)
        self.assertEqual(snapshot["watchlistCodes"], ["600000"])


if __name__ == "__main__":
    unittest.main()
