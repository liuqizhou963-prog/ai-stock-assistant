"""
会话工作记忆（Session Working Memory）
优先使用 Redis；Redis 不可用时自动降级到进程内存字典。
Key 格式：session:{conv_id}
每个会话保留最近 MAX_MESSAGES 条，TTL 24 小时。
"""
import json
import threading
import time

SESSION_TTL = 86400   # 24 小时
MAX_MESSAGES = 10
REDIS_URL = "redis://localhost:6379"

# ---------- Redis 连接（可选依赖） ----------
_redis_client = None
_redis_checked = False
_redis_lock = threading.Lock()


def _get_redis():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    with _redis_lock:
        if _redis_checked:
            return _redis_client
        try:
            import redis  # noqa: PLC0415
            r = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
            r.ping()
            _redis_client = r
        except Exception:
            _redis_client = None
        _redis_checked = True
    return _redis_client


# ---------- 内存降级存储 ----------
_mem_store: dict = {}   # key -> list[str]（JSON 字符串，最新在前）
_summary_store: dict = {}
_mem_lock = threading.Lock()


def _merge_summary(previous, messages):
    topics = []
    if previous:
        topics.append(str(previous).replace("此前对话主题：", ""))
    for message in messages:
        if message.get("role") == "user":
            content = str(message.get("content", "")).strip()
            if content:
                topics.append(content[:100])
    unique = list(dict.fromkeys(topics))[-4:]
    return "此前对话主题：" + "；".join(unique)[:360] if unique else ""


# ---------- 公共接口 ----------

def get_history(conv_id: str) -> list:
    """
    返回该会话最近 MAX_MESSAGES 条消息列表（由旧到新）。
    每条格式：{"role": "user"/"assistant", "content": "..."}
    """
    key = f"session:{conv_id}"
    r = _get_redis()
    if r:
        try:
            raw_list = r.lrange(key, 0, MAX_MESSAGES - 1)  # 最新在前
            msgs = [json.loads(x) for x in raw_list]
            summary = r.get(key + ":summary")
            result = list(reversed(msgs))
            return ([{"role": "system", "content": summary}] if summary else []) + result
        except Exception:
            pass

    # 内存降级
    with _mem_lock:
        msgs = list(_mem_store.get(key, []))
        summary = _summary_store.get(key, "")
    result = list(reversed(msgs[:MAX_MESSAGES]))
    return ([{"role": "system", "content": summary}] if summary else []) + result


def add_messages(conv_id: str, user_message: str, assistant_reply: str) -> None:
    """一次性写入用户消息和助手回复（保持原子性）。"""
    key = f"session:{conv_id}"
    user_entry = json.dumps({"role": "user", "content": user_message}, ensure_ascii=False)
    asst_entry = json.dumps({"role": "assistant", "content": assistant_reply}, ensure_ascii=False)

    r = _get_redis()
    if r:
        try:
            existing = [json.loads(x) for x in r.lrange(key, 0, MAX_MESSAGES - 1)]
            summary = _merge_summary(r.get(key + ":summary"), existing)
            pipe = r.pipeline()
            # lpush 最新在前；先 push assistant 再 push user，
            # 这样 lrange 读到的顺序是 [assistant, user, ...]（最新在前）
            pipe.lpush(key, asst_entry, user_entry)
            pipe.ltrim(key, 0, MAX_MESSAGES - 1)
            pipe.expire(key, SESSION_TTL)
            if summary:
                pipe.set(key + ":summary", summary, ex=SESSION_TTL)
            pipe.execute()
            return
        except Exception:
            pass

    # 内存降级（最新在前）
    with _mem_lock:
        msgs = _mem_store.setdefault(key, [])
        _summary_store[key] = _merge_summary(_summary_store.get(key, ""), msgs)
        msgs.insert(0, json.loads(asst_entry))
        msgs.insert(0, json.loads(user_entry))
        _mem_store[key] = msgs[:MAX_MESSAGES]
