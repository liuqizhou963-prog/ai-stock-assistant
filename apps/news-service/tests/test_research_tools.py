import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant import research_tools


class ResearchToolsTests(unittest.TestCase):
    def test_parse_screen_conditions(self):
        conditions = research_tools.parse_screen_conditions("低PE、高ROE、营收增长超过20%")
        self.assertEqual(conditions["pe_max"], 20.0)
        self.assertEqual(conditions["roe_min"], 15.0)
        self.assertEqual(conditions["revenue_growth_min"], 20.0)

    def test_screen_uses_deterministic_conditions(self):
        snapshots = {
            "sh600519": {"symbol": "sh600519", "name": "甲", "industry": "白酒", "pe": 12, "roe": 20, "revenue_growth": 25, "profit_growth": 8},
            "sz000858": {"symbol": "sz000858", "name": "乙", "industry": "白酒", "pe": 30, "roe": 20, "revenue_growth": 25, "profit_growth": 8},
        }

        result = research_tools.screen_stocks(
            list(snapshots),
            {"pe_max": 20, "roe_min": 15, "revenue_growth_min": 20},
            fetcher=lambda symbol: snapshots[symbol],
        )

        self.assertEqual([item["snapshot"]["symbol"] for item in result["matched"]], ["sh600519"])
        self.assertIn("条件选股结果", research_tools.format_screen_report(result))

    def test_compare_groups_by_returned_industry(self):
        result = research_tools.compare_snapshots([
            {"symbol": "sh600519", "name": "甲", "industry": "白酒", "pe": 10, "roe": 20, "revenue_growth": 10, "profit_growth": 8},
            {"symbol": "sz000858", "name": "乙", "industry": "白酒", "pe": 20, "roe": 10, "revenue_growth": 30, "profit_growth": 12},
        ])
        self.assertEqual(result["peer_count"], 2)
        self.assertEqual(result["items"][0]["comparison"]["pe_median"], 15)
        self.assertIn("本次提交的候选股票", result["evidence"]["scope"])


if __name__ == "__main__":
    unittest.main()
