import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DashboardLayoutContractTests(unittest.TestCase):
    """The news view keeps its own dashboard and routes users to the stock assistant."""

    def setUp(self):
        self.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_stock_assistant_is_a_current_tab_entry(self):
        self.assertIn('id="assistantToggle"', self.html)
        self.assertIn('id="viewStockAssistant"', self.html)
        self.assertIn('window.top.location.href', self.html)
        self.assertIn("document.getElementById('assistantToggle').onclick = openStockAssistant", self.html)
        self.assertNotIn('id="assistant"', self.html)
        self.assertNotIn('id="viewWorkbench"', self.html)

    def test_news_dashboard_keeps_its_refresh_and_global_notice_ui(self):
        self.assertIn('id="toastStack"', self.html)
        self.assertIn("showToast('价格提醒'", self.html)
        self.assertIn('id="refreshBtn"', self.html)
        self.assertIn('id="refreshStatus"', self.html)


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
