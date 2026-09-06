from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_desktop_package_includes_and_starts_news_service_runtime():
    main = (ROOT / "apps" / "desktop" / "src" / "main.cjs").read_text(encoding="utf-8")
    package = (ROOT / "apps" / "desktop" / "package.json").read_text(encoding="utf-8")

    assert "news-service" in package
    assert "news-service/.venv" in package
    assert "startNewsService" in main
    assert "waitForNewsService" in main
    assert "newsPort" in main
    assert "news-service-runtime" in main
    assert "newsPython" in main


def test_news_frame_reads_the_desktop_news_port():
    frame = (ROOT / "apps" / "renderer" / "src" / "InvestmentNewsFrame.tsx").read_text(encoding="utf-8")

    assert 'get("newsPort")' in frame
    assert "127.0.0.1:${newsPort}" in frame
