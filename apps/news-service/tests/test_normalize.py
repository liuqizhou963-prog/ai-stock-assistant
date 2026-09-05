import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from normalize import normalize_items
# normalize_items（新闻标准化函数）


def make_item(title, url, ts, summary="", source="测试源"):
    # make_item（创建测试新闻）
    return {
        "title": title,
        "url": url,
        "time": "07-27 18:00",
        "ts": ts,
        "summary": summary,
        "source": source,
    }


class NormalizeTests(unittest.TestCase):
    def test_removes_old_items_and_sorts_newest_first(self):
        items = [
            make_item(
                "较新的新闻",
                "https://example.com/new",
                9 * 24 * 60 * 60,
            ),
            make_item(
                "过期新闻",
                "https://example.com/old",
                4 * 24 * 60 * 60,
            ),
            make_item(
                "最新的新闻",
                "https://example.com/latest",
                10 * 24 * 60 * 60,
            ),
        ]

        result = normalize_items(
            items,
            recent_days=5,
            now_ts=10 * 24 * 60 * 60,
        )

        self.assertEqual(
            [item["title"] for item in result],
            ["最新的新闻", "较新的新闻"],
        )

    def test_removes_redline_items(self):
        items = [
            make_item(
                "正常行业新闻",
                "https://example.com/normal",
                900,
            ),
            make_item(
                "包含赌博内容的新闻",
                "https://example.com/bad",
                900,
            ),
        ]

        result = normalize_items(
            items,
            redline_keywords=["赌博"],
            now_ts=1000,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "正常行业新闻")

    def test_removes_duplicate_tracking_urls(self):
        items = [
            make_item(
                "第一条新闻",
                "https://example.com/news?utm_source=rss",
                900,
            ),
            make_item(
                "重复新闻",
                "https://example.com/news?utm_medium=email",
                800,
            ),
        ]

        result = normalize_items(items, now_ts=1000)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "第一条新闻")

    def test_keeps_item_without_time(self):
        item = make_item(
            "没有时间的新闻",
            "https://example.com/no-time",
            0,
        )

        result = normalize_items([item], now_ts=1000)

        self.assertEqual(len(result), 1)

    def test_removes_future_items_beyond_clock_skew(self):
        item = make_item(
            "未来新闻",
            "https://example.com/future",
            1000 + 6 * 60,
        )

        result = normalize_items([item], now_ts=1000)

        self.assertEqual(result, [])

    def test_removes_item_without_title(self):
        item = make_item(
            "",
            "https://example.com/no-title",
            900,
        )

        result = normalize_items([item], now_ts=1000)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
