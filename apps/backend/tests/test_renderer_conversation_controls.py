import unittest
from pathlib import Path


RENDERER = Path(__file__).resolve().parents[2] / "renderer" / "src" / "App.tsx"


class RendererConversationControlsTests(unittest.TestCase):
    def setUp(self):
        self.source = RENDERER.read_text(encoding="utf-8")

    def test_sidebar_does_not_render_obsolete_pinned_prompt(self):
        self.assertNotIn('className="pinned-conversation"', self.source)
        self.assertNotIn("本周市场观察", self.source)

    def test_conversation_items_expose_delete_action(self):
        self.assertIn("deleteConversation", self.source)
        self.assertIn('title="删除会话"', self.source)

    def test_tool_trace_is_not_rendered_in_conversation(self):
        self.assertNotIn('className="tool-trace"', self.source)


if __name__ == "__main__":
    unittest.main()
