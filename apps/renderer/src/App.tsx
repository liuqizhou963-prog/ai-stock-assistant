import { useState } from 'react'
import './App.css'

const sectors = ['全部行业', '农林牧渔', '基础化工', '钢铁', '有色金属', '电子', '家用电器', '食品饮料', '纺织服饰', '轻工制造', '医药生物']

function App() {
  const [activeSector, setActiveSector] = useState('全部行业')

  return (
    <main className="news-app">
      <aside className="news-sidebar" aria-label="资讯导航">
        <div className="brand-block">
          <div className="brand-mark">▲</div>
          <div><strong>投资资讯</strong><span>Investment News</span></div>
        </div>
        <div className="nav-heading">视图</div>
        <button className="view-item view-item-active" type="button">● 资讯看板</button>
        <button className="view-item" type="button">● 行情工作台</button>
        <div className="nav-heading">行业 / SW 一级</div>
        <nav className="sector-list" aria-label="行业筛选">
          {sectors.map((sector, index) => (
            <button
              className={`sector-item ${activeSector === sector ? 'sector-item-active' : ''}`}
              key={sector}
              type="button"
              onClick={() => setActiveSector(sector)}
            >
              <span><i className={`sector-dot sector-dot-${index % 5}`} />{sector}</span>
              <small>{sector === '全部行业' ? 184 : index % 3 === 0 ? 32 : 16}</small>
            </button>
          ))}
        </nav>
      </aside>

      <section className="news-main">
        <header className="news-header">
          <div><p className="section-kicker">INVESTMENT NEWS</p><h1>{activeSector}</h1><p className="header-meta">覆盖 12 个主题赛道 · 本栏 184 条　<span>最近 7 天</span> · 更新 2026-08-11 05:24:32 · 本地抓取</p></div>
          <div className="header-actions"><button type="button" aria-label="刷新资讯">↻</button><button className="ai-button" type="button">AI</button></div>
        </header>

        <div className="news-content">
          <section className="highlights" aria-labelledby="highlights-title">
            <h2 id="highlights-title">✦ 行业今日要点</h2>
            <ul>
              <li>AI / 大模型: 扎克伯格发布个人 AI 宣言引发争议</li>
              <li>AI / 大模型: Claude 代理入侵健身房系统引热议</li>
              <li>半导体 / 芯片: 英伟达推进 Agentic AI 工具包</li>
              <li>半导体 / 芯片: 欧洲扩大 IRIS² 卫星星座部署</li>
            </ul>
          </section>

          <article className="news-card">
            <div className="news-bullet" />
            <div className="news-card-body"><h2>空间转录组学揭示心脏移植排斥性质</h2><p>Spatial Transcriptomics Uncovers Heterogeneity in Heart Transplant Rejection</p><span className="tag">生物医药 / 健康</span></div>
            <div className="news-card-meta"><span>GEN</span><time>2天前<br />08-11 05:24</time></div>
          </article>
        </div>
      </section>
    </main>
  )
}

export default App
