import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.llm import call as _llm_call, stream_call as _llm_stream_call, load_config, LLMError  # noqa: E402

SYSTEM_PROMPT = """你是一位经验丰富的股票投资助手，具备扎实的金融市场知识，能像专业金融从业者一样与用户深入交流。

【你能做的】
- 回答任何与股票、基金、债券、期货、黄金白银、原油、外汇、市场行情、宏观经济相关的问题
- 解读行业政策、监管动态、上市公司公告和新闻
- 讲解技术分析方法、基本面分析思路、市场情绪判断
- 解释金融术语、交易规则、市场机制
- 结合已有资讯提炼信息线索，说明出处和与用户关注点的关系
- 如果提供了【实时行情】或【财务快照】，只能准确转述其中已有字段，并注明数据来源、日期和缺失项
- 像一个有经验的炒股朋友一样，语气专业自然，可以深入聊

【你必须拒绝的——遇到以下请求，礼貌说明原因后停止】
1. 预测某只股票或大盘的涨跌、目标价位、操作时机
2. 给出具体的买入 / 卖出 / 加仓 / 减仓建议
3. 与金融市场完全无关的话题（天气、烹饪、娱乐、编程等）

基本面、技术面、行业趋势、估值、风险、投资价值和“为什么涨跌”的解释属于允许的分析，不要因为出现“投资”或“走势”就拒绝。分析应陈述依据、不确定性和多种可能，不给出确定的未来涨跌预测或交易指令。

【回答规范】
- 有候选资讯时：优先结合资讯回答，说明每条资讯和用户关注点的关系，保留原文链接
- 无候选资讯或资讯不相关时：直接用专业知识回答，不编造新闻或数据
- 有实时行情时：优先使用实时行情中的事实数据，并注明数据来源和更新时间；不要说自己无法获取实时行情
- 不要编造行情、财务数字、行业中位数或报告日期；后端证据中的数字优先级最高
- 不把相关性说成确定性因果
- 输出中文，语气自然专业"""

_MEMORY_TYPE_LABELS = {
    "preference":    "偏好",
    "watch_topic":   "关注主题",
    "saved_article": "收藏文章",
    "watchlist":    "自选跟踪",
    "conversation":  "对话摘要",
}


def _format_memories(memories: list) -> str:
    # _format_memories（把记忆列表格式化为提示词文本）
    if not memories:
        return "（暂无记忆）"
    lines = []
    for m in memories:
        label = _MEMORY_TYPE_LABELS.get(m.get("memory_type", ""), "记忆")
        lines.append(f"[{label}] {m.get('title', '')}：{m.get('content', '')}")
    return "\n".join(lines)


def _format_articles(articles: list) -> str:
    # _format_articles（把候选文章列表格式化为提示词文本）
    lines = []
    for i, a in enumerate(articles):
        title   = a.get("title", "") or a.get("zh", "")
        source  = a.get("source", "")
        industry = a.get("industry_name", "")
        summary = (a.get("summary", "") or "")[:80]
        url     = a.get("url", "")
        lines.append(f"{i}. {title} / {source} / {industry} / {summary} / {url}")
    return "\n".join(lines) or "（无候选文章）"


def _format_session_history(session_history: list) -> str:
    # _format_session_history（把会话历史列表格式化为提示词文本，由旧到新）
    if not session_history:
        return ""
    lines = []
    for msg in session_history:
        role = (
            "上下文摘要" if msg.get("role") == "system"
            else ("用户" if msg.get("role") == "user" else "助手")
        )
        content = str(msg.get("content", "")).strip()
        if content:
            lines.append(f"{role}：{content}")
    if not lines:
        return ""
    return "【会话历史】\n" + "\n".join(lines) + "\n\n"


def _format_market_quotes(market_quotes: list) -> str:
    if not market_quotes:
        return ""
    lines = ["【实时行情（来自新浪财经）】"]
    for quote in market_quotes:
        sign = "+" if quote.get("change", 0) >= 0 else ""
        lines.append(
            f"{quote.get('name', '')}（{quote.get('symbol', '')}）："
            f"现价 {quote.get('price')}，"
            f"涨跌 {sign}{quote.get('change')}，"
            f"涨跌幅 {sign}{quote.get('change_pct')}%，"
            f"开盘 {quote.get('open')}，最高 {quote.get('high')}，最低 {quote.get('low')}，"
            f"成交量 {quote.get('volume')}，成交额 {quote.get('amount')}；"
            f"更新时间 {quote.get('trade_date', quote.get('date', ''))} "
            f"{quote.get('quote_time', quote.get('time', ''))}，"
            f"数据状态 {quote.get('freshness', 'unknown')}"
        )
    return "\n".join(lines)


def _format_research_context(context: dict | None) -> str:
    if not context:
        return ""
    if context.get("fundamentals"):
        data = context["fundamentals"]
        labels = [
            ("PE", data.get("pe")),
            ("PB", data.get("pb")),
            ("市值", data.get("market_cap")),
            ("流通市值", data.get("float_market_cap")),
            ("涨跌幅", data.get("change_pct")),
            ("营收", data.get("revenue")),
            ("营收同比", data.get("revenue_growth")),
            ("净利润", data.get("net_profit")),
            ("净利润同比", data.get("profit_growth")),
            ("毛利率", data.get("gross_margin")),
            ("净利率", data.get("net_margin")),
            ("ROE", data.get("roe")),
            ("经营现金流", data.get("operating_cash_flow")),
            ("负债率", data.get("debt_ratio")),
        ]
        values = "，".join(f"{name}={value}" for name, value in labels if value is not None)
        return f"【公司财务快照（{data.get('name', '')} {data.get('symbol', '')}）】\n{values}\n行业：{data.get('industry', '')}；报告期：{data.get('report_date', '未知')}；数据源：{data.get('source', '')}；抓取时间：{data.get('fetched_at', '')}"
    if context.get("error"):
        return "【技术指标】\n" + str(context["error"])
    latest = context.get("latest", {})
    fields = [
        ("收盘", latest.get("close")),
        ("成交量", latest.get("volume")),
        ("量比", latest.get("volume_ratio")),
        ("MA5", latest.get("sma5")),
        ("MA10", latest.get("sma10")),
        ("MA20", latest.get("sma20")),
        ("MACD", latest.get("macd")),
        ("DIF", latest.get("dif")),
        ("DEA", latest.get("dea")),
        ("RSI14", latest.get("rsi14")),
        ("K", latest.get("k")),
        ("D", latest.get("d")),
        ("J", latest.get("j")),
    ]
    values = "，".join(f"{name}={value:.4f}" for name, value in fields if isinstance(value, (int, float)))
    return f"【技术指标（{context.get('symbol', '')}，{context.get('days', 0)}个交易日）】\n{values}"


def _format_research_data(data: dict | None) -> str:
    """Render verified Text2SQL output as immutable evidence for the LLM."""
    if not isinstance(data, dict):
        return ""
    if not data.get("ok"):
        return "【本地投研数据查询】\n查询未成功：" + str(data.get("answer") or "未知错误")
    columns = [str(item) for item in data.get("columns") or []]
    rows = data.get("rows") or []
    if not columns:
        return "【本地投研数据查询】\n查询成功，但没有可解释字段。"
    lines = [
        "【本地投研数据查询（已校验只读 SQL 结果）】",
        "数据源：本地投研快照；SQL：" + str(data.get("sql") or ""),
        "字段：" + "、".join(columns),
    ]
    for row in rows[:20]:
        if isinstance(row, dict):
            lines.append("；".join(f"{column}={row.get(column)}" for column in columns))
    if len(rows) > 20:
        lines.append(f"其余 {len(rows) - 20} 条记录未展开。")
    lines.append("只能依据以上结构化结果解释，不得补写未返回的统计或字段。")
    return "\n".join(lines)


FOCUS_KIND_LABELS = {
    "article": "用户正在追问的资讯",
    "digest_key_point": "用户正在追问的行业要点",
    "digest_point": "用户正在追问的行业要点",
}


def _format_focus(focus: dict | None) -> str:
    """Render the panel item the user clicked "问助手" on.

    The dashboard sends this so that pronouns like "这条" resolve to a concrete
    article or digest point instead of being guessed from industry_key alone.
    """
    if not isinstance(focus, dict):
        return ""
    title = str(focus.get("title") or "").strip()
    if not title:
        return ""
    label = FOCUS_KIND_LABELS.get(str(focus.get("kind") or ""), "用户正在追问的条目")
    lines = [f"标题：{title}"]
    for field, name in (
        ("raw_title", "原文标题"),
        ("source", "来源"),
        ("time", "发布时间"),
        ("industry_name", "所属行业"),
        ("subindustry_name", "主题赛道"),
        ("url", "链接"),
    ):
        value = str(focus.get(field) or "").strip()
        if value and value != title:
            lines.append(f"{name}：{value}")
    body = "\n".join(lines)
    return (
        f"【{label}】\n{body}\n"
        "用户问题中的“这条 / 它 / 这个要点”均指上面这一条，请围绕它作答。"
    )


def build_user_message(
    user_message: str,
    memories: list,
    articles: list,
    session_history: list = None,
    market_quotes: list = None,
    streaming: bool = False,
    research_context: dict = None,
    focus: dict = None,
    research_data: dict = None,
) -> str:
    # build_user_message（拼装发给 LLM 的完整用户消息）
    history_section = _format_session_history(session_history or [])
    memory_text = _format_memories(memories)
    market_text = _format_market_quotes(market_quotes or [])
    market_section = f"{market_text}\n\n" if market_text else ""
    research_text = _format_research_context(research_context)
    research_section = f"{research_text}\n\n" if research_text else ""
    data_text = _format_research_data(research_data)
    data_section = f"{data_text}\n\n" if data_text else ""
    focus_text = _format_focus(focus)
    focus_section = f"{focus_text}\n\n" if focus_text else ""

    if articles:
        articles_section = f"【候选资讯】\n{_format_articles(articles)}\n\n"
        articles_note = "如有相关资讯请引用并说明推荐理由（提到与用户记忆的关系）；无相关资讯则直接用专业知识回答。"
    else:
        articles_section = ""
        articles_note = "当前无候选资讯，请直接用专业知识回答。"

    output_instruction = (
        "请直接用中文回答，不要输出 JSON、Markdown 代码块或分析过程。"
        if streaming
        else (
            "请输出 JSON（严格格式，不要其他文字）：\n"
            '{\n'
            '  "answer": "回答内容（若拒绝回答也写在这里，说明原因）",\n'
            '  "articles": [\n'
            '    {"index": 0, "reason": "推荐理由（必须提到与用户记忆的关系）"}\n'
            '  ],\n'
            '  "memory_suggestions": [\n'
            '    {"type": "watch_topic", "title": "...", "content": "...", "tags": ["..."]}\n'
            '  ]\n'
            '}'
        )
    )

    return (
        f"{history_section}"
        f"【用户问题】\n{user_message}\n\n"
        f"{focus_section}"
        f"【用户记忆】\n{memory_text}\n\n"
        f"{market_section}"
        f"{research_section}"
        f"{data_section}"
        f"{articles_section}"
        f"{articles_note}\n\n"
        + output_instruction
    )


def parse_llm_json(text: str) -> dict:
    # parse_llm_json（三级兜底：直接解析 → 提取代码块 → 纯文字降级）
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return {"answer": text, "articles": [], "memory_suggestions": []}


def chat(
    user_message: str,
    memories: list,
    articles: list,
    session_history: list = None,
    root: str = None,
    market_quotes: list = None,
    research_context: dict = None,
    focus: dict = None,
    research_data: dict = None,
):
    """
    调用 LLM 生成推荐解释。
    返回 (ok: bool, answer: str, enriched_articles: list, memory_suggestions: list)
    ok=False 时 answer 说明失败原因，由调用方决定是否降级。
    session_history: 当前会话历史（由旧到新），注入到 prompt 中提供对话上下文。
    """
    root = root or ROOT
    try:
        config = load_config(root)
    except LLMError as e:
        return False, f"LLM 配置错误：{e}", [], []

    user_msg = build_user_message(
        user_message,
        memories,
        articles,
        session_history,
        market_quotes=market_quotes,
        research_context=research_context,
        focus=focus,
        research_data=research_data,
    )

    try:
        raw = _llm_call(SYSTEM_PROMPT, user_msg, config=config)
    except LLMError as e:
        return False, str(e), [], []

    parsed = parse_llm_json(raw)
    answer = parsed.get("answer", "")
    llm_arts = parsed.get("articles", [])
    suggestions = parsed.get("memory_suggestions", [])

    enriched = []
    for item in llm_arts:
        idx = item.get("index")
        if isinstance(idx, int) and 0 <= idx < len(articles):
            art = dict(articles[idx])
            art["reason"] = str(item.get("reason", ""))
            enriched.append(art)

    # LLM 没有返回有效索引时，退回候选文章列表（reason 留空）
    if not enriched and articles:
        enriched = [dict(a, reason="") for a in articles[:5]]

    return True, answer, enriched, suggestions


def stream_chat(
    user_message: str,
    memories: list,
    articles: list,
    session_history: list = None,
    root: str = None,
    market_quotes: list = None,
    research_context: dict = None,
    focus: dict = None,
    research_data: dict = None,
):
    """Yield plain answer text for the SSE chat endpoint."""
    root = root or ROOT
    try:
        config = load_config(root)
    except LLMError as error:
        raise error

    user_msg = build_user_message(
        user_message,
        memories,
        articles,
        session_history,
        market_quotes,
        streaming=True,
        research_context=research_context,
        focus=focus,
        research_data=research_data,
    )
    yield from _llm_stream_call(SYSTEM_PROMPT, user_msg, config=config)
