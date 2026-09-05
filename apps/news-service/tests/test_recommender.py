import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant.recommender import extract_keywords, keywords_from_memories, recommend

_FAKE_ARTICLES = [
    {
        "title": "NVIDIA H100 supply chain",
        "zh": "英伟达 H100 供应链更新",
        "summary": "AI 算力链和 HBM 需求持续增长",
        "source": "TechNews",
        "url": "https://example.com/1",
        "industry_key": "ai",
        "industry_name": "AI / 大模型",
        "content_text": "ai AI大模型 NVIDIA H100 supply chain 英伟达 HBM TechNews",
        "ts": 9999999999,
    },
    {
        "title": "Robot arm breakthrough",
        "zh": "机器人手臂重大突破",
        "summary": "机器人执行器精度大幅提升",
        "source": "RobotDaily",
        "url": "https://example.com/2",
        "industry_key": "robot",
        "industry_name": "机器人",
        "content_text": "robot 机器人 Robot arm 机器人执行器 RobotDaily",
        "ts": 9999999998,
    },
]


class ExtractKeywordsTests(unittest.TestCase):
    def test_splits_on_spaces(self):
        kws = extract_keywords("AI 算力链 HBM")
        self.assertIn("AI", kws)
        self.assertIn("算力链", kws)
        self.assertIn("HBM", kws)

    def test_splits_on_chinese_punctuation(self):
        kws = extract_keywords("AI，半导体。国产替代")
        self.assertIn("AI", kws)
        self.assertIn("半导体", kws)
        self.assertIn("国产替代", kws)

    def test_filters_single_char(self):
        kws = extract_keywords("a AI b 半导体")
        self.assertNotIn("a", kws)
        self.assertNotIn("b", kws)
        self.assertIn("AI", kws)

    def test_deduplicates(self):
        kws = extract_keywords("AI AI 算力 算力")
        self.assertEqual(kws.count("AI"), 1)
        self.assertEqual(kws.count("算力"), 1)

    def test_empty_string_returns_empty(self):
        self.assertEqual(extract_keywords(""), [])


class KeywordsFromMemoriesTests(unittest.TestCase):
    def test_extracts_from_title_and_content(self):
        memories = [{"title": "AI 算力链", "content": "关注 HBM 先进封装", "tags": []}]
        kws = keywords_from_memories(memories)
        self.assertIn("AI", kws)
        self.assertIn("算力链", kws)
        self.assertIn("HBM", kws)

    def test_extracts_tags(self):
        memories = [{"title": "", "content": "", "tags": ["半导体", "国产替代"]}]
        kws = keywords_from_memories(memories)
        self.assertIn("半导体", kws)
        self.assertIn("国产替代", kws)

    def test_no_duplicates_across_fields(self):
        memories = [{"title": "AI 算力", "content": "AI 算力", "tags": ["AI"]}]
        kws = keywords_from_memories(memories)
        self.assertEqual(kws.count("AI"), 1)

    def test_empty_memories_returns_empty(self):
        self.assertEqual(keywords_from_memories([]), [])


class RecommendTests(unittest.TestCase):
    def test_returns_matching_articles(self):
        with patch("assistant.article_cache._cache", _FAKE_ARTICLES):
            results = recommend("AI 算力链")
        self.assertTrue(len(results) > 0)
        self.assertTrue(any("H100" in a["title"] for a in results))

    def test_filters_by_industry_key(self):
        with patch("assistant.article_cache._cache", _FAKE_ARTICLES):
            results = recommend("机器人", industry_key="robot")
        self.assertTrue(all(a["industry_key"] == "robot" for a in results))

    def test_memory_keywords_help_find_articles(self):
        memories = [{"title": "HBM", "content": "关注 HBM", "tags": []}]
        with patch("assistant.article_cache._cache", _FAKE_ARTICLES):
            results = recommend("最近有什么新消息", memories=memories)
        self.assertTrue(len(results) > 0)

    def test_no_match_returns_empty(self):
        with patch("assistant.article_cache._cache", _FAKE_ARTICLES):
            results = recommend("量子计算外星技术")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
