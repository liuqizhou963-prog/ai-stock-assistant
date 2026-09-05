import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch
# fetch（抓取配置和资源上限）

import llm
# llm（大模型配置和输入上限）


def valid_fetch_config():
    # valid_fetch_config（创建合法抓取配置）
    return {
        "fetch": {
            "per_source": 5,
            "timeout": 20,
            "recent_days": 7,
        },
        "industries": [
            {"key": "ai", "name": "AI", "accent": "#ff5a1f"},
        ],
        "sources": [
            {
                "name": "测试源",
                "hint": "ai",
                "type": "rss",
                "url": "https://example.com/feed",
            },
        ],
    }


class ConfigLimitTests(unittest.TestCase):
    def test_fetch_rejects_unknown_field(self):
        config = valid_fetch_config()
        config["unexpected"] = True

        with self.assertRaises(ValueError):
            fetch.validate_config(config)

    def test_fetch_rejects_invalid_numeric_limit(self):
        config = valid_fetch_config()
        config["fetch"]["per_source"] = 1000

        with self.assertRaises(ValueError):
            fetch.validate_config(config)

    def test_fetch_rejects_duplicate_url(self):
        config = valid_fetch_config()
        config["sources"].append(dict(config["sources"][0], name="重复源"))

        with self.assertRaises(ValueError):
            fetch.validate_config(config)

    def test_fetch_rejects_invalid_url_scheme(self):
        config = valid_fetch_config()
        config["sources"][0]["url"] = "ftp://example.com/feed"

        with self.assertRaises(ValueError):
            fetch.validate_config(config)

    def test_llm_rejects_unknown_api_field(self):
        config = {
            "provider": "api",
            "api": {
                "base_url": "https://example.com/v1",
                "model": "test-model",
                "unexpected": True,
            },
        }

        with TemporaryDirectory() as directory:
            path = Path(directory) / "llm.config.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaises(llm.LLMError) as context:
                llm.load_config(directory)

        self.assertEqual(context.exception.kind, "config")

    def test_llm_rejects_oversized_prompt(self):
        with self.assertRaises(llm.LLMError) as context:
            llm.call("x" * (llm.MAX_PROMPT_CHARS + 1), "", {"provider": "claude-cli"})

        self.assertEqual(context.exception.kind, "config")

    def test_llm_rejects_excessive_timeout(self):
        with self.assertRaises(llm.LLMError) as context:
            llm.call("system", "user", {"provider": "claude-cli"}, timeout=llm.MAX_TIMEOUT + 1)

        self.assertEqual(context.exception.kind, "config")

    @patch("llm.urllib.request.urlopen")
    @patch.dict("llm.os.environ", {"LLM_API_KEY": "test-key"}, clear=True)
    def test_llm_rejects_oversized_response(self, mock_urlopen):
        response = mock_urlopen.return_value
        response.__enter__.return_value = response
        response.read.return_value = b"x" * (llm.MAX_RESPONSE_BYTES + 1)

        config = {
            "provider": "api",
            "api": {
                "base_url": "https://example.com/v1",
                "model": "test-model",
            },
        }

        with self.assertRaises(llm.LLMError) as context:
            llm.call("system", "user", config)

        self.assertEqual(context.exception.kind, "response")


if __name__ == "__main__":
    unittest.main()
