import json
import socket
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import llm
# llm（大模型统一适配层）


class LLMAdapterTests(unittest.TestCase):
    def write_config(self, config):
        # write_config（在临时目录写入测试配置）
        temp_dir = TemporaryDirectory()
        path = Path(temp_dir.name) / "llm.config.json"
        path.write_text(
            json.dumps(config),
            encoding="utf-8",
        )
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def test_load_config_accepts_cli_provider(self):
        root = self.write_config({"provider": "claude-cli"})

        config = llm.load_config(root)

        self.assertEqual(config["provider"], "claude-cli")

    def test_load_config_rejects_unknown_provider(self):
        root = self.write_config({"provider": "unknown"})

        with self.assertRaises(llm.LLMError) as context:
            llm.load_config(root)

        self.assertEqual(context.exception.kind, "config")

    @patch("llm.subprocess.run")
    @patch("llm.shutil.which", return_value="claude")
    def test_cli_returns_stdout(self, mock_which, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout="模型回答",
            stderr="",
        )

        result = llm.call(
            "系统指令",
            "用户问题",
            {"provider": "claude-cli"},
        )

        self.assertEqual(result, "模型回答")
        mock_which.assert_called_once_with("claude")
        self.assertEqual(mock_run.call_args.kwargs["input"], "用户问题")

    @patch("llm.shutil.which", return_value=None)
    def test_cli_missing_command_has_unavailable_error(self, mock_which):
        with self.assertRaises(llm.LLMError) as context:
            llm.call(
                "系统指令",
                "用户问题",
                {"provider": "claude-cli"},
            )

        self.assertEqual(context.exception.kind, "unavailable")

    @patch("llm.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("claude", 1))
    @patch("llm.shutil.which", return_value="claude")
    def test_cli_timeout_has_timeout_error(self, mock_which, mock_run):
        with self.assertRaises(llm.LLMError) as context:
            llm.call(
                "系统指令",
                "用户问题",
                {"provider": "claude-cli"},
            )

        self.assertEqual(context.exception.kind, "timeout")

    @patch.dict("llm.os.environ", {}, clear=True)
    def test_api_without_key_has_config_error(self):
        config = {
            "provider": "api",
            "api": {
                "base_url": "https://example.com/v1",
                "api_key_env": "LLM_API_KEY",
                "model": "test-model",
            },
        }

        with self.assertRaises(llm.LLMError) as context:
            llm.call("系统指令", "用户问题", config)

        self.assertEqual(context.exception.kind, "config")

    @patch("llm.urllib.request.urlopen")
    @patch.dict("llm.os.environ", {"LLM_API_KEY": "test-key"}, clear=True)
    def test_api_returns_message_content(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "choices": [
                {"message": {"content": "接口回答"}}
            ]
        }).encode("utf-8")
        mock_urlopen.return_value = response

        config = {
            "provider": "api",
            "api": {
                "base_url": "https://example.com/v1",
                "api_key_env": "LLM_API_KEY",
                "model": "test-model",
            },
        }

        result = llm.call("系统指令", "用户问题", config)

        self.assertEqual(result, "接口回答")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://example.com/v1/chat/completions",
        )

    @patch("llm.urllib.request.urlopen")
    @patch.dict("llm.os.environ", {"LLM_API_KEY": "test-key"}, clear=True)
    def test_api_stream_returns_text_deltas(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__iter__.return_value = iter([
            'data: {"choices":[{"delta":{"content":"第一"}}]}\n\n'.encode("utf-8"),
            'data: {"choices":[{"delta":{"content":"段"}}]}\n\n'.encode("utf-8"),
            b'data: [DONE]\n\n',
        ])
        mock_urlopen.return_value = response

        config = {
            "provider": "api",
            "api": {
                "base_url": "https://example.com/v1",
                "api_key_env": "LLM_API_KEY",
                "model": "test-model",
            },
        }

        result = list(llm.stream_call("系统指令", "用户问题", config))

        self.assertEqual(result, ["第一", "段"])
        request = mock_urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertTrue(body["stream"])

    @patch("llm.urllib.request.urlopen")
    @patch.dict("llm.os.environ", {"LLM_API_KEY": "test-key"}, clear=True)
    def test_api_bad_response_has_response_error(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"unexpected": true}'
        mock_urlopen.return_value = response

        config = {
            "provider": "api",
            "api": {
                "base_url": "https://example.com/v1",
                "api_key_env": "LLM_API_KEY",
                "model": "test-model",
            },
        }

        with self.assertRaises(llm.LLMError) as context:
            llm.call("系统指令", "用户问题", config)

        self.assertEqual(context.exception.kind, "response")

    @patch("llm.urllib.request.urlopen")
    @patch.dict("llm.os.environ", {"LLM_API_KEY": "test-key"}, clear=True)
    def test_api_timeout_has_timeout_error(self, mock_urlopen):
        mock_urlopen.side_effect = llm.urllib.error.URLError(
            socket.timeout("测试超时")
        )

        config = {
            "provider": "api",
            "api": {
                "base_url": "https://example.com/v1",
                "api_key_env": "LLM_API_KEY",
                "model": "test-model",
            },
        }

        with self.assertRaises(llm.LLMError) as context:
            llm.call("系统指令", "用户问题", config)

        self.assertEqual(context.exception.kind, "timeout")


if __name__ == "__main__":
    unittest.main()
