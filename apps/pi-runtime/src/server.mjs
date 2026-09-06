import readline from "node:readline";
import { Agent } from "@earendil-works/pi-agent-core";
import { Type } from "@earendil-works/pi-ai";
import { getModel, streamSimple } from "@earendil-works/pi-ai/compat";
import { classifyIntent, classifyRequest, enforceFinancialSafety, researchRequirements } from "./policy.mjs";
import { AnySearchMcpClient } from "./anysearch-mcp.mjs";
import { buildToolFallback } from "./response-fallback.mjs";

const MAX_TOOL_CALLS = 6;
const MAX_SEARCH_RESULTS = 8;
const STOCK_TOOL_ALLOWLIST = new Set([
  "get_market_quote", "get_kline", "get_order_book", "get_tick_transactions", "get_kline_with_ma",
  "get_stock_reports", "download_report_pdf", "get_industry_reports", "get_eps_forecast", "search_reports",
  "screen_stocks", "get_hot_reasons", "get_northbound_flow", "get_concept_blocks", "get_intraday_fund_flow",
  "get_dragon_tiger", "get_lockup_expiry", "get_industry_comparison", "get_board_fund_flow", "get_daily_dragon_tiger",
  "get_margin_trading", "get_block_trades", "get_holder_changes", "get_dividends", "get_fund_flow_history",
  "get_stock_news", "get_cls_telegraph", "get_global_news", "get_finance_snapshot", "get_f10", "get_stock_info",
  "get_financial_statements", "get_announcements", "get_latest_announcements", "get_limit_pool", "get_limit_up_reasons",
  "get_limit_up_sentiment", "get_stock_monitor", "get_price_anomalies", "get_price_anomaly_counts", "get_option_contracts",
  "get_option_quote", "get_option_greeks", "get_investor_questions", "get_hot_rank", "get_hot_concepts", "get_full_valuation",
  "calculate_valuation_metric", "get_dragon_tiger_backup", "get_fund_flow_backup", "get_announcements_backup",
]);

function modelFor(name) {
  const table = {
    deepseek: ["deepseek", process.env.DEEPSEEK_MODEL || "deepseek-v4-flash"],
    openai: ["openai", process.env.OPENAI_MODEL || "gpt-4o-mini"],
    claude: ["anthropic", process.env.ANTHROPIC_MODEL || "claude-haiku-4-5"],
  };
  const [provider, id] = table[name] || table.deepseek;
  const model = getModel(provider, id);
  if (!model) throw new Error(`Pi 未找到模型 ${provider}/${id}`);
  return model;
}

function textResult(value, details = {}) {
  return { content: [{ type: "text", text: JSON.stringify(value, ensureJson) }], details };
}

function ensureJson(_key, value) {
  if (typeof value === "bigint") return Number(value);
  return value;
}

function resultPreview(result) {
  const text = (result?.content || []).filter((part) => part.type === "text").map((part) => part.text).join(" ");
  return text.replace(/\s+/g, " ").slice(0, 600);
}

const EVIDENCE_LABELS = { quote: "实时行情", kline: "历史K线", financials: "财务数据", web: "网络检索" };

function appendEvidenceCitations(answer, evidence) {
  if (!evidence.length || /主要信息来源|数据来源|来源和时间/.test(answer)) return answer;
  const lines = evidence.map((item) => {
    const label = EVIDENCE_LABELS[item.kind] || item.kind;
    return `- ${label}：${item.source}，截至 ${item.updatedAt}${item.error ? `，获取失败：${item.error}` : ""}`;
  });
  return `${answer}\n\n主要信息来源：\n${lines.join("\n")}`;
}

async function callBackend(tool, arguments_) {
  if (!STOCK_TOOL_ALLOWLIST.has(tool)) throw new Error("股票数据工具不在白名单中");
  const port = process.env.DESKTOP_AGENT_BACKEND_PORT || "8000";
  const response = await fetch(`http://127.0.0.1:${port}/agent/workbench/query`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tool, arguments: arguments_ }),
    signal: AbortSignal.timeout(35_000),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `股票数据工具返回 HTTP ${response.status}`);
  return payload;
}

async function webSearch(query, limit = 5) {
  const client = new AnySearchMcpClient();
  const data = await client.call("search", { query, limit: Math.min(limit, MAX_SEARCH_RESULTS) });
  return { status: "success", source: "anysearch-mcp", data };
}

async function webBatchSearch(queries) {
  if (!Array.isArray(queries) || queries.length < 1 || queries.length > 5) throw new Error("batch_search 需要 1-5 个查询");
  const client = new AnySearchMcpClient();
  return { status: "success", source: "anysearch-mcp", data: await client.call("batch_search", { queries }) };
}

async function webSubDomains(domains) {
  if (!Array.isArray(domains) || domains.length < 1 || domains.length > 8) throw new Error("get_sub_domains 需要 1-8 个领域");
  const client = new AnySearchMcpClient();
  return { status: "success", source: "anysearch-mcp", data: await client.call("get_sub_domains", { domains }) };
}

async function webExtract(urls) {
  const values = Array.isArray(urls) ? urls : [urls];
  if (values.length < 1 || values.length > 5 || values.some((url) => !/^https?:\/\//i.test(String(url)))) throw new Error("extract 只允许 1-5 个 http/https URL");
  const client = new AnySearchMcpClient();
  return { status: "success", source: "anysearch-mcp", data: await client.call("extract", { urls: values }) };
}

async function webOpen(url) {
  const parsed = new URL(url);
  if (!/^https?:$/.test(parsed.protocol)) throw new Error("只允许读取 http/https 网页");
  const response = await fetch(parsed, { signal: AbortSignal.timeout(20_000), headers: { accept: "text/html,text/plain" } });
  if (!response.ok) throw new Error(`网页读取返回 HTTP ${response.status}`);
  const html = await response.text();
  const text = html.replace(/<script[\s\S]*?<\/script>/gi, "").replace(/<style[\s\S]*?<\/style>/gi, "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return { status: "success", url: parsed.toString(), content: text.slice(0, 20_000) };
}

function tools() {
  const stockDataGuide = `调用后端白名单股票数据工具。参数：tool=工具名（见下方速查），arguments=该工具参数对象。
后端可用工具速查（arguments 中股票代码传六位数字；日期统一 YYYY-MM-DD）：
- get_market_quote: 实时行情/估值/涨跌停价，arguments: {codes:["600519"]}
- get_kline_with_ma: 日K线含MA5/10/20，arguments: {code:"600519"}
- get_kline: 历史K线，arguments: {code, period:"day|week|month|60m|5m", limit:120}
- get_order_book: 五档盘口，arguments: {code}
- get_tick_transactions: 逐笔成交，arguments: {code, trade_date:"2026-09-05"}
- get_financial_statements: 三大报表，arguments: {code, report_type:"lrb|fzb|llb", periods:8}
- get_finance_snapshot: 财报快照，arguments: {code}
- get_full_valuation: 估值全景(市值/PE/PB/预测EPS/PEG)，arguments: {code}
- get_eps_forecast: 机构一致预期EPS，arguments: {code}
- get_stock_info: 行业/股本/市值/上市日期，arguments: {code}
- get_f10: 公司资料，arguments: {code, category:"公司概况|经营分析|财务分析|股东研究|重大事项|行业分析|最新提示"}
- get_concept_blocks: 所属概念板块，arguments: {code}
- get_announcements: 公司公告，arguments: {code, limit:20}
- get_stock_news: 个股新闻，arguments: {code, limit:20}
- get_stock_reports: 个股研报/评级，arguments: {code, max_pages:2}
- get_industry_reports: 行业研报，arguments: {industry_code:"*", max_pages:2}
- get_cls_telegraph: 财联社实时电报，arguments: {limit:20}
- get_global_news: 财经7x24快讯，arguments: {limit:20}
- get_limit_pool: 涨停/跌停池，arguments: {pool:"limit_up|open_limit|limit_down|yesterday_limit_up", trade_date}
- get_limit_up_reasons: 涨停原因题材，arguments: {trade_date}
- get_hot_reasons: 当日强势股与题材，arguments: {trade_date}
- get_intraday_fund_flow: 个股分钟资金流，arguments: {code}
- get_fund_flow_history: 个股120日资金流，arguments: {code}
- get_dragon_tiger: 个股龙虎榜，arguments: {code, trade_date, look_back:30}
- get_daily_dragon_tiger: 全市场龙虎榜，arguments: {trade_date}
- get_margin_trading: 融资融券，arguments: {code, limit:20}
- get_block_trades: 大宗交易，arguments: {code, limit:20}
- get_holder_changes: 股东户数变化，arguments: {code, limit:20}
- get_dividends: 分红送转历史，arguments: {code, limit:20}
- get_lockup_expiry: 限售解禁，arguments: {code, trade_date, forward_days:90}
- get_industry_comparison: 行业涨跌排名，arguments: {top_n:20}
- get_board_fund_flow: 板块资金流，arguments: {board_type:"industry|concept|region", period:"today|5d|10d", top_n:20}
- get_northbound_flow: 北向资金分钟流向，arguments: {}
- get_hot_rank: 人气榜，arguments: {provider:"ths|eastmoney", period:"hour|day", limit:20}
- get_stock_monitor: 交易所重点监控，arguments: {only_active:true}
- get_investor_questions: 互动易问答，arguments: {code, limit:10}
- get_price_anomalies: 异常波动明细，arguments: {limit:50}
- get_price_anomaly_counts: 异常波动统计，arguments: {limit:50}
- get_hot_concepts: 个股热门概念，arguments: {code}
- get_option_contracts: ETF期权合约，arguments: {underlying:"510050", call:true}
- get_option_quote: 期权T型报价，arguments: {option_code}
- get_option_greeks: 期权希腊值，arguments: {option_code}
- get_hot_concepts/get_holder_changes 等更多工具名称不在此列时，使用后返回的错误会提示参数问题，可按提示重试。`;
  return [
    {
      name: "stock_data",
      label: "股票数据",
      description: stockDataGuide,
      parameters: Type.Object({
        tool: Type.String({ description: "后端白名单工具名（见描述速查）" }),
        arguments: Type.Record(Type.String(), Type.Unknown()),
      }),
      execute: async (_id, params) => textResult(await callBackend(params.tool, params.arguments), { tool: params.tool }),
    },
    {
      name: "web_search",
      label: "联网搜索",
      description: "通过 AnySearch MCP 进行只读联网搜索，用于获取实时新闻和公开资料。不得用于登录、写入或交易。",
      parameters: Type.Object({ query: Type.String(), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: MAX_SEARCH_RESULTS })) }),
      execute: async (_id, params) => textResult(await webSearch(params.query, params.limit || 5), { tool: "web_search" }),
    },
    {
      name: "web_batch_search",
      label: "批量联网搜索",
      description: "通过 AnySearch MCP 并行执行 1-5 个只读搜索查询。",
      parameters: Type.Object({ queries: Type.Array(Type.Record(Type.String(), Type.Unknown()), { minItems: 1, maxItems: 5 }) }),
      execute: async (_id, params) => textResult(await webBatchSearch(params.queries), { tool: "web_batch_search" }),
    },
    {
      name: "web_get_sub_domains",
      label: "搜索领域发现",
      description: "通过 AnySearch MCP 发现垂直搜索领域，只读。",
      parameters: Type.Object({ domains: Type.Array(Type.String(), { minItems: 1, maxItems: 8 }) }),
      execute: async (_id, params) => textResult(await webSubDomains(params.domains), { tool: "web_get_sub_domains" }),
    },
    {
      name: "web_extract",
      label: "AnySearch 网页提取",
      description: "通过 AnySearch MCP 提取公开网页内容，只读，不执行登录、写入或交易。",
      parameters: Type.Object({ urls: Type.Union([Type.String(), Type.Array(Type.String(), { minItems: 1, maxItems: 5 })]) }),
      execute: async (_id, params) => textResult(await webExtract(params.urls), { tool: "web_extract" }),
    },
    {
      name: "web_open",
      label: "读取网页",
      description: "只读读取公开 http/https 网页并提取文本。",
      parameters: Type.Object({ url: Type.String() }),
      execute: async (_id, params) => textResult(await webOpen(params.url), { tool: "web_open" }),
    },
  ];
}

function toAgentMessage(message) {
  return { role: message.role, content: [{ type: "text", text: String(message.content || "") }], timestamp: Date.now() };
}

function extractAnswer(agent) {
  const messages = agent.state.messages || [];
  const final = [...messages].reverse().find((message) => message.role === "assistant");
  return (final?.content || []).filter((part) => part.type === "text").map((part) => part.text).join("").trim();
}

async function runTextAgent(model, systemPrompt, prompt, agentTools = []) {
  const agent = new Agent({
    initialState: { systemPrompt, model, tools: agentTools, messages: [] },
    streamFn: streamSimple,
    toolExecution: "sequential",
  });
  await agent.prompt(prompt);
  const answer = extractAnswer(agent);
  if (!answer) throw new Error("Pi 子 Agent 未返回可用回答");
  return answer;
}

async function collectFreshEvidence(query, requirements, traces) {
  const evidence = [];
  const code = requirements.codes?.[0];
  if (requirements.needsMarketQuote) {
    try {
      const result = await callBackend("get_market_quote", { codes: requirements.codes });
      const item = { kind: "quote", source: result.source || "股票数据工具", updatedAt: result.updatedAt || new Date().toISOString(), data: result.data };
      evidence.push(item);
      traces.push({ tool: "get_market_quote", status: result.status || "success", arguments: { codes: requirements.codes }, source: item.source, resultPreview: JSON.stringify(result.data, ensureJson).slice(0, 600), updatedAt: item.updatedAt });
    } catch (error) {
      const item = { kind: "quote", source: "股票数据工具", updatedAt: new Date().toISOString(), error: error instanceof Error ? error.message : String(error) };
      evidence.push(item);
      traces.push({ tool: "get_market_quote", status: "error", arguments: { codes: requirements.codes }, source: item.source, error: item.error, updatedAt: item.updatedAt });
    }
  }
  if (requirements.needsKline && code) {
    try {
      const result = await callBackend("get_kline_with_ma", { code, limit: 90 });
      const item = { kind: "kline", source: result.source || "股票数据工具", updatedAt: result.updatedAt || new Date().toISOString(), data: result.data };
      evidence.push(item);
      traces.push({ tool: "get_kline_with_ma", status: result.status || "success", arguments: { code }, source: item.source, resultPreview: JSON.stringify(result.data, ensureJson).slice(0, 600), updatedAt: item.updatedAt });
    } catch (error) {
      const item = { kind: "kline", source: "股票数据工具", updatedAt: new Date().toISOString(), error: error instanceof Error ? error.message : String(error) };
      evidence.push(item);
      traces.push({ tool: "get_kline_with_ma", status: "error", arguments: { code }, source: item.source, error: item.error, updatedAt: item.updatedAt });
    }
  }
  if (requirements.needsFinancials && code) {
    try {
      const statements = await callBackend("get_financial_statements", { code, report_type: "lrb", periods: 8 });
      const item = { kind: "financials", source: statements.source || "股票数据工具", updatedAt: statements.updatedAt || new Date().toISOString(), data: statements.data };
      evidence.push(item);
      traces.push({ tool: "get_financial_statements", status: statements.status || "success", arguments: { code, report_type: "lrb", periods: 8 }, source: item.source, resultPreview: JSON.stringify(statements.data, ensureJson).slice(0, 600), updatedAt: item.updatedAt });
    } catch (error) {
      const item = { kind: "financials", source: "股票数据工具", updatedAt: new Date().toISOString(), error: error instanceof Error ? error.message : String(error) };
      evidence.push(item);
      traces.push({ tool: "get_financial_statements", status: "error", arguments: { code }, source: item.source, error: item.error, updatedAt: item.updatedAt });
    }
  }
  if (requirements.needsWebSearch) {
    try {
      const result = await webSearch(query, 5);
      const item = { kind: "web", source: "AnySearch MCP", updatedAt: new Date().toISOString(), data: result.data };
      evidence.push(item);
      traces.push({ tool: "web_search", status: "success", arguments: { query }, source: item.source, resultPreview: JSON.stringify(result.data, ensureJson).slice(0, 600), updatedAt: item.updatedAt });
    } catch (error) {
      const item = { kind: "web", source: "AnySearch MCP", updatedAt: new Date().toISOString(), error: error instanceof Error ? error.message : String(error) };
      evidence.push(item);
      traces.push({ tool: "web_search", status: "error", arguments: { query }, source: item.source, error: item.error, updatedAt: item.updatedAt });
    }
  }
  return evidence;
}

const SPECIALIST_ROLES = [
  ["行情维度", "只看实时行情、成交量、资金与数据时效；不得预测涨跌。"],
  ["技术维度", "只看趋势、均线、指标和形态；区分历史事实与不确定性。"],
  ["基本面维度", "只看财报、估值、盈利和经营质量；标注报告期。"],
  ["新闻事件维度", "只看新闻、公告、政策和事件影响；标注来源和发布时间。"],
  ["风险维度", "只识别风险、数据缺口和需要进一步核查的事项。"],
];

async function runSpecialistSynthesis(model, systemPrompt, query, evidence) {
  const evidenceText = JSON.stringify(evidence, ensureJson);
  const specialistResults = await Promise.all(SPECIALIST_ROLES.map(async ([angle, instruction]) => {
    const prompt = `请从【${angle}】审视以下已获取的资料并回答用户问题。${instruction}\n\n用户问题：${query}\n\n资料（只能基于这些资料，不得编造，标注来源与时间）：${evidenceText}\n\n请用中文输出不超过 5 条要点，每条标注属于事实、分析或不确定性，不要提及分析流程或系统机制。`;
    return { angle, answer: await runTextAgent(model, systemPrompt, prompt) };
  }));
  const shortQuery = query.length <= 24;
  const synthesisPrompt = `你是股票研究分析师，请综合多角度的分析回答用户问题。\n\n用户问题：${query}\n\n参考资料（必须标注来源和时间）：${evidenceText}\n\n分项分析结果：${JSON.stringify(specialistResults, ensureJson)}\n\n输出要求：\n1. 篇幅与问题匹配：${shortQuery ? "这是简短查询，请直接给出精炼、信息密度高的回答（要点或小表格即可），不要长篇报告。" : "请按 核心观点 / 数据依据 / 分项分析 / 风险因素 / 仍需核查 的结构组织，便于阅读。"}\n2. 以自然、专业的分析师口吻作答，不要提及"子分析、多视角、合成、分项"等内部机制。\n3. 每条关键数据保留来源与时间标注。\n4. 明确区分事实、分析和不确定性。\n5. 禁止涨跌预测、目标价、买卖或仓位建议。`;
  return runTextAgent(model, systemPrompt, synthesisPrompt);
}

async function run(request) {
  const last = request.messages?.at(-1);
  const classification = classifyRequest(last?.content || request.content || "");
  if (!classification.allowed) return { answer: classification.message, toolCalls: [] };
  const model = modelFor(request.model || "deepseek");
  const query = last?.content || request.content || "";
  const requirements = researchRequirements(query);
  const intent = classifyIntent(query);
  // research: 综合研究 -> 多视角证据合成；data: 明确数据/指标查询 -> 交给可自主调工具的 Agent；chat: 普通对话
  const researchLike = intent === "research" || (intent === "chat" && /股票|行情|财报|估值|技术|行业|风险|个股|指数|ETF|公告|政策|怎么看|怎么样|建议/i.test(query));
  const preflightTraces = [];
  const evidence = researchLike ? await collectFreshEvidence(query, requirements, preflightTraces) : [];
  const basePrompt = request.systemPrompt + (evidence.length ? `\n\n## 已获取的研究资料（含来源与时间）\n${JSON.stringify(evidence, ensureJson)}` : "");
  if (researchLike) {
    try {
      const answer = await runSpecialistSynthesis(model, basePrompt, query, evidence);
      return { answer: enforceFinancialSafety(appendEvidenceCitations(answer, evidence)), toolCalls: preflightTraces, evidence };
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      return {
        answer: enforceFinancialSafety(buildToolFallback(query, preflightTraces, `分析模型未完成：${reason}。以上先返回已取得的数据。`)),
        toolCalls: preflightTraces,
        evidence,
      };
    }
  }
  const history = (request.messages || []).slice(0, -1).map(toAgentMessage);
  const agent = new Agent({
    initialState: {
      systemPrompt: request.systemPrompt + "\n\n## 输出规范\n直接给出结构化的最终答案，不要输出思考过程、计划或任何“让我…/我来…”类过程性文字；关键数据注明来源与时间；涉及合规边界时如实说明。",
      model,
      tools: tools(),
      messages: history,
    },
    streamFn: streamSimple,
    toolExecution: "sequential",
  });
  let toolCalls = 0;
  const traces = [];
  agent.beforeToolCall = async ({ toolCall }) => {
    toolCalls += 1;
    if (toolCalls > MAX_TOOL_CALLS) return { block: true, reason: "本轮工具调用次数已达到上限" };
    if (!["stock_data", "web_search", "web_batch_search", "web_get_sub_domains", "web_extract", "web_open"].includes(toolCall.name)) return { block: true, reason: "工具不在股票助手白名单中" };
    return undefined;
  };
  agent.afterToolCall = async ({ toolCall, result }) => {
    traces.push({ tool: toolCall.name, status: result?.isError ? "error" : "success", arguments: toolCall.arguments, result: result.details || null, resultPreview: resultPreview(result), updatedAt: new Date().toISOString() });
    return undefined;
  };
  try {
    await agent.prompt(query);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { answer: enforceFinancialSafety(buildToolFallback(query, traces, `模型未完成收尾：${reason}。以上先返回已取得的数据。`)), toolCalls: traces };
  }
  const answer = extractAnswer(agent);
  if (!answer) {
    return { answer: enforceFinancialSafety(buildToolFallback(query, traces)), toolCalls: traces };
  }
  return { answer: enforceFinancialSafety(answer), toolCalls: traces };
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  try {
    const request = JSON.parse(line);
    process.stdout.write(`${JSON.stringify(await run(request), ensureJson)}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ error: error instanceof Error ? error.message : String(error) })}\n`);
  }
}
