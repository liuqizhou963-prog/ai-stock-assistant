import unittest
from unittest.mock import patch

import server


class PriceAlertTests(unittest.IsolatedAsyncioTestCase):
    async def test_matching_alert_is_triggered_and_disabled(self):
        alert = {
            "id": 7,
            "symbol": "sh600519",
            "name": "贵州茅台",
            "condition": "below",
            "threshold": 1351.6,
            "enabled": 1,
        }
        quote = {"symbol": "sh600519", "price": 1350.6}
        with patch.object(server._research_store, "list_alerts", return_value=[alert]), \
             patch.object(server._market_tools, "get_quotes_for_symbols", return_value=[quote]), \
             patch.object(server._research_store, "mark_alert_triggered") as mark_triggered:
            triggered = await server._check_price_alerts()

        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0]["alert"]["id"], 7)
        mark_triggered.assert_called_once_with(7)

    async def test_non_matching_alert_remains_active(self):
        alert = {
            "id": 8,
            "symbol": "sh600519",
            "name": "贵州茅台",
            "condition": "above",
            "threshold": 1351.6,
            "enabled": 1,
        }
        quote = {"symbol": "sh600519", "price": 1350.6}
        with patch.object(server._research_store, "list_alerts", return_value=[alert]), \
             patch.object(server._market_tools, "get_quotes_for_symbols", return_value=[quote]), \
             patch.object(server._research_store, "mark_alert_triggered") as mark_triggered:
            triggered = await server._check_price_alerts()

        self.assertEqual(triggered, [])
        mark_triggered.assert_not_called()


if __name__ == "__main__":
    unittest.main()
