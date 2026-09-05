import json
import subprocess
import sys
import threading
import unittest
from collections import OrderedDict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server
# server（本地服务与刷新编排模块）


def completed(script_name, returncode=0, stdout="完成", stderr=""):
    # completed（创建假的子进程结果）
    command = [sys.executable, str(ROOT / "scripts" / script_name)]
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class ServerTests(unittest.TestCase):
    def setUp(self):
        server._refresh_lock = threading.Lock()
        server._refresh_results = OrderedDict()

    def test_success_runs_fetch_then_digest(self):
        calls = []

        def fake_runner(command, **kwargs):
            calls.append(Path(command[-1]).name)
            return completed(Path(command[-1]).name)

        result = server.run_refresh(runner=fake_runner)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["stage"], "complete")
        self.assertEqual(calls, ["fetch.py", "digest.py"])
        self.assertTrue(result["run_id"])
        self.assertIn("started_at", result)
        self.assertIn("finished_at", result)
        self.assertGreaterEqual(result["duration_ms"], 0)
        self.assertIn("duration_ms", result["fetch"])
        self.assertIn("duration_ms", result["digest"])

    def test_fetch_failure_skips_digest(self):
        calls = []

        def fake_runner(command, **kwargs):
            name = Path(command[-1]).name
            calls.append(name)
            return completed(name, returncode=1, stderr="抓取失败")

        result = server.run_refresh(runner=fake_runner)

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "fetch")
        self.assertEqual(result["digest"]["status"], "skipped")
        self.assertEqual(calls, ["fetch.py"])

    def test_digest_failure_returns_digest_stage(self):
        def fake_runner(command, **kwargs):
            name = Path(command[-1]).name
            if name == "digest.py":
                return completed(name, returncode=1, stderr="摘要失败")
            return completed(name)

        result = server.run_refresh(runner=fake_runner)

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "digest")
        self.assertIn("摘要失败", result["error"])

    def test_fetch_timeout_skips_digest(self):
        calls = []

        def fake_runner(command, **kwargs):
            calls.append(Path(command[-1]).name)
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        result = server.run_refresh(runner=fake_runner)

        self.assertEqual(result["fetch"]["status"], "timeout")
        self.assertEqual(result["digest"]["status"], "skipped")
        self.assertEqual(calls, ["fetch.py"])

    def test_second_refresh_is_rejected_while_first_is_running(self):
        started = threading.Event()
        release = threading.Event()
        first_result = []

        def blocking_runner(command, **kwargs):
            started.set()
            release.wait(timeout=2)
            return completed(Path(command[-1]).name)

        worker = threading.Thread(
            target=lambda: first_result.append(
                server.run_refresh(runner=blocking_runner)
            )
        )
        worker.start()
        self.assertTrue(started.wait(timeout=1))

        busy = server.run_refresh(runner=blocking_runner)
        release.set()
        worker.join(timeout=2)

        self.assertEqual(busy["status"], "busy")
        self.assertFalse(busy["ok"])
        self.assertEqual(first_result[0]["status"], "succeeded")

    def test_same_request_id_replays_without_running_again(self):
        calls = []

        def fake_runner(command, **kwargs):
            calls.append(Path(command[-1]).name)
            return completed(Path(command[-1]).name)

        first = server.run_refresh(
            runner=fake_runner,
            request_id="same-request",
        )
        second = server.run_refresh(
            runner=fake_runner,
            request_id="same-request",
        )

        self.assertEqual(calls, ["fetch.py", "digest.py"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(second["run_id"], first["run_id"])

    def test_digest_failure_restores_previous_data_file(self):
        old_data = "previous-success"
        new_data = "new-fetch-result"

        with TemporaryDirectory() as directory:
            data_path = Path(directory) / "data.js"
            data_path.write_text(old_data, encoding="utf-8")

            with patch.object(server, "DATA_PATH", str(data_path)):
                def fake_runner(command, **kwargs):
                    name = Path(command[-1]).name
                    if name == "fetch.py":
                        data_path.write_text(new_data, encoding="utf-8")
                        return completed(name)
                    return completed(name, returncode=1, stderr="摘要失败")

                result = server.run_refresh(runner=fake_runner)

            self.assertEqual(result["stage"], "digest")
            self.assertEqual(data_path.read_text(encoding="utf-8"), old_data)
            self.assertFalse(Path(str(data_path) + ".refresh-backup").exists())

    def test_response_codes(self):
        self.assertEqual(server.response_code({"status": "busy", "ok": False}), 409)
        self.assertEqual(server.response_code({"status": "succeeded", "ok": True}), 200)
        self.assertEqual(server.response_code({"status": "failed", "ok": False}), 500)

    @patch.dict("server.os.environ", {"TEST_API_KEY": "secret-value"}, clear=True)
    def test_step_output_redacts_secrets(self):
        def fake_runner(command, **kwargs):
            return completed(
                Path(command[-1]).name,
                stdout="key=secret-value sk-test-secret-value",
            )

        result = server.run_refresh(runner=fake_runner)

        self.assertNotIn("secret-value", result["fetch"]["stdout"])
        self.assertNotIn("sk-test-secret-value", result["fetch"]["stdout"])
        self.assertIn("[REDACTED]", result["fetch"]["stdout"])

    @patch.object(server.LOGGER, "info")
    def test_structured_log_contains_run_id_and_stage(self, mock_info):
        result = server.run_refresh(
            runner=lambda command, **kwargs: completed(
                Path(command[-1]).name,
            )
        )

        events = [
            json.loads(call.args[0])
            for call in mock_info.call_args_list
        ]

        self.assertTrue(events)
        self.assertTrue(all(event["run_id"] == result["run_id"] for event in events))
        self.assertIn("fetch", {event["stage"] for event in events})
        self.assertIn("digest", {event["stage"] for event in events})

    @patch.dict("server.os.environ", {server.REFRESH_TOKEN_ENV: "secret"}, clear=True)
    def test_token_is_required_when_configured(self):
        self.assertFalse(server.is_authorized("127.0.0.1", ""))
        self.assertFalse(server.is_authorized("127.0.0.1", "wrong"))
        self.assertTrue(server.is_authorized("127.0.0.1", "secret"))

    @patch.dict("server.os.environ", {}, clear=True)
    def test_loopback_is_allowed_when_token_is_not_configured(self):
        self.assertTrue(server.is_authorized("127.0.0.1", ""))
        self.assertTrue(server.is_authorized("::1", ""))
        self.assertFalse(server.is_authorized("192.168.1.20", ""))

    def test_unknown_path_and_wrong_method(self):
        client = TestClient(server.app, raise_server_exceptions=False)

        response = client.get("/api/refresh")
        self.assertEqual(response.status_code, 405)

        response = client.post("/api/unknown")
        self.assertEqual(response.status_code, 404)

    def test_research_query_returns_safe_snapshot_result(self):
        client = TestClient(server.app, raise_server_exceptions=False)

        response = client.post(
            "/api/research/query",
            json={"message": "统计各行业资讯数量"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["route"], "text2sql")
        self.assertTrue(payload["sql"].lower().startswith("select"))


if __name__ == "__main__":
    unittest.main()
