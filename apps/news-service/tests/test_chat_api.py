import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server
from assistant import db as _db
from assistant import article_cache

_NOW = int(time.time())

_FAKE_ARTICLES = [
    {
        "title": "NVIDIA H100 算力更新",
        "zh": "英伟达 H100 供应链",
        "summary": "AI 算力链和 HBM 持续增长",
        "source": "TechNews",
        "url": "https://example.com/1",
        "industry_key": "ai",
        "industry_name": "AI / 大模型",
        "content_text": "ai AI大模型 NVIDIA H100 算力 HBM TechNews",
        "time": "07-29 10:00",
        "ts": _NOW - 3600,
    },
]


class ChatAPITests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "assistant.db")
        patch.object(_db, "DB_PATH", self._db_path).start()
        patch.object(_db, "STATE_DIR", self._tmp.name).start()
        _db.init_db()
        with article_cache._cache_lock:
            article_cache._cache = list(_FAKE_ARTICLES)
        self.client = TestClient(server.app, raise_server_exceptions=True)

    def tearDown(self):
        patch.stopall()
        with article_cache._cache_lock:
            article_cache._cache = []
        self._tmp.cleanup()

    def test_missing_message_returns_400(self):
        resp = self.client.post("/api/assistant/chat", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])

    def test_empty_message_returns_400(self):
        resp = self.client.post("/api/assistant/chat", json={"message": "  "})
        self.assertEqual(resp.status_code, 400)

    def test_valid_message_returns_ok(self):
        resp = self.client.post("/api/assistant/chat", json={"message": "AI 算力链"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("answer", data)
        self.assertIsInstance(data["articles"], list)
        self.assertIsInstance(data["memory_suggestions"], list)

    def test_matching_message_returns_articles(self):
        resp = self.client.post("/api/assistant/chat", json={"message": "AI 算力链"})
        data = resp.json()
        self.assertGreater(len(data["articles"]), 0)
        art = data["articles"][0]
        self.assertIn("title", art)
        self.assertIn("url", art)
        self.assertIn("reason", art)

    def test_no_match_returns_empty_articles(self):
        resp = self.client.post("/api/assistant/chat", json={"message": "量子外星技术"})
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["articles"], [])

    def test_industry_key_filters_results(self):
        resp = self.client.post("/api/assistant/chat", json={
            "message": "AI 算力链",
            "industry_key": "robot",
        })
        data = resp.json()
        self.assertEqual(data["articles"], [])

    def test_memory_expands_search(self):
        self.client.post("/api/memory/save", json={
            "memory_type": "watch_topic",
            "title": "HBM",
            "content": "关注 HBM 和先进封装",
            "tags": ["HBM"],
        })
        resp = self.client.post("/api/assistant/chat", json={"message": "最近有什么新消息"})
        data = resp.json()
        self.assertGreater(len(data["articles"]), 0)


if __name__ == "__main__":
    unittest.main()
