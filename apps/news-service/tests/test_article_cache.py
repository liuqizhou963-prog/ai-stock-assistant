import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant import article_cache

# ── 测试固件 ──────────────────────────────────────────────────────────

_NOW = int(time.time())

_SAMPLE_DATA = {
    "schema_version": 1,
    "generated_at": "2026-01-01T00:00:00+08:00",
    "recent_days": 7,
    "has_ai": True,
    "stats": {},
    "industries": [
        {
            "key": "ai",
            "name": "AI / 大模型",
            "accent": "#ff5a1f",
            "total": 2,
            "items": [
                {
                    "title": "NVIDIA H100 supply chain update",
                    "url": "https://example.com/1",
                    "time": "07-29 10:00",
                    "ts": _NOW - 3600,       # 1 小时前
                    "summary": "AI 算力链和 HBM 需求持续增长",
                    "source": "TechNews",
                    "zh": "英伟达 H100 供应链更新",
                },
                {
                    "title": "Old chip news",
                    "url": "https://example.com/2",
                    "time": "07-22 10:00",
                    "ts": _NOW - 7 * 86400,  # 7 天前
                    "summary": "算力相关旧新闻",
                    "source": "OldMedia",
                    "zh": "旧芯片消息",
                },
            ],
            "points": [],
        },
        {
            "key": "robot",
            "name": "机器人",
            "accent": "#0ea5e9",
            "total": 1,
            "items": [
                {
                    "title": "Boston Dynamics latest",
                    "url": "https://example.com/3",
                    "time": "07-29 08:00",
                    "ts": _NOW - 7200,       # 2 小时前
                    "summary": "人形机器人执行器最新进展",
                    "source": "Wired",
                    "zh": "波士顿动力最新消息",
                },
            ],
            "points": [],
        },
    ],
}


def _write_data_js(directory, data=None):
    data = data or _SAMPLE_DATA
    path = os.path.join(directory, "data.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.DATA = ")
        f.write(json.dumps(data, ensure_ascii=False))
        f.write(";\n")
    return path

class ArticleCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._data_js = _write_data_js(self._tmp)
        with article_cache._cache_lock:
            article_cache._cache = []

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        with article_cache._cache_lock:
            article_cache._cache = []

    # ── reload_articles ──────────────────────────────────────────────

    def test_reload_returns_total_count(self):
        n = article_cache.reload_articles(self._data_js)
        self.assertEqual(n, 3)

    def test_reload_populates_cache(self):
        article_cache.reload_articles(self._data_js)
        self.assertEqual(len(article_cache.get_articles()), 3)

    def test_reload_attaches_industry_info(self):
        article_cache.reload_articles(self._data_js)
        ai_arts = [a for a in article_cache.get_articles() if a["industry_key"] == "ai"]
        self.assertEqual(len(ai_arts), 2)
        self.assertEqual(ai_arts[0]["industry_name"], "AI / 大模型")

    def test_reload_builds_content_text(self):
        article_cache.reload_articles(self._data_js)
        first = article_cache.get_articles()[0]
        self.assertIn("ai", first["content_text"])

    def test_reload_nonexistent_file_returns_zero(self):
        n = article_cache.reload_articles("/nonexistent/path/data.js")
        self.assertEqual(n, 0)
        self.assertEqual(article_cache.get_articles(), [])

    def test_reload_twice_replaces_cache(self):
        article_cache.reload_articles(self._data_js)
        article_cache.reload_articles(self._data_js)
        self.assertEqual(len(article_cache.get_articles()), 3)

    # ── search_articles ──────────────────────────────────────────────

    def test_search_finds_by_title_keyword(self):
        article_cache.reload_articles(self._data_js)
        results = article_cache.search_articles(["H100"])
        self.assertTrue(len(results) > 0)
        self.assertIn("H100", results[0]["title"])

    def test_search_finds_by_summary_keyword(self):
        article_cache.reload_articles(self._data_js)
        results = article_cache.search_articles(["HBM"])
        self.assertTrue(len(results) > 0)

    def test_search_filters_by_industry(self):
        article_cache.reload_articles(self._data_js)
        results = article_cache.search_articles(["机器人"], industry_key="robot")
        self.assertTrue(len(results) > 0)
        self.assertTrue(all(a["industry_key"] == "robot" for a in results))

    def test_search_empty_keywords_returns_empty(self):
        article_cache.reload_articles(self._data_js)
        self.assertEqual(article_cache.search_articles([]), [])

    def test_search_respects_limit(self):
        article_cache.reload_articles(self._data_js)
        results = article_cache.search_articles(["算力", "AI", "机器人"], limit=2)
        self.assertLessEqual(len(results), 2)

    def test_newer_article_scores_higher_than_old(self):
        article_cache.reload_articles(self._data_js)
        # 两篇都含"算力"，1小时前 vs 7天前，新的应排前面
        results = article_cache.search_articles(["算力"])
        self.assertTrue(len(results) >= 2)
        self.assertIn("H100", results[0]["title"])  # 1 小时前的排在首位


if __name__ == "__main__":
    unittest.main()
