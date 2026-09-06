const DEFAULT_ENDPOINT = "https://api.anysearch.com/mcp";
const PROTOCOL_VERSION = "2025-03-26";
const READ_ONLY_TOOLS = new Set(["search", "batch_search", "get_sub_domains", "extract"]);

export class AnySearchMcpClient {
  constructor(endpoint = process.env.ANYSEARCH_MCP_URL?.trim() || DEFAULT_ENDPOINT) {
    this.endpoint = endpoint;
    this.sessionId = undefined;
    this.requestId = 0;
    this.initialized = false;
  }

  async listTools() {
    await this.initialize();
    const result = await this.request("tools/list", {});
    return (result.tools || []).filter((tool) => READ_ONLY_TOOLS.has(tool.name));
  }

  async call(tool, arguments_) {
    if (!READ_ONLY_TOOLS.has(tool)) throw new Error("AnySearch 工具不在只读白名单中");
    await this.initialize();
    return this.request("tools/call", { name: tool, arguments: arguments_ });
  }

  async initialize() {
    if (this.initialized) return;
    await this.request("initialize", {
      protocolVersion: PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: "stock-assistant", version: "0.1.0" },
    });
    this.initialized = true;
  }

  async request(method, params) {
    const headers = {
      accept: "application/json, text/event-stream",
      "content-type": "application/json",
    };
    if (this.sessionId) headers["mcp-session-id"] = this.sessionId;
    const response = await fetch(this.endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify({ jsonrpc: "2.0", id: ++this.requestId, method, params }),
      signal: AbortSignal.timeout(25_000),
    });
    if (!response.ok) throw new Error(`AnySearch MCP 返回 HTTP ${response.status}`);
    const sessionId = response.headers.get("mcp-session-id");
    if (sessionId) this.sessionId = sessionId;
    const body = await response.json();
    if (body.error) throw new Error(body.error.message || "AnySearch MCP 请求失败");
    return body.result || {};
  }
}
