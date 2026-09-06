import test from "node:test";
import assert from "node:assert/strict";
import { AnySearchMcpClient } from "../src/anysearch-mcp.mjs";

test("initializes AnySearch MCP and exposes its read-only search tools", async () => {
  const client = new AnySearchMcpClient();
  const tools = await client.listTools();

  assert.ok(tools.some((tool) => tool.name === "search"));
  assert.ok(tools.some((tool) => tool.name === "batch_search"));
  assert.ok(tools.some((tool) => tool.name === "get_sub_domains"));
  assert.ok(tools.some((tool) => tool.name === "extract"));
});
