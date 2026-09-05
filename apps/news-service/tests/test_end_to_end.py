import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DashboardLayoutContractTests(unittest.TestCase):
    """The assistant is a collapsible drawer; market tools live in the main area."""

    def setUp(self):
        self.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_assistant_is_collapsed_until_opened(self):
        self.assertIn('.assistant{position:relative', self.html)
        self.assertIn('.app.assistant-open .assistant{display:flex;}', self.html)
        self.assertIn('id="assistantToggle"', self.html)
        self.assertIn('aria-expanded="false"', self.html)

    def test_assistant_width_is_resizable_and_persisted(self):
        self.assertIn('id="assistantResizer"', self.html)
        self.assertIn("localStorage.setItem('assistantWidth'", self.html)
        self.assertIn('--assistant-w', self.html)

    def test_market_tools_live_in_the_main_workbench_view(self):
        workbench = self.html.index('id="workbench"')
        assistant = self.html.index('<aside class="assistant"')
        self.assertLess(workbench, assistant, "行情工作台应在主区，不在助手内部")
        self.assertIn('id="viewWorkbench"', self.html)
        self.assertNotIn('id="researchBtn"', self.html)

    def test_text2sql_panel_stays_inside_existing_workbench(self):
        workbench = self.html.index('id="workbench"')
        data_query = self.html.index('id="dataQueryPanel"')
        assistant = self.html.index('<aside class="assistant"')
        self.assertLess(workbench, data_query)
        self.assertLess(data_query, assistant)
        self.assertIn("/api/research/query", self.html)
        self.assertIn('data-data-query="资讯总量是多少"', self.html)
        self.assertIn('data-data-query="统计最近7天每天的资讯数量"', self.html)

    def test_workbench_exposes_common_market_indicators(self):
        self.assertIn('data-indicator="volume"', self.html)
        self.assertIn('data-indicator="rsi"', self.html)
        self.assertIn('data-indicator="volumeRatio"', self.html)
        self.assertIn('data-indicator="kdj"', self.html)
        self.assertIn('id="quoteVolumeRatio"', self.html)

    def test_alerts_notify_globally_instead_of_the_chat_stream(self):
        self.assertIn("showToast('价格提醒'", self.html)
        self.assertIn('id="toastStack"', self.html)
        self.assertIn('id="alertBadge"', self.html)

    def test_board_items_can_be_handed_to_the_assistant(self):
        self.assertIn('data-ask="item"', self.html)
        self.assertIn('data-ask="point"', self.html)
        self.assertIn('id="assistantFocus"', self.html)
        self.assertIn('focus:sentFocus', self.html)


class EndToEndContractTests(unittest.TestCase):
    def test_page_submits_post_refresh_request(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn('fetch("/api/refresh"', html)
        self.assertIn('method: "POST"', html)
        self.assertIn('X-Refresh-Request', html)
        self.assertIn('id="refreshBtn"', html)

    def test_page_has_running_and_failure_states(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertIn('state === "submitting"', html)
        self.assertIn('state === "running"', html)
        self.assertIn('state === "failed"', html)
        self.assertIn('window.location.reload()', html)
        self.assertIn('aria-live="polite"', html)


if __name__ == "__main__":
    unittest.main()
