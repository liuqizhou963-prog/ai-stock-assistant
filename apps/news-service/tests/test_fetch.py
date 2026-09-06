import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch
# fetch（多源抓取模块）


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "fetch": {
                "per_source": 1,
                # These tests cover source grouping and failure isolation, not
                # the rolling freshness filter.
                "recent_days": 365,
            },
            "industries": [
                {
                    "key": "ai",
                    "name": "AI / 大模型",
                    "accent": "#ff5a1f"
                },
                {
                    "key": "space",
                    "name": "航天 / 太空",
                    "accent": "#8b5cf6"
                }
            ],
            "sources": [
                {
                    "name": "测试 AI 源",
                    "hint": "ai",
                    "type": "rss",
                    "url": "https://example.com/ai.xml"
                },
                {
                    "name": "测试航天源",
                    "hint": "space",
                    "type": "rss",
                    "url": "https://example.com/space.xml"
                }
            ]
        }

    @patch("fetch.fetch_one")
    def test_groups_sources_by_industry(self, mock_fetch_one):
        def fake_fetch(url, source_name):
            if "space" in url:
                return [
                    {
                        "title": "航天新闻",
                        "url": "https://example.com/space-news",
                        "time": "07-27 18:00",
                        "ts": 1785146400,
                        "summary": "航天测试摘要",
                        "source": source_name
                    }
                ]

            return [
                {
                    "title": "AI 新闻 1",
                    "url": "https://example.com/ai-news-1",
                    "time": "07-27 17:00",
                    "ts": 1785142800,
                    "summary": "AI 摘要 1",
                    "source": source_name
                },
                {
                    "title": "AI 新闻 2",
                    "url": "https://example.com/ai-news-2",
                    "time": "07-27 16:00",
                    "ts": 1785139200,
                    "summary": "AI 摘要 2",
                    "source": source_name
                }
            ]

        mock_fetch_one.side_effect = fake_fetch

        result = fetch.build_result(self.config)

        self.assertEqual(
            [item["key"] for item in result["industries"]],
            ["ai", "space"]
        )
        self.assertEqual(len(result["industries"][0]["items"]), 1)
        self.assertEqual(
            result["industries"][0]["items"][0]["title"],
            "AI 新闻 1"
        )
        self.assertEqual(
            result["industries"][1]["items"][0]["title"],
            "航天新闻"
        )

    @patch("fetch.fetch_one")
    def test_one_source_failure_does_not_stop_other_sources(
        self,
        mock_fetch_one
    ):
        def fake_fetch(url, source_name):
            if "space" in url:
                raise TimeoutError("测试超时")

            return [
                {
                    "title": "正常新闻",
                    "url": "https://example.com/news",
                    "time": "07-27 18:00",
                    "ts": 1785146400,
                    "summary": "正常摘要",
                    "source": source_name
                }
            ]

        mock_fetch_one.side_effect = fake_fetch

        result = fetch.build_result(self.config)

        ai = result["industries"][0]
        space = result["industries"][1]

        self.assertEqual(len(ai["items"]), 1)
        self.assertEqual(len(space["items"]), 0)
        self.assertTrue(space["sources"][0]["ok"] is False)
        self.assertIn("测试超时", space["sources"][0]["error"])

    def test_build_web_data_matches_page_contract(self):
        result = {
            "industries": [
                {
                    "key": "ai",
                    "name": "AI / 大模型",
                    "accent": "#ff5a1f",
                    "total": 1,
                    "items": [
                        {
                            "title": "测试新闻",
                            "url": "https://example.com/news",
                            "time": "07-27 18:00",
                            "ts": 1785146400,
                            "summary": "测试摘要",
                            "source": "测试源",
                        }
                    ],
                }
            ]
        }

        data = fetch.build_web_data(self.config, result)

        self.assertIn("generated_at", data)
        self.assertEqual(data["recent_days"], self.config["fetch"]["recent_days"])
        self.assertFalse(data["has_ai"])
        self.assertEqual(data["stats"]["industries"], 1)
        self.assertEqual(data["stats"]["total_sources"], 1)
        self.assertEqual(data["stats"]["total_items"], 1)
        self.assertEqual(data["industries"][0]["points"], [])

    def test_write_data_file_creates_loadable_javascript(self):
        data = {
            "schema_version": 1,
            "generated_at": "2026-07-28T12:00:00+08:00",
            "recent_days": 7,
            "industries": [],
            "stats": {},
            "has_ai": False,
        }

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data.js"
            fetch.write_data_file(data, path)
            content = path.read_text(encoding="utf-8")

        prefix = "window.DATA = "
        suffix = ";\n"

        self.assertTrue(content.startswith(prefix))
        self.assertTrue(content.endswith(suffix))

        payload = content[len(prefix):-len(suffix)]
        self.assertEqual(json.loads(payload), data)

    def test_fetch_main_writes_data_when_some_sources_fail(self):
        config = self.config
        result = {
            "industries": [
                {
                    "key": "ai",
                    "name": "AI / 大模型",
                    "accent": "#ff5a1f",
                    "total": 2,
                    "items": [],
                }
            ],
            "sources": [
                {"name": "失败源", "ok": False},
                {"name": "成功源", "ok": True},
            ],
        }

        with patch("fetch.load_config", return_value=config), patch(
            "fetch.build_result",
            return_value=result,
        ), patch("fetch.write_data_file") as mock_write:
            fetch.main()

        mock_write.assert_called_once()

    def test_fetch_main_fails_when_all_sources_fail(self):
        config = self.config
        result = {
            "industries": [],
            "sources": [
                {"name": "失败源一", "ok": False},
                {"name": "失败源二", "ok": False},
            ],
        }

        with patch("fetch.load_config", return_value=config), patch(
            "fetch.build_result",
            return_value=result,
        ), patch("fetch.write_data_file") as mock_write:
            with self.assertRaises(SystemExit) as context:
                fetch.main()

        self.assertEqual(context.exception.code, 2)
        mock_write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
