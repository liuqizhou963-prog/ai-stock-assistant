import test from "node:test";
import assert from "node:assert/strict";
import { classifyIntent, classifyRequest, enforceFinancialSafety, researchRequirements } from "../src/policy.mjs";

test("forces fresh market and web evidence for time-sensitive research", () => {
  assert.deepEqual(researchRequirements("请查 600000 今天的行情和最新公告"), {
    needsMarketQuote: true,
    needsWebSearch: true,
    needsKline: false,
    needsFinancials: false,
    codes: ["600000"],
  });
});

test("detects kline and financial evidence needs", () => {
  const technical = researchRequirements("600519 最近的 MACD 和均线状态");
  assert.equal(technical.needsKline, true);
  const fundamental = researchRequirements("300750 最新的财报营收和净利润");
  assert.equal(fundamental.needsFinancials, true);
});

test("classifies data queries vs deep research", () => {
  assert.equal(classifyIntent("600519 现在多少钱？"), "data");
  assert.equal(classifyIntent("看看 600519 的 MACD 和均线状态"), "data");
  assert.equal(classifyIntent("分析一下 600519 贵州茅台当前的投资价值"), "research");
  assert.equal(classifyIntent("今天大盘怎么样"), "data");
});

test("rejects requests outside financial research scope", () => {
  const result = classifyRequest("帮我写一个贪吃蛇游戏");
  assert.equal(result.allowed, false);
  assert.match(result.message, /金融|股票|投研/);
});

test("rewrites deterministic trading advice and forecast language", () => {
  const result = enforceFinancialSafety("明天这只股票必涨，建议立即买入并设置目标价20元");
  assert.doesNotMatch(result, /必涨|立即买入|目标价20元/);
  assert.match(result, /风险提示/);
});

test("blocks return promises, suitability and position instructions", () => {
  const result = enforceFinancialSafety("这只股票稳赚20%，适合你投资，建议配置80%仓位");
  assert.doesNotMatch(result, /稳赚|适合你投资|配置80%仓位/);
  assert.match(result, /风险提示/);
});

test("keeps rating statistics intact (buy 14% is data, not advice)", () => {
  const result = enforceFinancialSafety("机构评级分布：强力推荐 84%，买入 14%，持有 2%，卖出 0%。");
  assert.match(result, /买入\s*14%/);
  assert.match(result, /卖出\s*0%/);
});

test("keeps quoted user language intact", () => {
  const result = enforceFinancialSafety("用户问“明天会涨吗”，这类问题无法给出确定性结论。");
  assert.match(result, /明天会涨吗/);
});

test("keeps compliance self-statements intact", () => {
  const result = enforceFinancialSafety("本报告不构成买入或卖出建议，仅供研究参考。");
  assert.match(result, /不构成买入或卖出建议/);
  assert.doesNotMatch(result, /不构成是否操作需自行评估决策/);
});

test("keeps factual market statements with numbers", () => {
  const result = enforceFinancialSafety("今日大涨2.4%，成交活跃，北向资金净买入5亿元。");
  assert.match(result, /今日大涨2\.4%/);
  assert.match(result, /净买入5亿元/);
});
