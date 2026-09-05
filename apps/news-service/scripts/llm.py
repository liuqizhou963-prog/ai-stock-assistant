import json
import os
import shutil
import socket
import subprocess
import tempfile
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit


MAX_TIMEOUT = 600
MAX_PROMPT_CHARS = 30000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_CHARS = 100000
ALLOWED_TOP_LEVEL_KEYS = {"provider", "api"}
ALLOWED_API_KEYS = {"base_url", "api_key", "api_key_env", "model"}
OPENAI_COMPAT_PROVIDERS = {"api"}          # 走 OpenAI /chat/completions 格式
ANTHROPIC_PROVIDERS     = {"claude-api"}   # 走 Anthropic /v1/messages 格式
ALL_API_PROVIDERS = OPENAI_COMPAT_PROVIDERS | ANTHROPIC_PROVIDERS


class LLMError(RuntimeError):
    # LLMError（大模型统一错误）
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def load_config(root):
    # load_config（读取并校验模型配置）
    path = os.path.join(root, "llm.config.json")

    try:
        with open(path, encoding="utf-8") as file:
            config = json.load(file)
    except FileNotFoundError as error:
        raise LLMError("config", "缺少 llm.config.json") from error
    except json.JSONDecodeError as error:
        raise LLMError("config", "llm.config.json 不是有效 JSON") from error

    provider = config.get("provider")

    unknown = set(config) - ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        raise LLMError("config", "模型配置存在未知字段：" + ", ".join(sorted(unknown)))

    if provider not in {"claude-cli"} | ALL_API_PROVIDERS:
        raise LLMError(
            "config",
            "provider 必须是 claude-cli、api 或 claude-api",
        )

    if provider in ALL_API_PROVIDERS:
        api = config.get("api")

        if not isinstance(api, dict):
            raise LLMError("config", "api 配置必须是对象")

        # claude-api 的 base_url 可选（有默认值），其余 provider 必填
        if provider in OPENAI_COMPAT_PROVIDERS and not api.get("base_url"):
            raise LLMError("config", "api.base_url 不能为空")

        if not api.get("model"):
            raise LLMError("config", "api.model 不能为空")

        unknown = set(api) - ALLOWED_API_KEYS
        if unknown:
            raise LLMError("config", "api 配置存在未知字段：" + ", ".join(sorted(unknown)))

        if provider in OPENAI_COMPAT_PROVIDERS:
            base_url = api.get("base_url", "")
            parts = urlsplit(base_url)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise LLMError("config", "api.base_url 必须是 http 或 https 地址")

        if len(api["model"]) > 200:
            raise LLMError("config", "api.model 过长")

        api_key_env = api.get("api_key_env", "LLM_API_KEY")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", api_key_env):
            raise LLMError("config", "api_key_env 不是合法环境变量名")

    return config


def _call_cli(system, user, timeout):
    # _call_cli（调用本机 Claude 命令行工具）
    claude_path = shutil.which("claude")

    if not claude_path:
        raise LLMError("unavailable", "没有找到 claude 命令")

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".txt",
        delete=False,
    ) as file:
        file.write(system)
        system_path = file.name

    try:
        completed = subprocess.run(
            [
                claude_path,
                "-p",
                "--output-format",
                "text",
                "--system-prompt-file",
                system_path,
            ],
            input=user,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise LLMError("timeout", "Claude 调用超时") from error
    finally:
        os.unlink(system_path)

    if completed.returncode != 0:
        raise LLMError(
            "process",
            "Claude 进程失败：" + completed.stderr[:160],
        )

    text = completed.stdout.strip()

    if len(text) > MAX_OUTPUT_CHARS:
        raise LLMError("response", "Claude 返回内容超过大小限制")

    if not text:
        raise LLMError("response", "Claude 返回了空文本")

    return text


def _call_api(system, user, config, timeout):
    # _call_api（调用兼容聊天接口）
    api = config["api"]
    env_name = api.get("api_key_env", "LLM_API_KEY")
    api_key = api.get("api_key") or os.environ.get(env_name)

    if not api_key:
        raise LLMError("config", "没有找到 API 密钥")

    body = json.dumps({
        "model": api["model"],
        "temperature": 0.3,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")

    request = urllib.request.Request(
        api["base_url"].rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise LLMError("http", "模型接口返回 HTTP 错误") from error
    except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
        raise LLMError("timeout", "模型接口请求失败或超时") from error

    if len(raw) > MAX_RESPONSE_BYTES:
        raise LLMError("response", "模型接口响应超过大小限制")

    try:
        data = json.loads(raw.decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as error:
        raise LLMError("response", "模型接口返回格式错误") from error

    if not isinstance(text, str) or not text.strip():
        raise LLMError("response", "模型接口返回了空文本")

    return text.strip()


def _stream_api(system, user, config, timeout):
    """Yield text deltas from an OpenAI-compatible SSE response."""
    api = config["api"]
    env_name = api.get("api_key_env", "LLM_API_KEY")
    api_key = api.get("api_key") or os.environ.get(env_name)

    if not api_key:
        raise LLMError("config", "没有找到 API 密钥")

    body = json.dumps({
        "model": api["model"],
        "temperature": 0.3,
        "stream": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    request = urllib.request.Request(
        api["base_url"].rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )

    total_bytes = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                total_bytes += len(raw_line)
                if total_bytes > MAX_RESPONSE_BYTES:
                    raise LLMError("response", "模型流式响应超过大小限制")
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    choices = data.get("choices") or []
                    delta = choices[0].get("delta") or {} if choices else {}
                    text = delta.get("content")
                except (json.JSONDecodeError, TypeError, IndexError) as error:
                    raise LLMError("response", "模型流式响应格式错误") from error
                if isinstance(text, str) and text:
                    yield text
    except urllib.error.HTTPError as error:
        raise LLMError("http", "模型接口返回 HTTP 错误") from error
    except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
        raise LLMError("timeout", "模型接口请求失败或超时") from error


def stream_call(system, user, config=None, timeout=240):
    """Yield model text deltas where the configured provider supports them."""
    if not isinstance(system, str) or not isinstance(user, str):
        raise LLMError("config", "模型输入必须是文本")
    if len(system) + len(user) > MAX_PROMPT_CHARS:
        raise LLMError("config", "模型输入超过长度限制")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise LLMError("config", "模型超时必须是数字")
    if not 1 <= timeout <= MAX_TIMEOUT:
        raise LLMError("config", "模型超时必须在 1 到 {} 秒之间".format(MAX_TIMEOUT))

    config = config or {"provider": "claude-cli"}
    provider = config.get("provider")

    if provider == "api":
        yield from _stream_api(system, user, config, timeout)
        return

    # These providers have no token iterator in the current adapter. Keep the
    # streaming contract and send their completed response as one chunk.
    if provider == "claude-cli":
        yield _call_cli(system, user, timeout)
        return
    if provider == "claude-api":
        yield _call_claude_api(system, user, config, timeout)
        return
    raise LLMError("config", "不支持的模型供应方")


def _call_claude_api(system, user, config, timeout):
    # _call_claude_api（调用 Anthropic Claude API，格式与 OpenAI 不同）
    api = config["api"]
    env_name = api.get("api_key_env", "ANTHROPIC_API_KEY")
    api_key = api.get("api_key") or os.environ.get(env_name)

    if not api_key:
        raise LLMError("config", "没有找到 Anthropic API 密钥")

    base_url = api.get("base_url", "https://api.anthropic.com").rstrip("/")
    model = api["model"]

    body = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")

    request = urllib.request.Request(
        base_url + "/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise LLMError("http", "Claude API 返回 HTTP 错误") from error
    except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
        raise LLMError("timeout", "Claude API 请求失败或超时") from error

    if len(raw) > MAX_RESPONSE_BYTES:
        raise LLMError("response", "Claude API 响应超过大小限制")

    try:
        data = json.loads(raw.decode("utf-8"))
        text = data["content"][0]["text"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise LLMError("response", "Claude API 返回格式错误") from error

    if not isinstance(text, str) or not text.strip():
        raise LLMError("response", "Claude API 返回了空文本")

    return text.strip()


def call(system, user, config=None, timeout=240):
    # call（根据配置选择供应方并返回模型文本）
    if not isinstance(system, str) or not isinstance(user, str):
        raise LLMError("config", "模型输入必须是文本")
    if len(system) + len(user) > MAX_PROMPT_CHARS:
        raise LLMError("config", "模型输入超过长度限制")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise LLMError("config", "模型超时必须是数字")
    if not 1 <= timeout <= MAX_TIMEOUT:
        raise LLMError("config", "模型超时必须在 1 到 {} 秒之间".format(MAX_TIMEOUT))

    config = config or {"provider": "claude-cli"}
    provider = config.get("provider")

    if provider == "claude-cli":
        return _call_cli(system, user, timeout)

    if provider == "api":
        return _call_api(system, user, config, timeout)

    if provider == "claude-api":
        return _call_claude_api(system, user, config, timeout)

    raise LLMError("config", "不支持的模型供应方")
