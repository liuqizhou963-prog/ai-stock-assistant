import test from "node:test";
import assert from "node:assert/strict";
import { buildToolFallback } from "./src/response-fallback.mjs";

test("returns successful tool results when the tool budget is exhausted", () => {
  const answer = buildToolFallback("分析行业", [
    { tool: "get_market_quote", status: "success", resultPreview: '{"涨幅":2.1}' },
    { tool: "get_full_valuation", status: "error", resultPreview: "" },
  ], "工具调用已达到上限，以上为已取得结果。");

  assert.match(answer, /get_market_quote/);
  assert.match(answer, /涨幅/);
  assert.match(answer, /未完成：1 项/);
  assert.match(answer, /已达到上限/);
});
