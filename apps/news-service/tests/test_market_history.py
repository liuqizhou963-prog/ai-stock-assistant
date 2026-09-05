import unittest

from assistant.market_history import calculate_indicators


class MarketHistoryIndicatorTests(unittest.TestCase):
    def test_common_volume_indicators_are_calculated(self):
        candles = [
            {"day": str(index), "open": 10 + index, "high": 11 + index,
             "low": 9 + index, "close": 10 + index, "volume": 100 * (index + 1)}
            for index in range(6)
        ]

        result = calculate_indicators(candles)

        self.assertIsNotNone(result[4]["rsi14"])
        self.assertAlmostEqual(result[4]["volume_ma5"], 300.0)
        self.assertAlmostEqual(result[4]["volume_ratio"], 5 / 3, places=5)
        self.assertIn("k", result[4])
        self.assertIn("j", result[4])


if __name__ == "__main__":
    unittest.main()
