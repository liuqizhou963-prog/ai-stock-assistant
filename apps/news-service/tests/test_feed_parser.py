import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from feed_parser import parse_feed


RSS_SAMPLE = """
<rss version="2.0">
  <channel>
    <item>
      <title>RSS 测试新闻</title>
      <link>https://example.com/rss-news</link>
      <pubDate>Mon, 27 Jul 2026 10:00:00 GMT</pubDate>
      <description>摘要 <strong>加粗内容</strong></description>
    </item>
  </channel>
</rss>
""".encode("utf-8")


ATOM_SAMPLE = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom 测试新闻</title>
    <link href="https://example.com/atom-news" />
    <updated>2026-07-27T10:00:00Z</updated>
    <summary>Atom 摘要内容</summary>
  </entry>
</feed>
""".encode("utf-8")


class FeedParserTests(unittest.TestCase):
    def test_parse_rss_item(self):
        items = parse_feed(RSS_SAMPLE, "RSS 测试源")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "RSS 测试新闻")
        self.assertEqual(items[0]["url"], "https://example.com/rss-news")
        self.assertEqual(items[0]["source"], "RSS 测试源")
        self.assertEqual(items[0]["time"], "07-27 18:00")
        self.assertGreater(items[0]["ts"], 0)
        self.assertEqual(items[0]["summary"], "摘要 加粗内容")

    def test_parse_atom_with_namespace(self):
        items = parse_feed(ATOM_SAMPLE, "Atom 测试源")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Atom 测试新闻")
        self.assertEqual(items[0]["url"], "https://example.com/atom-news")
        self.assertEqual(items[0]["time"], "07-27 18:00")

    def test_offsetless_time_is_interpreted_as_beijing_time(self):
        xml = """
        <rss><channel><item>
          <title>无时区时间</title>
          <pubDate>2026-07-27T10:00:00</pubDate>
        </item></channel></rss>
        """.encode("utf-8")

        items = parse_feed(xml, "测试源")

        self.assertEqual(items[0]["time"], "07-27 10:00")

    def test_missing_title_is_ignored(self):
        xml = """
        <rss><channel><item>
          <link>https://example.com/no-title</link>
        </item></channel></rss>
        """.encode("utf-8")

        self.assertEqual(parse_feed(xml, "测试源"), [])

    def test_missing_time_uses_empty_time_marker(self):
        xml = """
        <rss><channel><item>
          <title>没有时间的新闻</title>
          <link>https://example.com/no-time</link>
        </item></channel></rss>
        """.encode("utf-8")

        items = parse_feed(xml, "测试源")

        self.assertEqual(items[0]["time"], "—")
        self.assertEqual(items[0]["ts"], 0)

    def test_missing_link_keeps_news_item(self):
        xml = """
        <rss><channel><item>
          <title>没有链接的新闻</title>
        </item></channel></rss>
        """.encode("utf-8")

        items = parse_feed(xml, "测试源")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "")

    def test_invalid_xml_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "XML 格式错误"):
            parse_feed(b"<rss><item>", "错误源")


if __name__ == "__main__":
    unittest.main()
