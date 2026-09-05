"""
意图识别（两路融合）
路1：关键词 pattern 匹配（同步，零延迟，做快速兜底）
路2：LLM 语义分类（主判断，输出四类意图之一）

意图类别：
  news_query    需要检索最新资讯
  knowledge_qa  股票金融知识问答，无需检索
  memory_op     用户要保存/查看记忆、收藏
  reject        预测涨跌 / 买卖建议 / 与炒股无关
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.llm import call as _llm_call, load_config, LLMError  # noqa: E402

INTENT_NEWS_QUERY   = "news_query"
INTENT_KNOWLEDGE_QA = "knowledge_qa"
INTENT_MEMORY_OP    = "memory_op"
INTENT_REJECT       = "reject"

_ALL_INTENTS = {INTENT_NEWS_QUERY, INTENT_KNOWLEDGE_QA, INTENT_MEMORY_OP, INTENT_REJECT}

# ---------- 关键词 pattern ----------
_REJECT_PATTERNS = [
    # 当前事实行情可以回答；只拦截未来涨跌预测。
    r"明[天后].*[涨跌]",
    r"[涨跌].*预测",
    r"目标价",
    r"(应该|能不能|可以).*(买|卖|入|出|抄底|逃顶)",
    r"(今天|明天|下周|近期).*(操作|建议|怎么做)",
    r"推荐.*股票",
    r"哪只.*买",
    r"天气",
    r"(做饭|烹饪|菜谱|食谱)",
    r"(游戏|娱乐|明星|电影|综艺)",
    r"(编程|代码|程序|开发)",
]

_MEMORY_PATTERNS = [
    r"记住",
    r"帮我记",
    r"收藏",
    r"以后.*关注",
    r"保存.*偏好",
    r"记录.*关注",
    r"我的记忆",
    r"查看.*记忆",
]

_NEWS_PATTERNS = [
    r"(最近|今天|今日|本周|近期|昨天).*(新闻|消息|动态|行情|资讯|报道)",
    r"有.*报道",
    r"发生.*什么",
    r"最新.*(情况|进展|消息)",
    r"(上涨|下跌|暴涨|暴跌).*原因",
    r"(利好|利空)",
    r"(政策|公告|业绩|财报).*出来",
]

_CURRENT_QUOTE_PATTERNS = [
    r"(今天|今日|当前|现在|实时).*(涨|跌|行情|报价|价格|股价|多少|黄金|白银|原油|美元|XAU|XAG|WTI|DXY)",
    r"(涨|跌).*(多少|幅度|百分比).*(今天|今日|当前|现在|实时)",
    r"(黄金|白银|原油|美元|XAU|XAG|WTI|DXY).*(今天|今日|当前|现在|实时|报价|价格)",
]

_ALLOWED_ANALYSIS_PATTERNS = [
    r"分析",
    r"基本面",
    r"技术面",
    r"行业趋势",
    r"投资价值",
    r"估值",
    r"财务",
    r"竞争力",
    r"风险",
    r"逻辑",
    r"前景",
    r"走势",
    r"原因",
    r"为什么",
    r"为何",
    r"MACD|KDJ|均线|布林|K线|PE|市盈率|PB|市净率|ROE|负债率|市值|财报",
]

# LLM 分类用的 system prompt（极简，只输出类别名）
_CLASSIFY_SYSTEM = """将用户输入分类为以下四类之一，只输出类别名，不要任何解释：

news_query    - 需要查最新新闻/资讯/当前行情或涨跌事实
knowledge_qa  - 股票、黄金、商品、外汇、宏观金融知识或概念问答，不需要查新闻
memory_op     - 保存偏好/收藏/查看或删除记忆
reject        - 预测未来涨跌、给买卖建议、或与金融市场完全无关的话题

查询“今天/当前涨了多少、跌了多少、现在价格是多少”属于 news_query，不属于 reject。"""


def _pattern_check(message: str):
    """快速 pattern 检查；返回确信的意图或 None。"""
    for p in _REJECT_PATTERNS:
        if re.search(p, message):
            return INTENT_REJECT
    for p in _MEMORY_PATTERNS:
        if re.search(p, message):
            return INTENT_MEMORY_OP
    return None


def recognize(message: str, root: str = None) -> str:
    """
    两路融合意图识别。
    返回值：INTENT_* 四个常量之一。
    """
    root = root or ROOT

    # 路1：pattern 快速检查（对明确拒绝和记忆操作直接短路）
    fast = _pattern_check(message)
    if fast in (INTENT_REJECT, INTENT_MEMORY_OP):
        if fast == INTENT_REJECT and any(
            re.search(pattern, message) for pattern in _CURRENT_QUOTE_PATTERNS
        ):
            return INTENT_NEWS_QUERY
        return fast

    # 明确的当前行情查询无需等待 LLM 分类，避免网络延迟或模型误判。
    if any(re.search(pattern, message) for pattern in _CURRENT_QUOTE_PATTERNS):
        return INTENT_NEWS_QUERY

    # 基本面、行业、技术面和风险分析是允许的研究请求；不要让 LLM
    # 把“分析一下”泛化成预测或买卖建议。
    if any(re.search(pattern, message) for pattern in _ALLOWED_ANALYSIS_PATTERNS):
        return INTENT_KNOWLEDGE_QA

    # 路2：LLM 语义分类（主判断）
    try:
        config = load_config(root)
        raw = _llm_call(_CLASSIFY_SYSTEM, message, config=config).strip().lower()
        # 取第一行，防止 LLM 多输出文字
        first_line = raw.splitlines()[0].strip()
        if first_line in _ALL_INTENTS:
            # 当前事实行情可以查询；只有未来预测才属于 reject。
            if first_line == INTENT_REJECT and any(
                re.search(pattern, message) for pattern in _CURRENT_QUOTE_PATTERNS
            ):
                return INTENT_NEWS_QUERY
            return first_line
    except (LLMError, Exception):
        pass

    # 路1 兜底：pattern 判断新闻意图，默认 knowledge_qa
    for p in _NEWS_PATTERNS:
        if re.search(p, message):
            return INTENT_NEWS_QUERY

    return INTENT_KNOWLEDGE_QA
