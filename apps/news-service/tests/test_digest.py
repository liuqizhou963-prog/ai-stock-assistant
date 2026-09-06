import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import digest
# digest（摘要、翻译和原文溯源模块）

import llm
# llm（大模型统一适配层）


def make_industry(key="ai"):
    # make_industry（创建固定行业测试数据）
    return {
        "key": key,
        "name": "AI / 大模型" if key == "ai" else "航天 / 太空",
        "accent": "#ff5a1f" if key == "ai" else "#8b5cf6",
        "total": 1,
        "items": [
            {
                "title": "英文新闻一",
                "url": "https://example.com/news-1",
                "summary": "新闻摘要一",
                "source": "测试源",
            },
            {
                "title": "英文新闻二",
                "url": "https://example.com/news-2",
                "summary": "新闻摘要二",
                "source": "测试源",
            },
            {
                "title": "英文新闻三",
                "url": "https://example.com/news-3",
                "summary": "新闻摘要三",
                "source": "测试源",
            },
        ],
        "points": [],
    }


def valid_model_answer():
    # valid_model_answer（创建合法的固定模型回答）
    return json.dumps({
        "points": [
            {"t": "行业出现重要变化。", "refs": [0]},
            {"t": "企业发布新的产品动向。", "refs": [1]},
            {"t": "市场正在形成新的趋势。", "refs": [2]},
        ],
        "items": [
            {"i": 0, "zh": "中文新闻一"},
            {"i": 1, "zh": "中文新闻二"},
            {"i": 2, "zh": "中文新闻三"},
        ],
    })


class DigestTests(unittest.TestCase):
    def test_extracts_json_from_code_fence(self):
        value = digest.extract_json(
            "```json\n{\"points\": [], \"items\": []}\n```"
        )

        self.assertEqual(value["points"], [])
        self.assertEqual(value["items"], [])

    def test_rejects_invalid_reference(self):
        value = json.loads(valid_model_answer())
        value["points"][0]["refs"] = [99]

        with self.assertRaises(llm.LLMError) as context:
            digest.validate_model_result(value, item_count=3)

        self.assertEqual(context.exception.kind, "response")

    def test_process_industry_maps_titles_and_point_urls(self):
        industry = make_industry()

        def fake_call(system, user):
            return valid_model_answer()

        result, ok = digest.process_industry(industry, fake_call)

        self.assertTrue(ok)
        self.assertEqual(result["items"][0]["zh"], "中文新闻一")
        self.assertEqual(
            result["points"][0]["url"],
            "https://example.com/news-1",
        )

    def test_invalid_response_is_retried(self):
        industry = make_industry()
        responses = ["不是 JSON", valid_model_answer()]
        calls = []

        def fake_call(system, user):
            calls.append(user)
            return responses.pop(0)

        result, ok = digest.process_industry(
            industry,
            fake_call,
            attempts=2,
        )

        self.assertTrue(ok)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result["points"]), 3)

    def test_config_error_is_not_retried(self):
        industry = make_industry()
        calls = []

        def fake_call(system, user):
            calls.append(user)
            raise llm.LLMError("config", "缺少配置")

        result, ok = digest.process_industry(
            industry,
            fake_call,
            attempts=3,
        )

        self.assertFalse(ok)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["points"], [])

    def test_one_industry_failure_does_not_stop_other_industries(self):
        data = {
            "schema_version": 1,
            "generated_at": "2026-07-28T12:00:00+08:00",
            "recent_days": 7,
            "industries": [
                make_industry("ai"),
                make_industry("space"),
            ],
            "stats": {},
            "has_ai": False,
        }

        def fake_call(system, user):
            if "航天" in user:
                raise llm.LLMError("config", "测试失败")
            return valid_model_answer()

        result = digest.digest_data(
            data,
            {"provider": "fake"},
            call_model=fake_call,
        )

        self.assertEqual(len(result["industries"][0]["points"]), 3)
        self.assertEqual(result["industries"][1]["points"], [])
        self.assertFalse(result["has_ai"])

    def test_load_and_write_data_file(self):
        data = {
            "schema_version": 1,
            "generated_at": "2026-07-28T12:00:00+08:00",
            "recent_days": 7,
            "industries": [],
            "stats": {},
            "has_ai": False,
        }

        path = ROOT / "tests" / "_temporary_digest_data.js"

        try:
            digest.write_data_file(data, path)
            self.assertEqual(digest.load_data_file(path), data)
        finally:
            if path.exists():
                path.unlink()

    @patch("digest.llm.load_config")
    @patch("digest.load_data_file")
    @patch("digest.digest_data")
    @patch("digest.write_data_file")
    def test_digest_main_does_not_write_when_industry_fails(
        self,
        mock_write,
        mock_digest,
        mock_load_data,
        mock_load_config,
    ):
        mock_load_config.return_value = {"provider": "claude-cli"}
        mock_load_data.return_value = {
            "industries": [{"items": [{"title": "新闻"}]}]
        }
        mock_digest.return_value = {
            "industries": [{"items": [{"title": "新闻"}]}],
            "has_ai": False,
        }

        with self.assertRaises(SystemExit) as context:
            digest.main()

        self.assertEqual(context.exception.code, 2)
        mock_write.assert_not_called()

    @patch("digest.llm.load_config")
    @patch("digest.load_data_file")
    @patch("digest.write_data_file")
    def test_digest_main_keeps_fetched_data_when_llm_config_is_missing(
        self,
        mock_write,
        mock_load_data,
        mock_load_config,
    ):
        mock_load_config.side_effect = digest.llm.LLMError("config", "缺少 llm.config.json")
        fetched = {
            "industries": [{"items": [{"title": "新闻"}]}],
            "has_ai": True,
        }
        mock_load_data.return_value = fetched

        digest.main()

        mock_write.assert_called_once()
        saved = mock_write.call_args.args[0]
        self.assertFalse(saved["has_ai"])
        self.assertEqual(saved["industries"], fetched["industries"])


if __name__ == "__main__":
    unittest.main()
