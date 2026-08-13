import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE = 'http://127.0.0.1:8000'

type Taxonomy = {
  primarySectors: { id: string; name: string; industries: string[]; topics?: string[] }[]
  industries: string[]
  themes: string[]
}

type NewsItem = {
  id: number
  title: string
  summary: string
  url: string
  source_name: string
  published_at: string | null
  fetched_at: string
  primary_sector: string
  industry: string
  topics: string[]
}

type SourceHealth = {
  source_id: string
  source_name: string
  status: string
  item_count: number
  detail: string
  last_checked_at: string | null
}

function formatDate(value: string | null) {
  if (!value) return '时间待确认'
  return value.length > 24 ? value.slice(0, 16).replace('T', ' ') : value
}

function App() {
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null)
  const [news, setNews] = useState<NewsItem[]>([])
  const [sources, setSources] = useState<SourceHealth[]>([])
  const [activeSector, setActiveSector] = useState('全部行业')
  const [activeIndustry, setActiveIndustry] = useState('')
  const [activeTopic, setActiveTopic] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)

  const industries = useMemo(() => {
    if (!taxonomy) return []
    if (activeSector === '全部行业') return taxonomy.industries
    return taxonomy.primarySectors.find((sector) => sector.name === activeSector)?.industries ?? []
  }, [activeSector, taxonomy])

  const loadNews = async (shouldRefresh = false) => {
    setError('')
    if (shouldRefresh) setRefreshing(true)
    try {
      if (shouldRefresh) await fetch(`${API_BASE}/refresh`, { method: 'POST' })
      const query = new URLSearchParams()
      if (activeSector !== '全部行业') query.set('primary_sector', activeSector)
      if (activeIndustry) query.set('industry', activeIndustry)
      if (activeTopic) query.set('topic', activeTopic)
      const [newsResponse, sourceResponse] = await Promise.all([
        fetch(`${API_BASE}/news?${query.toString()}`),
        fetch(`${API_BASE}/sources`),
      ])
      if (!newsResponse.ok || !sourceResponse.ok) throw new Error('新闻服务返回异常')
      const newsData = await newsResponse.json()
      setNews(newsData.items)
      setUpdatedAt(newsData.updatedAt)
      setSources(await sourceResponse.json())
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '无法连接新闻服务')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    const initialize = async () => {
      try {
        const taxonomyResponse = await fetch(`${API_BASE}/taxonomy`)
        if (!taxonomyResponse.ok) throw new Error('分类服务不可用')
        setTaxonomy(await taxonomyResponse.json())
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : '无法连接后端')
      }
    }
    void initialize()
  }, [])

  useEffect(() => {
    if (taxonomy) void loadNews()
  }, [taxonomy, activeSector, activeIndustry, activeTopic])

  const backendOnline = Boolean(taxonomy)
  const failedSources = sources.filter((source) => source.status === 'error')

  return (
    <main className="news-app">
      <aside className="news-sidebar" aria-label="资讯导航">
        <div className="brand-block"><div className="brand-mark">▲</div><div><strong>投资资讯</strong><span>Investment News</span></div></div>
        <div className="nav-heading">视图</div>
        <button className="view-item view-item-active" type="button">● 资讯看板</button>
        <button className="view-item" type="button" disabled>● 行情工作台</button>
        <div className="nav-heading">一级板块</div>
        <div className="sector-list">
          <button className={`sector-item ${activeSector === '全部行业' ? 'sector-item-active' : ''}`} type="button" onClick={() => { setActiveSector('全部行业'); setActiveIndustry('') }}><span>全部行业</span><small>{news.length}</small></button>
          {taxonomy?.primarySectors.map((sector) => <button className={`sector-item ${activeSector === sector.name ? 'sector-item-active' : ''}`} key={sector.id} type="button" onClick={() => { setActiveSector(sector.name); setActiveIndustry('') }}><span>{sector.name}</span><small>{sector.industries.length}</small></button>)}
        </div>
        <div className="nav-heading">申万一级行业（31）</div>
        <div className="industry-list">
          {taxonomy?.industries.map((industry) => <button className={`industry-item ${activeIndustry === industry ? 'industry-item-active' : ''}`} key={industry} type="button" onClick={() => { setActiveSector('全部行业'); setActiveIndustry(industry) }}>{industry}</button>)}
        </div>
      </aside>

      <section className="news-main">
        <header className="news-header">
          <div><p className="section-kicker">INVESTMENT NEWS</p><h1>{activeSector}</h1><p className="header-meta">{news.length} 条已存资讯 · <span>{updatedAt ? `更新于 ${formatDate(updatedAt)}` : '等待首次抓取'}</span></p></div>
          <div className="header-actions"><button type="button" aria-label="刷新资讯" onClick={() => void loadNews(true)} disabled={refreshing}>{refreshing ? '…' : '↻'}</button><button className="ai-button" type="button" disabled>AI</button></div>
        </header>

        <div className={`backend-status ${backendOnline ? 'backend-status-online' : 'backend-status-offline'}`} role="status"><span className="backend-status-dot" aria-hidden="true" /><div><strong>{backendOnline ? '后端已连接' : '后端未连接'}</strong><p>{error || '新闻分类、存储和来源服务已就绪'}</p></div></div>

        <div className="filter-bar" aria-label="资讯筛选">
          <label>行业<select value={activeIndustry} onChange={(event) => setActiveIndustry(event.target.value)}><option value="">全部行业</option>{industries.map((industry) => <option key={industry} value={industry}>{industry}</option>)}</select></label>
          <div className="topic-filters"><span>主题</span>{taxonomy?.themes.slice(0, 8).map((topic) => <button className={activeTopic === topic ? 'topic-active' : ''} key={topic} type="button" onClick={() => setActiveTopic(activeTopic === topic ? '' : topic)}>{topic}</button>)}</div>
        </div>

        <div className="news-content">
          {failedSources.length > 0 && <div className="source-warning" role="alert">{failedSources.length} 个来源暂时不可用：{failedSources.map((source) => source.source_name).join('、')}。其他来源仍可继续刷新。</div>}
          {loading && <div className="empty-state">正在读取本地资讯库…</div>}
          {!loading && news.length === 0 && <div className="empty-state"><strong>暂无匹配资讯</strong><span>点击右上角刷新按钮抓取已配置来源，或调整筛选条件。</span></div>}
          <div className="news-list">{news.map((item) => <article className="news-card" key={item.id}><div className="news-bullet" /><div className="news-card-body"><h2><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></h2>{item.summary && <p>{item.summary}</p>}<div className="news-tags"><span className="tag">{item.primary_sector}</span>{item.industry && <span className="tag">{item.industry}</span>}{item.topics.map((topic) => <span className="tag" key={topic}>{topic}</span>)}</div></div><div className="news-card-meta"><strong>{item.source_name}</strong><time>{formatDate(item.published_at)}</time></div></article>)}</div>
          {sources.length > 0 && <section className="source-panel"><h2>来源健康</h2>{sources.map((source) => <div className="source-row" key={source.source_id}><span className={`source-dot source-${source.status}`} /> <strong>{source.source_name}</strong><span>{source.status === 'ok' ? `${source.item_count} 条` : source.detail || '不可用'}</span></div>)}</section>}
        </div>
      </section>
    </main>
  )
}

export default App
