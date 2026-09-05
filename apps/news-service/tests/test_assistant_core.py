import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant.assistant_core import (
    parse_llm_json,
    build_user_message,
    chat,
)

_FAKE_CONFIG = {"provider": "api", "api": {"base_url": "https://x.com", "model": "m"}}

_SAMPLE_ARTICLES = [
    {"title": "H100 算力", "zh": "英伟达H100", "source": "TechNews",
     "url": "https://x.com/1", "industry_name": "AI", "summary": "算力增长", "time": "07-29", "ts": 1},
    {"title": "机器人突破", "zh": "机器人", "source": "Wired",
     "url": "https://x.com/2", "industry_name": "机器人", "summary": "执行器提升", "time": "07-28", "ts": 2},
]

_SAMPLE_MEMORIES = [
    {"memory_type": "watch_topic", "title": "AI 算力链",
     "content": "关注 HBM 先进封装", "tags": ["AI"]},
]


class ParseLLMJsonTests(unittest.TestCase):
    def test_valid_json(self):
        text = '{"answer": "好的", "articles": [], "memory_suggestions": []}'
        result = parse_llm_json(text)
        self.assertEqual(result["answer"], "好的")

    def test_code_fence_json(self):
        text = '这是回答\n```json\n{"answer": "好", "articles": []}\n```'
        result = parse_llm_json(text)
        self.assertEqual(result["answer"], "好")

    def test_invalid_falls_back_to_plain_text(self):
        text = "这不是 JSON"
        result = parse_llm_json(text)
        self.assertEqual(result["answer"], text)
        self.assertEqual(result["articles"], [])
        self.assertEqual(result["memory_suggestions"], [])

    def test_empty_string_falls_back(self):
        result = parse_llm_json("")
        self.assertEqual(result["articles"], [])


class BuildUserMessageTests(unittest.TestCase):
    def test_contains_question(self):
        msg = build_user_message("AI 算力链最新情况", _SAMPLE_MEMORIES, _SAMPLE_ARTICLES)
        self.assertIn("AI 算力链最新情况", msg)

    def test_contains_memory_label(self):
        msg = build_user_message("问题", _SAMPLE_MEMORIES, _SAMPLE_ARTICLES)
        self.assertIn("关注主题", msg)
        self.assertIn("AI 算力链", msg)

    def test_contains_article_index(self):
        msg = build_user_message("问题", [], _SAMPLE_ARTICLES)
        self.assertIn("0.", msg)
        self.assertIn("1.", msg)
        self.assertIn("H100", msg)

    def test_empty_memories_shows_placeholder(self):
        msg = build_user_message("问题", [], _SAMPLE_ARTICLES)
        self.assertIn("暂无记忆", msg)

    def test_focus_context_is_injected(self):
        msg = build_user_message(
            "这条什么影响",
            [],
            _SAMPLE_ARTICLES,
            focus={
                "kind": "article",
                "title": "英伟达H100",
                "source": "TechNews",
                "url": "https://x.com/1",
            },
        )
        self.assertIn("用户正在追问的资讯", msg)
        self.assertIn("英伟达H100", msg)
        self.assertIn("来源：TechNews", msg)
        self.assertIn("均指上面这一条", msg)

    def test_focus_digest_point_uses_its_own_label(self):
        msg = build_user_message(
            "展开说说",
            [],
            [],
            focus={"kind": "digest_point", "title": "AI: 算力需求继续超预期"},
        )
        self.assertIn("用户正在追问的行业要点", msg)

    def test_no_focus_adds_no_section(self):
        msg = build_user_message("问题", [], _SAMPLE_ARTICLES)
        self.assertNotIn("正在追问", msg)


class ChatTests(unittest.TestCase):
    def test_success_returns_enriched_articles(self):
        llm_response = json.dumps({
            "answer": "根据你关注的算力链，推荐如下",
            "articles": [{"index": 0, "reason": "与HBM相关"}],
            "memory_suggestions": [],
        })
        with patch("assistant.assistant_core.load_config", return_value=_FAKE_CONFIG), \
             patch("assistant.assistant_core._llm_call", return_value=llm_response):
            ok, answer, articles, suggestions = chat(
                "AI 算力链最新", _SAMPLE_MEMORIES, _SAMPLE_ARTICLES
            )
        self.assertTrue(ok)
        self.assertIn("算力链", answer)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["reason"], "与HBM相关")
        self.assertEqual(articles[0]["title"], "H100 算力")

    def test_llm_error_returns_false(self):
        from scripts.llm import LLMError
        with patch("assistant.assistant_core.load_config", return_value=_FAKE_CONFIG), \
             patch("assistant.assistant_core._llm_call", side_effect=LLMError("timeout", "超时")):
            ok, answer, articles, suggestions = chat("问题", [], _SAMPLE_ARTICLES)
        self.assertFalse(ok)
        self.assertIn("超时", answer)
        self.assertEqual(articles, [])

    def test_config_error_returns_false(self):
        from scripts.llm import LLMError
        with patch("assistant.assistant_core.load_config", side_effect=LLMError("config", "缺少配置")):
            ok, answer, articles, suggestions = chat("问题", [], _SAMPLE_ARTICLES)
        self.assertFalse(ok)
        self.assertIn("配置", answer)

    def test_invalid_json_falls_back_to_candidates(self):
        with patch("assistant.assistant_core.load_config", return_value=_FAKE_CONFIG), \
             patch("assistant.assistant_core._llm_call", return_value="这不是JSON"):
            ok, answer, articles, suggestions = chat("问题", [], _SAMPLE_ARTICLES)
        self.assertTrue(ok)
        self.assertGreater(len(articles), 0)

    def test_no_candidates_with_llm_error_returns_empty(self):
        from scripts.llm import LLMError
        with patch("assistant.assistant_core.load_config", return_value=_FAKE_CONFIG), \
             patch("assistant.assistant_core._llm_call", side_effect=LLMError("config", "无key")):
            ok, answer, articles, suggestions = chat("问题", [], [])
        self.assertFalse(ok)
        self.assertEqual(articles, [])


if __name__ == "__main__":
    unittest.main()
