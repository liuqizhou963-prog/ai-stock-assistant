import "./InvestmentNewsFrame.css";

export default function InvestmentNewsFrame() {
  return (
    <main className="investment-news-frame" aria-label="资讯看板">
      <iframe
        className="investment-news-frame__content"
        title="投资资讯"
        src="http://127.0.0.1:8888/index.html"
      />
    </main>
  );
}
