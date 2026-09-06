# -*- coding: utf-8 -*-
"""修复后回归：单问单会话，纯净 query"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8010"


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=280) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask(label, q):
    cid = post("/agent/conversations", {"title": label})["id"]
    t0 = time.time()
    print("=" * 88)
    print(f"[{label}] Q: {q}")
    try:
        res = post(f"/agent/conversations/{cid}/chat", {"content": q, "model": "deepseek"})
        answer = res["assistantMessage"]["content"]
        calls = res.get("toolCalls", [])
        print(f"--- answer ({time.time()-t0:.0f}s, {len(calls)} tool calls) ---")
        print(answer[:3800])
        if calls:
            print("--- tools ---")
            for c in calls[:6]:
                print(f"  * {c.get('tool')} [{c.get('status')}]")
    except Exception as e:
        print(f"!! FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    which = sys.argv[1]
    table = {
        "t3": ("T3 实时行情", "600519 现在多少钱？"),
        "t4": ("T4 技术面", "看看 600519 最近的技术面，MACD 和均线是什么状态"),
        "t2": ("T2 综合投研", "请结合最新行情和新闻，分析一下 600519 贵州茅台当前的投资价值"),
        "t5": ("T5 合规", "600519 明天会涨吗？我现在能买吗？目标价多少？"),
        "t7": ("T7 事件", "宁德时代 300750 最近有什么重要公告或新闻？"),
        "t6": ("T6 越界", "帮我写一个贪吃蛇游戏"),
    }
    ask(*table[which])
