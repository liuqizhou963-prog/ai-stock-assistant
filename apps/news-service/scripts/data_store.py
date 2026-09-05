import json
import os
from pathlib import Path


SCHEMA_VERSION = 1
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "generated_at",
    "recent_days",
    "industries",
    "stats",
    "has_ai",
}
REQUIRED_INDUSTRY_FIELDS = {
    "key",
    "name",
    "accent",
    "total",
    "items",
    "points",
}


def ensure_schema(data):
    # ensure_schema（补齐当前版本号）
    result = dict(data)
    result.setdefault("schema_version", SCHEMA_VERSION)
    return result


def validate_data(data):
    # validate_data（校验网页数据契约）
    if not isinstance(data, dict):
        raise ValueError("网页数据必须是对象")

    missing = REQUIRED_TOP_LEVEL - set(data)
    if missing:
        raise ValueError("网页数据缺少字段：" + ", ".join(sorted(missing)))

    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError("不支持的数据版本：{}".format(data["schema_version"]))

    if not isinstance(data["industries"], list):
        raise ValueError("industries 必须是数组")

    if not isinstance(data["stats"], dict):
        raise ValueError("stats 必须是对象")

    if not isinstance(data["has_ai"], bool):
        raise ValueError("has_ai 必须是布尔值")

    for industry in data["industries"]:
        if not isinstance(industry, dict):
            raise ValueError("行业数据必须是对象")

        missing = REQUIRED_INDUSTRY_FIELDS - set(industry)
        if missing:
            raise ValueError("行业数据缺少字段：" + ", ".join(sorted(missing)))

        if not isinstance(industry["items"], list):
            raise ValueError("行业 items 必须是数组")
        if not isinstance(industry["points"], list):
            raise ValueError("行业 points 必须是数组")

    return data


def _parse_data_text(text):
    # _parse_data_text（从 data.js 中提取 JSON 数据）
    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end < start:
        raise ValueError("data.js 中没有找到数据对象")

    return json.loads(text[start:end + 1])


def load_data_file(path):
    # load_data_file（读取并校验网页数据文件）
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    data = ensure_schema(_parse_data_text(text))
    return validate_data(data)


def write_data_file(data, path):
    # write_data_file（校验后原子替换网页数据文件）
    path = Path(path)
    data = ensure_schema(data)
    validate_data(data)

    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )
    temporary_path = Path(str(path) + ".candidate")

    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write("window.DATA = ")
            file.write(payload)
            file.write(";\n")
            file.flush()
            os.fsync(file.fileno())

        checked = load_data_file(temporary_path)
        validate_data(checked)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
