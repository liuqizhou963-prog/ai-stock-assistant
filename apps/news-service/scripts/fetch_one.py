import json
import sys
import urllib.error
import urllib.request

from feed_parser import parse_feed
# parse_feed（信息源解析函数）


USER_AGENT = "investment-news-copy/0.1"
# USER_AGENT（请求身份说明）

TIMEOUT = 20
# TIMEOUT（请求超时时间，单位为秒）

MAX_ITEMS = 5
# MAX_ITEMS（单个信息源最多保留的新闻数量）

def fetch_one(url, source_name, timeout=TIMEOUT):
    # fetch_one（抓取一个真实信息源）
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw_xml = response.read()

    return parse_feed(raw_xml, source_name)[:MAX_ITEMS]


def main():
    # main（命令行入口）
    if len(sys.argv) != 3:
        print(
            "用法：python scripts/fetch_one.py 信息源地址 信息源名称"
        )
        raise SystemExit(2)

    url = sys.argv[1]
    source_name = sys.argv[2]

    try:
        items = fetch_one(url, source_name)
    except urllib.error.HTTPError as error:
        print("HTTP 请求失败：", error.code)
        raise SystemExit(1)
    except urllib.error.URLError as error:
        print("网络请求失败：", error.reason)
        raise SystemExit(1)
    except Exception as error:
        print("信息源处理失败：", error)
        raise SystemExit(1)

    print(json.dumps(items, ensure_ascii=False, indent=2))
    print("成功解析新闻条数：", len(items))


if __name__ == "__main__":
    main()
