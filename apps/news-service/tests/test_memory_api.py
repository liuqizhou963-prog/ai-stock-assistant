import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server
from assistant import db as _db


class MemoryAPITests(unittest.TestCase):
    def setUp(self):
        # 每个测试用独立的临时数据库，互不干扰
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "assistant.db")
        patch.object(_db, "DB_PATH", self._db_path).start()
        patch.object(_db, "STATE_DIR", self._tmp.name).start()
        _db.init_db()
        self.client = TestClient(server.app, raise_server_exceptions=True)

    def tearDown(self):
        patch.stopall()
        self._tmp.cleanup()

    # ── GET /api/memory ──────────────────────────────────────────────

    def test_list_empty_initially(self):
        resp = self.client.get("/api/memory")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["items"], [])

    # ── POST /api/memory/save ─────────────────────────────────────────

    def test_save_returns_id(self):
        resp = self.client.post("/api/memory/save", json={
            "memory_type": "watch_topic",
            "title": "AI 算力链",
            "content": "用户关注 AI 算力链、HBM、先进封装。",
            "tags": ["AI", "算力链"],
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["id"], int)

    def test_save_then_list_returns_item(self):
        self.client.post("/api/memory/save", json={
            "memory_type": "preference",
            "title": "半导体偏好",
            "content": "更关注半导体设备和国产替代。",
            "tags": ["半导体"],
        })
        resp = self.client.get("/api/memory")
        items = resp.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "半导体偏好")
        self.assertEqual(items[0]["tags"], ["半导体"])

    def test_save_without_title_returns_400(self):
        resp = self.client.post("/api/memory/save", json={
            "memory_type": "preference",
            "content": "内容但没有标题",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])

    def test_save_without_content_returns_400(self):
        resp = self.client.post("/api/memory/save", json={
            "memory_type": "preference",
            "title": "有标题没内容",
        })
        self.assertEqual(resp.status_code, 400)

    # ── DELETE /api/memory/{id} ───────────────────────────────────────

    def test_delete_removes_memory(self):
        save_resp = self.client.post("/api/memory/save", json={
            "memory_type": "watch_topic",
            "title": "待删除",
            "content": "临时记忆",
        })
        mem_id = save_resp.json()["id"]

        del_resp = self.client.delete(f"/api/memory/{mem_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertTrue(del_resp.json()["ok"])

        items = self.client.get("/api/memory").json()["items"]
        self.assertEqual(items, [])

    def test_delete_nonexistent_still_returns_ok(self):
        # 删不存在的 id 不应该报错
        resp = self.client.delete("/api/memory/9999")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    # ── 多条记忆 ─────────────────────────────────────────────────────

    def test_multiple_memories_listed_newest_first(self):
        for i in range(3):
            self.client.post("/api/memory/save", json={
                "memory_type": "watch_topic",
                "title": f"主题{i}",
                "content": f"内容{i}",
            })
        items = self.client.get("/api/memory").json()["items"]
        self.assertEqual(len(items), 3)
        # 最后存入的排最前
        self.assertEqual(items[0]["title"], "主题2")


if __name__ == "__main__":
    unittest.main()
