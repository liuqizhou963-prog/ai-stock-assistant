import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 fallback
    ZoneInfo = None

BEIJING = (
    ZoneInfo("Asia/Shanghai")
    if ZoneInfo is not None
    else timezone(timedelta(hours=8), name="Asia/Shanghai")
)
# BEIJING（北京时间）


def local_name(tag):
    # local_name（去除 XML 命名空间）
    return tag.split("}")[-1]


def clean_text(value):
    # clean_text（清理摘要中的网页标签和多余空格）
    value = re.sub(r"<[^>]+>", "", value or "")
    return re.sub(r"\s+", " ", value).strip()


def node_text(node):
    # node_text（读取 XML 节点中的全部文本）
    return "".join(node.itertext()).strip()


def parse_datetime(value):
    # parse_datetime（解析新闻发布时间）
    if not value:
        return None

    try:
        result = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            result = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError:
            return None

    # RSS feeds may omit the offset. Interpret that value in the product's
    # China timezone instead of silently shifting it by eight hours.
    if result.tzinfo is None:
        result = result.replace(tzinfo=BEIJING)

    return result


def parse_feed(xml_content, source_name):
    # parse_feed（解析 RSS 或 Atom 信息源）
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as error:
        raise ValueError("XML 格式错误") from error

    entries = [
        node
        for node in root.iter()
        if local_name(node.tag) in ("item", "entry")
    ]

    result = []

    for entry in entries:
        item = {
            "title": "",
            # title（原文标题）

            "url": "",
            # url（原文链接）

            "time": "",
            # time（页面显示时间）

            "ts": 0,
            # ts（数字时间戳）

            "summary": "",
            # summary（新闻摘要）

            "source": source_name,
            # source（信息源名称）
        }

        raw_time = ""

        for child in entry:
            tag = local_name(child.tag)
            value = node_text(child)

            if tag == "title" and not item["title"]:
                item["title"] = value

            elif tag == "link" and not item["url"]:
                item["url"] = child.get("href") or value

            elif tag in ("pubDate", "published", "updated", "date"):
                if not raw_time:
                    raw_time = value

            elif tag in ("description", "summary", "content"):
                if not item["summary"]:
                    item["summary"] = clean_text(value)[:160]

        if not item["title"]:
            continue

        timestamp = parse_datetime(raw_time)

        if timestamp is None:
            item["time"] = "—"
            item["ts"] = 0
        else:
            item["time"] = timestamp.astimezone(BEIJING).strftime(
                "%m-%d %H:%M"
            )
            item["ts"] = int(timestamp.timestamp())

        result.append(item)

    return result
