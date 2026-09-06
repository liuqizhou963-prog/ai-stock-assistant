// 金融合规与请求分类策略
//
// 设计原则（v2，修复"合规后处理毁损文本"问题）：
// 1. 保护引号内容：模型引用用户原话（如 "明天会涨吗"）不参与替换。
// 2. 保护合规自述行：含"不构成/不提供/不建议/无法/风险提示"等自我保护表达的行，
//    说明模型本就在做合规声明，不应再被正则改写。
// 3. 保护评级/统计行：机构评级、占比统计里的"买入 14%"是历史事实，不是操作指令。
// 4. 规则只匹配"露骨违规句式"（指令前缀+动作词、确定性断言），
//    不再对"买入/卖出/涨/跌"等裸词做全局替换。

const OUT_OF_SCOPE = /(?:贪吃蛇|写游戏|写小说|修电脑|天气预报|旅游攻略|做菜|解数学题|政治竞选)/i;

// 行级保护关键词：该行是合规自述 / 免责声明 / 历史陈述时整体跳过改写
const SAFE_LINE = /不构成|不提供|不推荐|不建议|不预测|不承诺|不做|不作|不适合|不适宜|禁止|拒绝|无法|难以|不能|不宜|不应|不可|不应当|不要|仅供|仅供参考|不承担|免责|风险提示|合规|谨慎|谨防|危险|警惕|不负责|不保证|非投资建议|不代表|自行决定|独立判断|独立评估|注意风险|投资有风险|入市需谨慎|自行承担|历史|回测|过去|历年|近\d年|近\d个月|中长期|数据显示|统计|整体而言/;

// 评级/资金/占比类统计行：行内含百分比且含统计特征词，或为表格行
const RATING_STAT_LINE = /(?:评级|机构|强力推荐|中性|增持|减持|占比|统计|券商|推荐[：:]|主流|榜单|持股比例)/;
const TABLE_LINE = /^\s*\|/;

// 露骨违规词规则（仅在非保护行上执行）
const RULES = [
  // 目标价（带具体数字）
  { re: /目标价(?:格|位)?\s*[:：]?\s*\d+(?:\.\d+)?\s*元?/g, to: "具体价位请自行研究评估" },
  // 确定性涨跌断言（字面强断言）
  { re: /(?:必涨|必跌|肯定涨|肯定跌|一定涨|一定跌|稳涨|稳跌|保证涨|保证跌|铁定(?:涨|跌)|百分之百会(?:涨|跌))/g, to: "涨跌结果无法确定" },
  // 时间指向的极端涨跌断言（仅极端词，排除后接数字的行情陈述，如"今日大涨2.4%"）
  { re: /(?:明天|明日|下周|下个交易日|未来几天|未来数日|未来\d+\s*天|下月)(?:必|肯定|一定|绝对)?(?:会|将)?(?:涨停|大涨|跌停|大跌|暴跌|翻倍|腰斩)(?![\d.%元万])/g, to: "涨跌结果无法确定" },
  // "预测+方向"句式（避免命中"预测营收增长"这类中性表述）
  { re: /预测(?:其|该|此|未来|后市|短期|中期|明日|下周|股价)?(?:将|会)?(?:大幅|继续|持续)?(?:反弹|回调|上攻|下探|大涨|大跌|涨停|跌停|创新高|创新低)/g, to: "方向性预判无法确定" },
  // 露骨买卖指令：仅匹配"指令前缀+动作"或"动作+祈使尾"或"时间副词+动作"，
  // 从而放行"净买入 5 亿 / 机构买入 / 买入 14%"这类陈述性语境。
  { re: /(?:强烈建议|建议|推荐|请|务必|可以考虑|可以|应当|应该|是时候|值得|适合)(?:[^，。！？；\n]{0,4}?)(?:逢低)?(?:买入|卖出|加仓|减仓|重仓|清仓|做多|做空|抄底|追高|建仓|补仓|满仓)/g, to: "是否操作需自行评估决策" },
  { re: /(?:立即|马上|赶紧|赶快|立刻|果断|大胆|趁|逢低)(?:[^，。！？；\n]{0,4}?)(?:买入|卖出|加仓|减仓|重仓|清仓|做多|做空|抄底|追高|建仓|补仓|满仓)/g, to: "是否操作需自行评估决策" },
  { re: /(?:买入|卖出|加仓|减仓|重仓|清仓|做多|做空|抄底|追高|建仓|补仓|满仓|止盈|止损)(?:了|吧|为好|为宜|才是明智)/g, to: "是否操作需自行评估决策" },
  // 收益承诺类
  { re: /(?:稳赚不赔|稳赚|稳赢|包赚|无风险收益|零风险|保本保息|保证收益|承诺收益|保底收益)/g, to: "收益与风险无法保证" },
  { re: /(?:保证|承诺)(?:年化)?(?:收益率|年化收益|收益|回报)(?:率)?(?:达到|超过|不低于)?\s*\d+(?:\.\d+)?%?/g, to: "收益与风险无法保证" },
  // 适合性表述
  { re: /(?:适合|适宜|适配)(?:你|您|散户|新手|保守型|激进型|长期投资者)?投资|(?:你|您)(?:应该|应当)投资/g, to: "需结合个人情况独立评估" },
  // 仓位/资金配置指令（排除"持有"这类状态动词，避免毁损持仓陈述）
  { re: /(?:建议|推荐|应当|可以|请)?(?:配置|投入|控制在|保持|用)\s*\d+(?:\.\d+)?%?\s*(?:仓位|持仓|资金比例|资金|比例)/g, to: "资金配置请自行决定" },
];

const FRESHNESS = /最新|实时|今天|当前|现在|刚刚|盘中|收盘|本周|近期|最近|今日/i;
const WEB_SIGNALS = /新闻|公告|资讯|消息|政策|研报|联网|搜索|来源|验证|事件|回购|减持|增持/i;
// 明确数据请求：指向特定数据/指标，未要求综合判断 → 应走"自主工具"路径而非强制多视角研究
const DATA_REQUEST = /多少钱|现价|报价|最新价|涨跌幅|换手|市盈率|市净率|PE|PB|ROE|MACD|KDJ|RSI|均线|K线|K线图|布林|金叉|死叉|分时|盘口|财报|营收|净利润|分红|股息|解禁|股东|公告|研报|评级|资金流|北向|龙虎榜|涨停池|开盘|收盘|盘中|行情|走势|估值|大盘|指数/;
const DEEP_RESEARCH = /分析|深度分析|投资价值|前景|逻辑|评价|点评|解读|综合|对比|比较|推荐|怎么看|如何操作|是否值得/;

export function researchRequirements(input) {
  const text = String(input ?? "");
  const codes = [...text.matchAll(/(?<!\d)\d{6}(?!\d)/g)].map((match) => match[0]).slice(0, 10);
  return {
    needsMarketQuote: codes.length > 0 && FRESHNESS.test(text),
    needsWebSearch: WEB_SIGNALS.test(text) || (FRESHNESS.test(text) && codes.length === 0),
    needsKline: codes.length > 0 && /MACD|KDJ|RSI|均线|MA5|MA10|MA20|MA60|K线|K线图|布林|金叉|死叉|技术面|技术分析|支撑|压力|量价|形态|趋势线|蜡烛图/.test(text),
    needsFinancials: codes.length > 0 && /财报|财务|业绩|营收|收入|净利润|利润|毛利率|净利率|ROE|资产负债|现金流|每股收益|EPS|分红|股息|基本面|成长性|盈利质量/.test(text),
    codes,
  };
}

// 意图分类：data=明确数据/指标查询（给自主工具） | research=综合研究（给多视角证据合成） | chat=普通对话
export function classifyIntent(input) {
  const text = String(input ?? "").trim();
  const dataHits = (text.match(DATA_REQUEST) || []).length;
  const deepHits = (text.match(DEEP_RESEARCH) || []).length;
  const hasCode = /(?<!\d)\d{6}(?!\d)/.test(text);
  if (dataHits > 0 && deepHits === 0 && (hasCode || /最新|今天|现在|近期/.test(text))) return "data";
  if (dataHits > 0 && deepHits === 0 && /行情|走势|公告|新闻|研报|涨停|资金/.test(text)) return "data";
  if (hasCode && text.length <= 80) return "research";
  return "chat";
}

export function classifyRequest(input) {
  const text = String(input ?? "").trim();
  if (!text) return { allowed: false, message: "请输入与股票、金融数据或投研相关的问题。" };
  if (OUT_OF_SCOPE.test(text)) {
    return { allowed: false, message: "我只处理股票、金融数据和投研问题，请换成相关问题。" };
  }
  return { allowed: true };
}

function protectQuotes(text) {
  const placeholders = [];
  const protectedText = text.replace(/"[^"\n]*"|“[^”\n]*”|「[^」\n]*」|‘[^’\n]*’|'[^'\n]*'/g, (match) => {
    placeholders.push(match);
    return `\u0000Q${placeholders.length - 1}\u0000`;
  });
  return {
    protectedText,
    restore(textWithPlaceholders) {
      return textWithPlaceholders.replace(/\u0000Q(\d+)\u0000/g, (_match, index) => placeholders[Number(index)] ?? "");
    },
  };
}

function isProtectedLine(line) {
  const trimmed = line.trim();
  if (!trimmed) return true; // 空行不动
  if (SAFE_LINE.test(trimmed)) return true;
  // 评级/资金/占比统计行：含百分比且含统计特征词；或表格行含百分比
  if (/%/.test(trimmed)) {
    if (RATING_STAT_LINE.test(trimmed)) return true;
    if (TABLE_LINE.test(trimmed)) return true;
  }
  return false;
}

export function enforceFinancialSafety(input) {
  let result = String(input ?? "");
  const quotes = protectQuotes(result);
  const lines = quotes.protectedText.split("\n").map((line) => {
    if (isProtectedLine(line)) return line;
    let cleaned = line;
    for (const rule of RULES) {
      cleaned = cleaned.replace(rule.re, rule.to);
    }
    return cleaned;
  });
  result = quotes.restore(lines.join("\n"));
  if (!/风险提示/.test(result)) {
    result += "\n\n风险提示：以上内容仅用于公开信息整理与研究，不构成投资建议；市场有风险，数据可能存在延迟或误差。";
  }
  return result.trim();
}
