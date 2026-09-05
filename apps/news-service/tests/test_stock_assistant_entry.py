from pathlib import Path


INDEX_HTML = Path(__file__).resolve().parents[1] / "index.html"


def test_news_page_routes_to_current_stock_assistant():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="viewStockAssistant"' in html
    assert '<span class="nm">股票助手</span>' in html
    assert 'id="viewWorkbench"' not in html
    assert '<span class="nm">行情工作台</span>' not in html
    assert "window.top.location.href" in html
    assert "document.getElementById('assistantToggle').onclick = openStockAssistant" in html
    assert 'id="assistant"' not in html
    assert "toggleAssistant" not in html
