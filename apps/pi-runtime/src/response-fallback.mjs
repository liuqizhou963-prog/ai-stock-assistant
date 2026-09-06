export function buildToolFallback(query, traces, reason = "") {
  const successful = traces.filter((trace) => trace?.status === "success");
  const failed = traces.filter((trace) => trace?.status !== "success");
  const lines = [`已完成对“${String(query || "").trim()}”的部分检索。`];
  if (successful.length) {
    lines.push("已取得的结果：");
    for (const trace of successful.slice(0, 6)) {
      const preview = String(trace.resultPreview || "").replace(/\s+/g, " ").trim();
      lines.push(`- ${trace.tool || "数据工具"}${preview ? `：${preview.slice(0, 220)}` : "：已返回数据"}`);
    }
  } else {
    lines.push("本轮没有取得可用的数据结果。");
  }
  if (failed.length) {
    lines.push(`未完成：${failed.length} 项数据调用失败或被限制。`);
  }
  lines.push(reason || "你可以缩小查询范围后重试，我会优先整理已经取得的数据。");
  return lines.join("\n");
}
