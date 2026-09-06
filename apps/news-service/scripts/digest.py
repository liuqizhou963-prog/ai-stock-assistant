import json
import os
from concurrent.futures import ThreadPoolExecutor

import llm
# llm（大模型统一适配层）

from data_store import load_data_file, write_data_file
# data_store（网页数据契约和原子写入模块）


HERE = os.path.dirname(os.path.abspath(__file__))
# HERE（当前脚本所在目录）

ROOT = os.path.dirname(HERE)
# ROOT（项目根目录）

TOPN = 16
# TOPN（每个行业最多交给模型处理的新闻数量）

MIN_POINTS = 3
# MIN_POINTS（今日要点的最少数量）

MAX_POINTS = 5
# MAX_POINTS（今日要点的最多数量）

MAX_POINT_LENGTH = 40
# MAX_POINT_LENGTH（单条今日要点的最大字符数）

ATTEMPTS = 3
# ATTEMPTS（单个行业的最大尝试次数）

MAX_WORKERS = 4
# MAX_WORKERS（并行处理行业摘要，避免 12 个行业完全串行等待）

SYSTEM_PROMPT = """
你是中文行业新闻分析助手。
输入是一组带编号的行业新闻，请完成两件事：
1. 提炼 3 到 5 条今日要点，每条不超过 40 个字符，客观描述重要动向。
2. 为每条新闻生成准确、简洁的中文标题；如果原文已经是中文，原样返回。

只能输出 JSON，不要输出解释、Markdown 或代码块。
格式必须是：
{
  "points": [
    {"t": "要点文本", "refs": [0, 2]}
  ],
  "items": [
    {"i": 0, "zh": "中文标题"}
  ]
}

refs 只能引用输入中真实存在的新闻编号。
""".strip()


def extract_json(text):
    # extract_json（从模型文本中提取 JSON 对象）
    if not isinstance(text, str):
        return None

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end < start:
        return None

    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    return value if isinstance(value, dict) else None


def build_user_prompt(industry):
    # build_user_prompt（构建单个行业的模型输入）
    lines = [
        "行业：" + str(industry.get("name", "")),
        "新闻：",
    ]

    for index, item in enumerate(industry.get("items", [])[:TOPN]):
        lines.append(
            f"{index}. {item.get('title', '')}"
            f" | 来源：{item.get('source', '')}"
            f" | 摘要：{item.get('summary', '')}"
        )

    return "\n".join(lines)


def _response_error(message):
    # _response_error（创建模型返回格式错误）
    return llm.LLMError("response", message)


def validate_model_result(value, item_count):
    # validate_model_result（校验模型返回的结构和引用）
    if not isinstance(value, dict):
        raise _response_error("模型返回不是对象")

    raw_points = value.get("points")
    raw_items = value.get("items")

    if not isinstance(raw_points, list):
        raise _response_error("points 必须是数组")

    if not MIN_POINTS <= len(raw_points) <= MAX_POINTS:
        raise _response_error("points 数量必须是 3 到 5 条")

    points = []

    for point in raw_points:
        if not isinstance(point, dict):
            raise _response_error("point 必须是对象")

        text = point.get("t")
        refs = point.get("refs")

        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text.strip()) > MAX_POINT_LENGTH
        ):
            raise _response_error("今日要点文本不合法")

        if not isinstance(refs, list) or not refs:
            raise _response_error("每条要点必须有 refs 引用")

        clean_refs = []

        for ref in refs:
            if isinstance(ref, bool) or not isinstance(ref, int):
                raise _response_error("refs 必须是整数编号")
            if ref < 0 or ref >= item_count:
                raise _response_error("refs 引用了不存在的新闻编号")
            if ref not in clean_refs:
                clean_refs.append(ref)

        points.append({
            "t": text.strip(),
            "refs": clean_refs,
        })

    if not isinstance(raw_items, list):
        raise _response_error("items 必须是数组")

    translations = {}

    for item in raw_items:
        if not isinstance(item, dict):
            raise _response_error("翻译条目必须是对象")

        index = item.get("i")
        title = item.get("zh")

        if isinstance(index, bool) or not isinstance(index, int):
            raise _response_error("翻译条目的 i 必须是整数")
        if index < 0 or index >= item_count:
            raise _response_error("翻译条目引用了不存在的新闻编号")
        if index in translations:
            raise _response_error("同一新闻不能重复翻译")
        if not isinstance(title, str) or not title.strip():
            raise _response_error("中文标题不能为空")

        translations[index] = title.strip()

    if len(translations) != item_count:
        raise _response_error("必须为每条新闻返回中文标题")

    return {
        "points": points,
        "translations": translations,
    }


def _is_retryable(error):
    # _is_retryable（判断错误是否值得重试）
    return getattr(error, "kind", "") in {
        "timeout",
        "http",
        "process",
        "response",
    }


def process_industry(industry, call_model, attempts=ATTEMPTS):
    # process_industry（处理一个行业的摘要、翻译和引用）
    result = dict(industry)
    result["items"] = [
        dict(item)
        for item in industry.get("items", [])[:TOPN]
    ]

    if not result["items"]:
        result["points"] = []
        return result, True

    prompt = build_user_prompt(result)
    last_error = None

    for _ in range(attempts):
        try:
            raw = call_model(SYSTEM_PROMPT, prompt)
            value = extract_json(raw)

            if value is None:
                raise _response_error("模型没有返回合法 JSON")

            checked = validate_model_result(
                value,
                len(result["items"]),
            )
        except llm.LLMError as error:
            last_error = error
            if not _is_retryable(error):
                break
            continue

        result["points"] = [
            {
                "t": point["t"],
                "url": result["items"][point["refs"][0]]["url"],
            }
            for point in checked["points"]
        ]

        for index, title in checked["translations"].items():
            result["items"][index]["zh"] = title

        return result, True

    result["points"] = []
    return result, False


def digest_data(data, config, call_model=None):
    # digest_data（处理整个看板数据并保留部分成功结果）
    if call_model is None:
        def call_model(system, user):
            return llm.call(system, user, config=config)

    result = dict(data)
    source_industries = data.get("industries", [])
    non_empty = sum(bool(industry.get("items")) for industry in source_industries)

    # 保持输入顺序，同时让多个行业共享有限的并发度。
    worker_count = min(MAX_WORKERS, max(1, len(source_industries)))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        processed_results = list(
            pool.map(
                lambda industry: process_industry(industry, call_model),
                source_industries,
            )
        )

    industries = [processed for processed, _ in processed_results]
    successful = sum(
        1
        for processed, ok in processed_results
        if ok and processed.get("items")
    )

    result["industries"] = industries
    result["has_ai"] = non_empty > 0 and successful == non_empty
    return result


def main():
    # main（程序入口）
    data_path = os.path.join(ROOT, "data.js")
    try:
        config = llm.load_config(ROOT)
    except llm.LLMError as error:
        # 模型配置是可选的：没有配置时仍应保留抓取到的资讯，
        # 只跳过 AI 要点和标题翻译，避免整次刷新失败。
        if error.kind != "config" or str(error) != "缺少 llm.config.json":
            raise
        data = load_data_file(__import__("pathlib").Path(data_path))
        result = dict(data)
        result["has_ai"] = False
        write_data_file(result, __import__("pathlib").Path(data_path))
        print("未配置 llm.config.json，已保留抓取资讯并跳过 AI 摘要")
        return

    data = load_data_file(__import__("pathlib").Path(data_path))
    result = digest_data(data, config)

    has_items = any(
        bool(industry.get("items"))
        for industry in result.get("industries", [])
    )

    if has_items and not result.get("has_ai"):
        print("摘要阶段失败：至少一个行业未完成摘要")
        raise SystemExit(2)

    write_data_file(result, __import__("pathlib").Path(data_path))
    print("摘要和翻译处理完成，has_ai=", result["has_ai"])


if __name__ == "__main__":
    main()
