import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant import intent, market_tools


_QUOTE_TEXT = (
    'var hq_str_sh600519="贵州茅台,1330.030,1361.760,1350.600,'
    '1355.720,1325.770,0,0,5512752,7373462605.000,0,0,0,0,0,0,0,0,0,0,'
    '0,0,0,0,0,0,0,0,0,2026-07-31,15:25:48,00,H|1500|2025900.00";'
)
_GOLD_TEXT = (
    'var hq_str_hf_XAU="4071.82,4103.420,4071.82,4072.17,4111.65,'
    '4068.10,15:39:00,4103.42,4103.93,0,0,0,2026-07-31,伦敦金（现货黄金）";'
)


class MarketToolsTests(unittest.TestCase):
    def test_current_stock_name_resolves_and_parses_quote(self):
        with patch.object(market_tools, "_resolve_by_suggest", return_value="sh600519"), \
             patch.object(market_tools, "_request_text", return_value=_QUOTE_TEXT):
            quotes = market_tools.get_market_quotes("贵州茅台现在涨多少")

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["symbol"], "sh600519")
        self.assertEqual(quotes[0]["price"], 1350.6)
        self.assertEqual(quotes[0]["change_pct"], -0.82)
        self.assertEqual(quotes[0]["open"], 1330.03)
        self.assertEqual(quotes[0]["high"], 1355.72)
        self.assertEqual(quotes[0]["low"], 1325.77)
        self.assertEqual(quotes[0]["volume"], 5512752)
        self.assertEqual(quotes[0]["amount"], 7373462605.0)

    def test_broad_market_query_uses_default_indices(self):
        self.assertEqual(
            market_tools._symbols_for_message("今日大盘涨跌情况"),
            ["sh000001", "sz399001", "sz399006"],
        )

    def test_gold_uses_commodity_quote_format(self):
        with patch.object(market_tools, "_request_text", return_value=_GOLD_TEXT):
            quotes = market_tools.get_market_quotes("黄金XAU现在多少钱")

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["symbol"], "hf_XAU")
        self.assertEqual(quotes[0]["price"], 4071.82)
        self.assertEqual(quotes[0]["change_pct"], -0.77)

    def test_current_quote_is_not_prediction(self):
        self.assertEqual(intent.recognize("今日大盘涨跌情况"), intent.INTENT_NEWS_QUERY)
        self.assertEqual(intent.recognize("贵州茅台现在涨多少"), intent.INTENT_NEWS_QUERY)
        self.assertEqual(intent.recognize("明天会涨多少"), intent.INTENT_REJECT)

    def test_market_report_contains_auditable_table(self):
        with patch.object(market_tools, "_request_text", return_value=_QUOTE_TEXT):
            quotes = market_tools.get_quotes_for_symbols(["sh600519"])
        report = market_tools.format_market_quotes(quotes)
        self.assertIn("| 标的 |", report)
        self.assertIn("开盘", report)
        self.assertIn("数据来源", report)

    def test_allowed_analysis_is_not_rejected(self):
        self.assertEqual(intent.recognize("分析一下"), intent.INTENT_KNOWLEDGE_QA)
        self.assertEqual(intent.recognize("从基本面和行业趋势分析"), intent.INTENT_KNOWLEDGE_QA)
        self.assertEqual(intent.recognize("这个股票的投资价值和风险"), intent.INTENT_KNOWLEDGE_QA)


if __name__ == "__main__":
    unittest.main()
