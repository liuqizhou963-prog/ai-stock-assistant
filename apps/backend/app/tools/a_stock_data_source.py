# Generated from skills/a-stock-data/SKILL.md; do not edit by hand.
import socket
from mootdx.quotes import Quotes
_TDX_SERVERS = [('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709), ('123.60.73.44', 7709), ('116.205.163.254', 7709), ('121.36.225.169', 7709), ('123.60.70.228', 7709), ('124.71.9.153', 7709), ('110.41.147.114', 7709), ('124.71.187.122', 7709)]

def _probe(ip, port, timeout=2.0):
    """TCP 握手探测（快速粗筛）。注意：握手成功 ≠ 能取数，必须再经 _validate 验活。"""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def _validate(client, market: str='std') -> bool:
    """真实取数验活：坏服务器可 TCP 握手通过却回 2 字节空 body → 静默空表。用一次真实 K 线请求兜底。

    验活样本 '000001' 是 A 股代码，只对 market='std' 有意义。其它市场（如扩展行情 'ext'）
    用它必然取不到数，会把所有正常服务器都判死、误报「全部不可达」，故非 std 时跳过验活。
    """
    if market != 'std':
        return True
    try:
        df = client.bars(symbol='000001', frequency=9, offset=1)
        return df is not None and (not df.empty)
    except Exception:
        return False

def tdx_client(market='std'):
    """
    创建 mootdx 客户端，规避 0.11.x BESTIP.HQ 空串 bug + 坏服务器静默空表（#43）。
    每个候选都必须「真实取数验活」通过才采用（_probe TCP 握手是假阳性来源）：
      1) 顺序探测 _TDX_SERVERS，对 probe 通过者再 _validate 真实取数，取第一个验活成功的；
      2) 全部失败 → 回退 mootdx 自带 bestip 测速选优（同样验活）；
      3) 再回退裸 factory（老用户 config 已有可用 BESTIP 时成立）；
      4) 仍失败 → 抛 RuntimeError，明确报错而非静默返回空表 / 崩溃。
    """
    for ip, port in _TDX_SERVERS:
        if not _probe(ip, port):
            continue
        try:
            c = Quotes.factory(market=market, server=(ip, port))
            if _validate(c, market):
                return c
        except Exception:
            continue
    for kwargs in ({'bestip': True}, {}):
        try:
            c = Quotes.factory(market=market, **kwargs)
            if _validate(c, market):
                return c
        except Exception:
            continue
    raise RuntimeError('所有 mootdx 服务器均无法取到数据（TCP 可达但返回空 / 被 reset）。海外网络通常全部超时（TCP 7709），请走国内代理或更新 _TDX_SERVERS 列表。')
SH_INDEX = {'000300', '000905', '000016', '000688', '000852', '000010'}

def get_prefix(code: str) -> str:
    """6位代码 → 市场前缀（sh/sz/bj）。支持显式前缀 sh/sz/bj 透传以解决歧义。"""
    c = code.lower()
    if c.startswith(('sh', 'sz', 'bj')):
        return c[:2]
    if c.startswith('92'):
        return 'bj'
    if c.startswith(('5', '6', '9')):
        return 'sh'
    if c.startswith(('4', '8')):
        return 'bj'
    if c in SH_INDEX:
        return 'sh'
    return 'sz'
import re
_TICKER_RE = re.compile('^(?:(sh|sz|bj)(\\d{6})|(\\d{6})(?:\\.(sh|sz|bj))?)$', re.IGNORECASE)

def _natural_market(digits: str) -> str:
    """6 位码的自然归属市场。仅用于校验显式前缀是否自相矛盾。
    注意 000xxx 是沪指数/深个股共用的歧义段，由调用处单独处理，不走这里。"""
    if digits.startswith('92') or digits[:2] in ('43', '83', '87'):
        return 'bj'
    if digits[0] in ('5', '6', '9'):
        return 'sh'
    return 'sz'

def norm_ticker(code: str, stock_only: bool=False) -> str:
    """任意受支持写法 → 纯 6 位数字代码。

    支持 600519 / SH600519 / sh600519 / 600519.SH / BJ920982 等。
    stock_only=True：个股专用接口（研报、一致预期等）传这个，会拒绝显式指数写法。
    ⚠️ 不匹配时**抛 ValueError，绝不静默返回空串或猜一个代码**——
    否则调用方会把「代码格式写错」误读成「这只票没有数据」，
    或者更糟：拿到另一只股票的数据还以为是对的。
    """
    raw = str(code).strip()
    m = _TICKER_RE.match(raw)
    if not m:
        raise ValueError(f'无法把 {code!r} 解析为 6 位股票代码；支持格式：600519 / SH600519 / sh600519 / 600519.SH（前缀与后缀二选一，不能同时写）')
    digits = m.group(2) or m.group(3)
    market = (m.group(1) or m.group(4) or '').lower()
    if market:
        if digits.startswith('000'):
            if market == 'bj':
                raise ValueError(f'{code!r} 市场标识与号段矛盾：000xxx 不属北交所。')
            if stock_only and market == 'sh':
                raise ValueError(f'{code!r} 指向沪市指数而非个股（沪市无 000xxx 个股），本接口只服务个股。要查同号段的深市个股请显式传 sz{digits}。')
        else:
            nat = _natural_market(digits)
            if market != nat:
                raise ValueError(f'{code!r} 的市场标识与号段矛盾：{digits} 属 {nat} 市，而不是 {market} 市。（改用 {nat}{digits} 或去掉市场标识）')
    return digits
import time
import random
import requests
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
DATACENTER_URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
EM_SESSION = requests.Session()
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def em_get(url: str, params: dict | None=None, headers: dict | None=None, timeout: int=15, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA。
    所有 eastmoney.com 接口都应通过它请求，避免高频被封 IP。"""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()

def eastmoney_datacenter(report_name: str, columns: str='ALL', filter_str: str='', page_size: int=50, sort_columns: str='', sort_types: str='-1') -> list[dict]:
    """东财数据中心统一查询 — 龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 共用（已内置限流）"""
    params = {'reportName': report_name, 'columns': columns, 'filter': filter_str, 'pageNumber': '1', 'pageSize': str(page_size), 'sortColumns': sort_columns, 'sortTypes': sort_types, 'source': 'WEB', 'client': 'WEB'}
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get('result') and d['result'].get('data'):
        return d['result']['data']
    return []
from mootdx.quotes import Quotes
import urllib.request

def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """
    批量拉取腾讯财经实时行情。
    codes: ["688017", "300476", "002463"]
    也支持指数: ["000001", "000300", "399006"]
    也支持ETF: ["510050", "510300"]
    返回: {code: {name, price, pe_ttm, pb, mcap, ...}}
    """
    SH_INDEX = {'000300', '000905', '000016', '000688', '000852', '000010'}
    prefixed = []
    key_of = {}
    for c in codes:
        low = c.lower()
        if low.startswith(('sh', 'sz', 'bj')):
            p = low
        elif c.startswith('92'):
            p = f'bj{c}'
        elif c in SH_INDEX or c.startswith(('5', '6', '9')):
            p = f'sh{c}'
        elif c.startswith(('4', '8')):
            p = f'bj{c}'
        else:
            p = f'sz{c}'
        prefixed.append(p)
        key_of[p] = c
    url = 'https://qt.gtimg.cn/q=' + ','.join(prefixed)
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode('gbk')
    result = {}
    for line in data.strip().split(';'):
        if not line.strip() or '=' not in line or '"' not in line:
            continue
        key = line.split('=')[0].split('_')[-1]
        vals = line.split('"')[1].split('~')
        if len(vals) < 53:
            continue
        code = key_of.get(key, key[2:])
        result[code] = {'name': vals[1], 'price': float(vals[3]) if vals[3] else 0, 'last_close': float(vals[4]) if vals[4] else 0, 'open': float(vals[5]) if vals[5] else 0, 'change_amt': float(vals[31]) if vals[31] else 0, 'change_pct': float(vals[32]) if vals[32] else 0, 'high': float(vals[33]) if vals[33] else 0, 'low': float(vals[34]) if vals[34] else 0, 'amount_wan': float(vals[37]) if vals[37] else 0, 'turnover_pct': float(vals[38]) if vals[38] else 0, 'pe_ttm': float(vals[39]) if vals[39] else 0, 'amplitude_pct': float(vals[43]) if vals[43] else 0, 'float_mcap_yi': float(vals[44]) if vals[44] else 0, 'mcap_yi': float(vals[45]) if vals[45] else 0, 'pb': float(vals[46]) if vals[46] else 0, 'limit_up': float(vals[47]) if vals[47] else 0, 'limit_down': float(vals[48]) if vals[48] else 0, 'vol_ratio': float(vals[49]) if vals[49] else 0, 'pe_static': float(vals[52]) if vals[52] else 0}
        q = result[code]
        q['is_stale'] = q['amount_wan'] == 0 and q['price'] == q['last_close'] and (q['price'] > 0)
        if q['is_stale'] and key[2:4] in ('43', '83', '87'):
            q['stale_reason'] = '北交所老号段，多数已迁至 920xxx，请按名称反查现行代码'
        elif q['is_stale']:
            q['stale_reason'] = '成交量为 0（停牌 / 未开盘 / 废码），报价非当日真实成交'
    return result
import requests

def baidu_kline_with_ma(code: str, start_time: str='') -> dict:
    """百度股市通K线 — 独有能力: 返回时自带 ma5/ma10/ma20 均价"""
    url = 'https://finance.pae.baidu.com/selfselect/getstockquotation'
    params = {'all': '1', 'isIndex': 'false', 'isBk': 'false', 'isBlock': 'false', 'isFutures': 'false', 'isStock': 'true', 'newFormat': '1', 'group': 'quotation_kline_ab', 'finClientType': 'pc', 'code': code, 'start_time': start_time, 'ktype': '1'}
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/vnd.finance-web.v1+json', 'Origin': 'https://gushitong.baidu.com', 'Referer': 'https://gushitong.baidu.com/'}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json()
    result = d.get('Result', {})
    md = result.get('newMarketData', {})
    keys = md.get('keys', [])
    rows = md.get('marketData', '').split(';')
    return {'keys': keys, 'rows': rows}
import requests
import re
import time
from datetime import date, timedelta
from pathlib import Path
REPORT_API = 'https://reportapi.eastmoney.com/report/list'
PDF_TPL = 'https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'

def eastmoney_reports(code: str, max_pages: int=5) -> list[dict]:
    """拉取指定股票的研报列表。

    code 支持 600519 / SH600519 / 600519.SH 等写法（内部归一化为纯 6 位）。
    ⚠️ reportapi 只认纯 6 位数字：传 "SH600519" 会返回 hits=0，
       看起来像「这只票没研报」，实际是格式没归一化——务必先过 norm_ticker()。
    返回 [] 仅表示东财确无该标的研报覆盖（格式错误已在上游抛 ValueError）。
    """
    code = norm_ticker(code, stock_only=True)
    all_records = []
    for page in range(1, max_pages + 1):
        params = {'industryCode': '*', 'pageSize': '100', 'industry': '*', 'rating': '*', 'ratingChange': '*', 'beginTime': '2000-01-01', 'endTime': '2030-01-01', 'pageNo': str(page), 'fields': '', 'qType': '0', 'orgCode': '', 'code': code, 'rcode': '', 'p': str(page), 'pageNum': str(page), 'pageNumber': str(page)}
        r = em_get(REPORT_API, params=params, headers={'Referer': 'https://data.eastmoney.com/'}, timeout=30)
        d = r.json()
        rows = d.get('data') or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (d.get('TotalPage', 1) or 1):
            break
    if not all_records and code[:2] in ('43', '83', '87'):
        raise ValueError(f'{code} 属北交所老号段（43/83/87），东财研报库已不再按老码索引。北交所存量标的已基本迁至 920xxx（如 832982→920982）；请按股票名称反查现行 920 代码后重试。详见「北交所老号段」警告。')
    return all_records

def download_pdf(record: dict, target_dir: str='./reports') -> str | None:
    """下载单份研报PDF，返回保存路径或None"""
    info_code = record.get('infoCode', '')
    if not info_code:
        return None
    date = (record.get('publishDate') or '')[:10]
    org = re.sub('[\\\\/:*?"<>|]', '_', record.get('orgSName') or '未知')[:40]
    title = re.sub('[\\\\/:*?"<>|]', '_', record.get('title', ''))[:80]
    fname = f'{date}_{org}_{title}.pdf'
    target = Path(target_dir) / fname
    if target.exists():
        return str(target)
    url = PDF_TPL.format(info_code=info_code)
    r = em_get(url, headers={'Referer': 'https://data.eastmoney.com/'}, timeout=60)
    if r.status_code == 200 and len(r.content) >= 1024:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(r.content)
        return str(target)
    return None
from datetime import date, timedelta

def eastmoney_industry_reports(industry_code: str='*', max_pages: int=5, begin: str='') -> list[dict]:
    """拉取行业研报列表（qType=1）。
    industry_code="*" = 全行业；传东财行业码（如 "1238"=IT服务Ⅱ）= 单行业。
    行业名 / 行业码在每条 record 的 industryName / industryCode 字段。
    begin 留空 = 近两年（相对今天算，避免硬编码日期越用越旧）。"""
    if not begin:
        begin = (date.today() - timedelta(days=730)).isoformat()
    all_records = []
    for page in range(1, max_pages + 1):
        params = {'industryCode': industry_code, 'pageSize': '100', 'industry': '*', 'rating': '*', 'ratingChange': '*', 'beginTime': begin, 'endTime': '2030-01-01', 'pageNo': str(page), 'fields': '', 'qType': '1'}
        r = em_get(REPORT_API, params=params, headers={'Referer': 'https://data.eastmoney.com/'}, timeout=30)
        d = r.json()
        rows = d.get('data') or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (d.get('TotalPage', 1) or 1):
            break
    return all_records
import requests
import pandas as pd
from io import StringIO

def ths_eps_forecast(code: str) -> pd.DataFrame:
    """
    同花顺机构一致预期EPS。
    直连 basic.10jqka.com.cn，解析HTML表格。
    code 支持 688017 / SH688017 / 688017.SH 等写法（内部归一化为纯 6 位）。
    返回 DataFrame: 年度, 预测机构数, 最小值, 均值, 最大值
    "均值" = 机构一致预期EPS
    """
    code = norm_ticker(code, stock_only=True)
    url = f'https://basic.10jqka.com.cn/new/{code}/worth.html'
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36', 'Referer': 'https://basic.10jqka.com.cn/'}
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = 'gbk'
    dfs = pd.read_html(StringIO(r.text))
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any(('每股收益' in c or '均值' in c for c in cols)):
            return df
    return dfs[0] if dfs else pd.DataFrame()
import os
import json
import secrets
import requests

def _claw_headers(call_type: str='normal') -> dict:
    """SkillHub 2.0 必须的 X-Claw 鉴权头"""
    return {'X-Claw-Call-Type': call_type, 'X-Claw-Skill-Id': 'report-search', 'X-Claw-Skill-Version': '2.0.0', 'X-Claw-Plugin-Id': 'none', 'X-Claw-Plugin-Version': 'none', 'X-Claw-Trace-Id': secrets.token_hex(32)}

def iwencai_search(query: str, channel: str='report', size: int=50) -> list[dict]:
    """
    iwencai 语义搜索。
    channel: "report"(研报) / "announcement"(公告) / "news"(新闻)
    size: 默认10, 实测可调到50（隐藏参数）
    """
    headers = {'Authorization': f'Bearer {IWENCAI_KEY}', 'Content-Type': 'application/json', **_claw_headers()}
    payload = {'channels': [channel], 'app_id': 'AIME_SKILL', 'query': query, 'size': size}
    r = requests.post(f'{IWENCAI_BASE}/v1/comprehensive/search', json=payload, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'iwencai HTTP {r.status_code}: {r.text[:200]}')
    data = r.json()
    if data.get('status_code', 0) != 0:
        raise RuntimeError(f'iwencai error: {data.get('status_msg', '')}')
    return data.get('data') or []

def iwencai_query(query: str, page: int=1, limit: int=50) -> list[dict]:
    """
    iwencai NL数据查询（结构化字段）。
    例: "贵州茅台 ROE" → DataFrame-like rows
    """
    headers = {'Authorization': f'Bearer {IWENCAI_KEY}', 'Content-Type': 'application/json', **_claw_headers()}
    payload = {'query': query, 'page': str(page), 'limit': str(limit), 'is_cache': '1', 'expand_index': 'true'}
    r = requests.post(f'{IWENCAI_BASE}/v1/query2data', json=payload, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'iwencai HTTP {r.status_code}: {r.text[:200]}')
    data = r.json()
    if data.get('status_code', 0) != 0:
        raise RuntimeError(f'iwencai error: {data.get('status_msg', '')}')
    return data.get('datas') or []

def dedup_articles(articles: list[dict]) -> list[dict]:
    """同一uid仅保留score最高的段落"""
    best = {}
    for a in articles:
        uid = a.get('uid', '') or f'{a.get('title', '')}|{a.get('publish_date', '')}'
        score = float(a.get('score', 0))
        if uid not in best or score > float(best[uid].get('score', 0)):
            best[uid] = a
    return sorted(best.values(), key=lambda x: x.get('publish_date', ''), reverse=True)
import requests
import pandas as pd

def ths_hot_reason(date: str=None) -> pd.DataFrame:
    """
    同花顺当日强势股归因。
    date: 'YYYY-MM-DD' 格式，None=今天
    返回 DataFrame，含每只股票的题材标签 (reason)。

    实测: 73ms 拿到 ~125 只 + 完整字段
    """
    from datetime import date as _date
    if date is None:
        date = _date.today().strftime('%Y-%m-%d')
    url = f'http://zx.10jqka.com.cn/event/api/getharden/date/{date}/orderby/date/orderway/desc/charset/GBK/'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36'}
    r = requests.get(url, headers=headers, timeout=10)
    data = r.json()
    if data.get('errocode', 0) != 0:
        raise RuntimeError(f'同花顺热点错误: {data.get('errormsg', '')}')
    rows = data.get('data') or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    rename_map = {'name': '名称', 'code': '代码', 'reason': '题材归因', 'close': '收盘价', 'zhangdie': '涨跌额', 'zhangfu': '涨幅%', 'huanshou': '换手率%', 'chengjiaoe': '成交额', 'chengjiaoliang': '成交量', 'ddejingliang': '大单净量', 'market': '市场'}
    df = df.rename(columns=rename_map)
    return df
import requests
import pandas as pd
from pathlib import Path
HSGT_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36', 'Host': 'data.hexin.cn', 'Referer': 'https://data.hexin.cn/'}

def hsgt_realtime() -> pd.DataFrame:
    """
    沪深股通当日实时分钟流向（含集合竞价 09:10–15:00，262 个时间点）。
    返回字段: time, hgt(沪股通累计净买入), sgt(深股通累计净买入)
    单位: 亿元
    """
    url = 'https://data.hexin.cn/market/hsgtApi/method/dayChart/'
    r = requests.get(url, headers=HSGT_HEADERS, timeout=10)
    d = r.json()
    times = d.get('time', [])
    hgt = d.get('hgt', [])
    sgt = d.get('sgt', [])
    n = len(times)
    return pd.DataFrame({'time': times, 'hgt_yi': hgt[:n] + [None] * (n - len(hgt)), 'sgt_yi': sgt[:n] + [None] * (n - len(sgt))})

def _northbound_cache_path() -> Path:
    """北向资金本地 CSV 缓存路径"""
    p = Path.home() / '.tradingagents' / 'cache' / 'northbound_daily.csv'
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _save_northbound_snapshot(date: str, hgt: float, sgt: float):
    """写入/更新当天北向收盘数据到 CSV"""
    path = _northbound_cache_path()
    rows = {}
    if path.exists():
        for line in path.read_text().strip().split('\n')[1:]:
            parts = line.split(',')
            if len(parts) == 3:
                rows[parts[0]] = line
    rows[date] = f'{date},{hgt},{sgt}'
    with open(path, 'w') as f:
        f.write('date,hgt,sgt\n')
        for d in sorted(rows.keys()):
            f.write(rows[d] + '\n')

def _load_northbound_history(n: int=20) -> pd.DataFrame:
    """读取最近 N 天北向历史"""
    path = _northbound_cache_path()
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df.tail(n)

def eastmoney_concept_blocks(code: str) -> dict:
    """
    个股所属板块/概念归属（东财 slist，一次请求拿全，已内置限流）。
    返回: {total, boards: [{name, code(BK码), change_pct, lead_stock}], concept_tags: [板块名...]}
    boards 混合 行业/概念/地域，板块名自解释；concept_tags 是所有板块名的便捷列表。
    """
    market_code = 1 if code.startswith('6') else 0
    params = {'fltt': '2', 'invt': '2', 'secid': f'{market_code}.{code}', 'spt': '3', 'pi': '0', 'pz': '200', 'po': '1', 'fields': 'f12,f14,f3,f128'}
    headers = {'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}
    try:
        r = em_get('https://push2.eastmoney.com/api/qt/slist/get', params=params, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
        print(f'[WARN] 东财板块归属请求失败: {e}')
        return {'total': 0, 'boards': [], 'concept_tags': []}
    diff = (d.get('data') or {}).get('diff') or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = []
    for it in items:
        boards.append({'name': it.get('f14', ''), 'code': it.get('f12', ''), 'change_pct': it.get('f3', ''), 'lead_stock': it.get('f128', '')})
    return {'total': len(boards), 'boards': boards, 'concept_tags': [b['name'] for b in boards]}
import requests

def eastmoney_fund_flow_minute(code: str) -> list[dict]:
    """
    个股资金流向（分钟级，当日盘中）。
    code: 6位股票代码
    返回: [{time, main_net, small_net, mid_net, large_net, super_net}, ...]
    单位: 元
    """
    secid = f'1.{code}' if code.startswith('6') else f'0.{code}'
    url = 'https://push2.eastmoney.com/api/qt/stock/fflow/kline/get'
    params = {'secid': secid, 'klt': 1, 'fields1': 'f1,f2,f3,f7', 'fields2': 'f51,f52,f53,f54,f55,f56,f57'}
    headers = {'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/', 'Origin': 'https://quote.eastmoney.com'}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
    except Exception as e:
        print(f'[WARN] push2 资金流请求失败: {e}')
        return []
    rows = []
    for line in d.get('data', {}).get('klines', []):
        parts = line.split(',')
        if len(parts) >= 6:
            rows.append({'time': parts[0], 'main_net': float(parts[1]), 'small_net': float(parts[2]), 'mid_net': float(parts[3]), 'large_net': float(parts[4]), 'super_net': float(parts[5])})
    return rows
import requests
from datetime import datetime, timedelta

def dragon_tiger_board(code: str, trade_date: str, look_back: int=30) -> dict:
    """
    龙虎榜数据聚合。
    trade_date: YYYY-MM-DD
    look_back: 回看天数
    返回: {records: [...], seats: {buy: [...], sell: [...]}, institution: {...}}
    """
    start = datetime.strptime(trade_date, '%Y-%m-%d') - timedelta(days=look_back)
    start_str = start.strftime('%Y-%m-%d')
    records = []
    data = eastmoney_datacenter('RPT_DAILYBILLBOARD_DETAILSNEW', filter_str=f'''(TRADE_DATE>='{start_str}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE="{code}")''', page_size=50, sort_columns='TRADE_DATE', sort_types='-1')
    for row in data:
        records.append({'date': str(row.get('TRADE_DATE', ''))[:10], 'reason': row.get('EXPLANATION', ''), 'net_buy': round((row.get('BILLBOARD_NET_AMT') or 0) / 10000, 1), 'turnover': round(float(row.get('TURNOVERRATE') or 0), 2)})
    buy_data, sell_data = ([], [])
    seats = {'buy': [], 'sell': []}
    if records:
        latest_date = records[0]['date']
        buy_data = eastmoney_datacenter('RPT_BILLBOARD_DAILYDETAILSBUY', filter_str=f'''(TRADE_DATE='{latest_date}')(SECURITY_CODE="{code}")''', page_size=10, sort_columns='BUY', sort_types='-1')
        for row in buy_data[:5]:
            seats['buy'].append({'name': row.get('OPERATEDEPT_NAME', ''), 'buy_amt': round((row.get('BUY') or 0) / 10000, 1), 'sell_amt': round((row.get('SELL') or 0) / 10000, 1), 'net': round((row.get('NET') or 0) / 10000, 1)})
        sell_data = eastmoney_datacenter('RPT_BILLBOARD_DAILYDETAILSSELL', filter_str=f'''(TRADE_DATE='{latest_date}')(SECURITY_CODE="{code}")''', page_size=10, sort_columns='SELL', sort_types='-1')
        for row in sell_data[:5]:
            seats['sell'].append({'name': row.get('OPERATEDEPT_NAME', ''), 'buy_amt': round((row.get('BUY') or 0) / 10000, 1), 'sell_amt': round((row.get('SELL') or 0) / 10000, 1), 'net': round((row.get('NET') or 0) / 10000, 1)})
    institution = {'buy_amt': 0, 'sell_amt': 0, 'net_amt': 0}
    for detail_data, side in [(buy_data, 'buy'), (sell_data, 'sell')]:
        for row in detail_data:
            if str(row.get('OPERATEDEPT_CODE', '')) == '0':
                amt = row.get('BUY') or 0 if side == 'buy' else row.get('SELL') or 0
                if side == 'buy':
                    institution['buy_amt'] += amt
                else:
                    institution['sell_amt'] += amt
    institution['buy_amt'] = round(institution['buy_amt'] / 10000, 1)
    institution['sell_amt'] = round(institution['sell_amt'] / 10000, 1)
    institution['net_amt'] = round(institution['buy_amt'] - institution['sell_amt'], 1)
    return {'records': records, 'seats': seats, 'institution': institution}
from datetime import datetime, timedelta

def lockup_expiry(code: str, trade_date: str, forward_days: int=90) -> dict:
    """
    限售解禁日历。
    返回: {history: [...], upcoming: [...]}
    """
    history_data = eastmoney_datacenter('RPT_LIFT_STAGE', filter_str=f'(SECURITY_CODE="{code}")', page_size=15, sort_columns='FREE_DATE', sort_types='-1')
    history = []
    for row in history_data:
        history.append({'date': str(row.get('FREE_DATE', ''))[:10], 'type': row.get('FREE_SHARES_TYPE', ''), 'shares': row.get('FREE_SHARES', 0), 'able_shares': row.get('ABLE_FREE_SHARES', 0), 'ratio': row.get('FREE_RATIO', 0)})
    end_date = datetime.strptime(trade_date, '%Y-%m-%d') + timedelta(days=forward_days)
    end_str = end_date.strftime('%Y-%m-%d')
    upcoming_data = eastmoney_datacenter('RPT_LIFT_STAGE', filter_str=f"""(SECURITY_CODE="{code}")(FREE_DATE>='{trade_date}')(FREE_DATE<='{end_str}')""", page_size=20, sort_columns='FREE_DATE', sort_types='1')
    upcoming = []
    for row in upcoming_data:
        upcoming.append({'date': str(row.get('FREE_DATE', ''))[:10], 'type': row.get('FREE_SHARES_TYPE', ''), 'shares': row.get('FREE_SHARES', 0), 'able_shares': row.get('ABLE_FREE_SHARES', 0), 'ratio': row.get('FREE_RATIO', 0)})
    return {'history': history, 'upcoming': upcoming}
import requests

def industry_comparison(top_n: int=20) -> dict:
    """
    全行业涨跌幅排名（东财行业板块，~100 个行业）。
    返回: {top: [...], bottom: [...], total: int}
    """
    url = 'https://push2.eastmoney.com/api/qt/clist/get'
    params = {'pn': '1', 'pz': '100', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2', 'fid': 'f3', 'fs': 'm:90+t:2', 'fields': 'f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207'}
    headers = {'User-Agent': UA}
    r = em_get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    items = d.get('data', {}).get('diff', [])
    if not items:
        return {'top': [], 'bottom': [], 'total': 0}
    rows = []
    for i, item in enumerate(items):
        rows.append({'rank': i + 1, 'name': item.get('f14', ''), 'change_pct': item.get('f3', 0), 'code': item.get('f12', ''), 'up_count': item.get('f104', 0), 'down_count': item.get('f105', 0), 'leader': item.get('f140', ''), 'leader_change': item.get('f136', 0)})
    return {'top': rows[:top_n], 'bottom': rows[-top_n:], 'total': len(rows)}
import requests
_BOARD_FS = {'industry': 'm:90+t:2', 'concept': 'm:90+t:3', 'region': 'm:90+t:1'}
_BOARD_PERIOD = {'today': ('f62', 'f62', 'f184', 'f3', 'f204'), '5d': ('f164', 'f164', 'f165', 'f109', 'f257'), '10d': ('f174', 'f174', 'f175', 'f160', None)}

def board_fund_flow(board_type: str='industry', period: str='today', top_n: int=20) -> dict:
    """
    板块资金流向排名（按主力净流入降序）。
    board_type: industry(行业) / concept(概念) / region(地域)
    period:     today(今日) / 5d(5日) / 10d(10日)
    返回: {board_type, period, total, rows:[{rank, name, code, change_pct,
           main_net(主力净额,元), main_pct(主力净占比,%), leader(领涨股),
           # 仅 today：super_large_net/large_net/medium_net/small_net(超大/大/中/小单净额,元)}]}
    注：板块级只有 今日/5日/10日（无 3日，个股级才有）。主力净额 = 超大单 + 大单。
    """
    if board_type not in _BOARD_FS:
        raise ValueError(f'board_type 须为 {list(_BOARD_FS)}')
    if period not in _BOARD_PERIOD:
        raise ValueError(f'period 须为 {list(_BOARD_PERIOD)}')
    fid, f_main, f_pct, f_chg, f_leader = _BOARD_PERIOD[period]
    fields = ['f12', 'f14', f_chg, f_main, f_pct]
    if f_leader:
        fields.append(f_leader)
    if period == 'today':
        fields += ['f66', 'f72', 'f78', 'f84']
    url = 'https://push2.eastmoney.com/api/qt/clist/get'
    base = {'pz': '200', 'po': '1', 'np': '1', 'fltt': '2', 'invt': '2', 'fid': fid, 'fs': _BOARD_FS[board_type], 'fields': ','.join(dict.fromkeys(fields))}

    def _page(pn: int):
        r = em_get(url, params={**base, 'pn': str(pn)}, headers={'User-Agent': UA}, timeout=15)
        d = r.json().get('data') or {}
        return (d.get('diff') or [], int(d.get('total') or 0))
    _PAGE = 200
    items, total = _page(1)
    pn = 2
    while len(items) < top_n:
        if total and len(items) >= total:
            break
        more, _ = _page(pn)
        if not more:
            break
        items += more
        pn += 1
        if len(more) < _PAGE:
            break
    total = max(total, len(items))
    rows = []
    for i, it in enumerate(items):
        row = {'rank': i + 1, 'name': it.get('f14', ''), 'code': it.get('f12', ''), 'change_pct': it.get(f_chg, 0), 'main_net': it.get(f_main, 0), 'main_pct': it.get(f_pct, 0), 'leader': it.get(f_leader, '') if f_leader else ''}
        if period == 'today':
            row.update({'super_large_net': it.get('f66', 0), 'large_net': it.get('f72', 0), 'medium_net': it.get('f78', 0), 'small_net': it.get('f84', 0)})
        rows.append(row)
    return {'board_type': board_type, 'period': period, 'total': total, 'rows': rows[:top_n]}
from datetime import datetime

def daily_dragon_tiger(trade_date: str=None, min_net_buy: float=None) -> dict:
    """
    全市场龙虎榜。
    trade_date: YYYY-MM-DD（默认当日）
    min_net_buy: 净买入下限（万元），None 不过滤
    返回: {date, total_records, stocks: [{code, name, reason, close, change_pct,
           net_buy_wan, buy_wan, sell_wan, turnover_pct}]}
    """
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y-%m-%d')
    data = eastmoney_datacenter('RPT_DAILYBILLBOARD_DETAILSNEW', filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')", page_size=500, sort_columns='BILLBOARD_NET_AMT', sort_types='-1')
    if not data:
        return {'date': trade_date, 'total_records': 0, 'stocks': [], 'note': '无数据（非交易日或盘后未更新）'}
    actual_date = str(data[0].get('TRADE_DATE', ''))[:10] if data else trade_date
    stocks = []
    for row in data:
        net_buy = (row.get('BILLBOARD_NET_AMT') or 0) / 10000
        if min_net_buy is not None and net_buy < min_net_buy:
            continue
        stocks.append({'code': row.get('SECURITY_CODE', ''), 'name': row.get('SECURITY_NAME_ABBR', ''), 'reason': row.get('EXPLANATION', ''), 'close': row.get('CLOSE_PRICE') or 0, 'change_pct': round(float(row.get('CHANGE_RATE') or 0), 2), 'net_buy_wan': round(net_buy, 1), 'buy_wan': round((row.get('BILLBOARD_BUY_AMT') or 0) / 10000, 1), 'sell_wan': round((row.get('BILLBOARD_SELL_AMT') or 0) / 10000, 1), 'turnover_pct': round(float(row.get('TURNOVERRATE') or 0), 2)})
    return {'date': actual_date, 'total_records': len(stocks), 'stocks': stocks}
from collections import Counter

def margin_trading(code: str, page_size: int=30) -> list[dict]:
    """
    融资融券明细（日级）。
    返回: [{date, rzye(融资余额), rzmre(融资买入), rqye(融券余额), ...}]
    """
    data = eastmoney_datacenter('RPTA_WEB_RZRQ_GGMX', filter_str=f'(SCODE="{code}")', page_size=page_size, sort_columns='DATE', sort_types='-1')
    rows = []
    for row in data:
        rows.append({'date': str(row.get('DATE', ''))[:10], 'rzye': row.get('RZYE', 0), 'rzmre': row.get('RZMRE', 0), 'rzche': row.get('RZCHE', 0), 'rqye': row.get('RQYE', 0), 'rqmcl': row.get('RQMCL', 0), 'rqchl': row.get('RQCHL', 0), 'rzrqye': row.get('RZRQYE', 0)})
    return rows

def block_trade(code: str, page_size: int=20) -> list[dict]:
    """
    大宗交易记录。
    返回: [{date, price, vol, amount, buyer, seller, premium_pct}]
    """
    data = eastmoney_datacenter('RPT_DATA_BLOCKTRADE', filter_str=f'(SECURITY_CODE="{code}")', page_size=page_size, sort_columns='TRADE_DATE', sort_types='-1')
    rows = []
    for row in data:
        close = row.get('CLOSE_PRICE') or 0
        deal_price = row.get('DEAL_PRICE') or 0
        premium = (deal_price / close - 1) * 100 if close else 0
        rows.append({'date': str(row.get('TRADE_DATE', ''))[:10], 'price': deal_price, 'close': close, 'premium_pct': round(premium, 2), 'vol': row.get('DEAL_VOLUME', 0), 'amount': row.get('DEAL_AMT', 0), 'buyer': row.get('BUYER_NAME', ''), 'seller': row.get('SELLER_NAME', '')})
    return rows

def holder_num_change(code: str, page_size: int=10) -> list[dict]:
    """
    股东户数变化（季度级）。
    返回: [{date, holder_num, change_num, change_ratio, avg_shares}]
    """
    data = eastmoney_datacenter('RPT_HOLDERNUMLATEST', filter_str=f'(SECURITY_CODE="{code}")', page_size=page_size, sort_columns='END_DATE', sort_types='-1')
    rows = []
    for row in data:
        rows.append({'date': str(row.get('END_DATE', ''))[:10], 'holder_num': row.get('HOLDER_NUM', 0), 'change_num': row.get('HOLDER_NUM_CHANGE', 0), 'change_ratio': row.get('HOLDER_NUM_RATIO', 0), 'avg_shares': row.get('AVG_FREE_SHARES', 0)})
    return rows

def dividend_history(code: str, page_size: int=20) -> list[dict]:
    """
    分红送转历史。
    返回: [{date, bonus_rmb(每股派息), transfer_ratio(转增比例), bonus_ratio(送股比例)}]
    """
    data = eastmoney_datacenter('RPT_SHAREBONUS_DET', filter_str=f'(SECURITY_CODE="{code}")', page_size=page_size, sort_columns='EX_DIVIDEND_DATE', sort_types='-1')
    rows = []
    for row in data:
        rows.append({'date': str(row.get('EX_DIVIDEND_DATE', ''))[:10], 'bonus_rmb': row.get('PRETAX_BONUS_RMB', 0), 'transfer_ratio': row.get('TRANSFER_RATIO', 0), 'bonus_ratio': row.get('BONUS_RATIO', 0), 'plan': row.get('ASSIGN_PROGRESS', '')})
    return rows
import requests

def stock_fund_flow_120d(code: str) -> list[dict]:
    """
    个股资金流（日级，最近120个交易日）。
    返回: [{date, main_net(主力净流入), small_net, mid_net, large_net, super_net}]
    单位: 元
    """
    market_code = 1 if code.startswith('6') else 0
    url = 'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get'
    params = {'secid': f'{market_code}.{code}', 'fields1': 'f1,f2,f3,f7', 'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65', 'lmt': '120'}
    headers = {'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/', 'Origin': 'https://quote.eastmoney.com'}
    try:
        r = em_get(url, params=params, headers=headers, timeout=15)
        d = r.json()
    except Exception as e:
        print(f'[WARN] push2 资金流请求失败: {e}')
        return []
    klines = d.get('data', {}).get('klines', [])
    rows = []
    for line in klines:
        parts = line.split(',')
        if len(parts) >= 7:
            rows.append({'date': parts[0], 'main_net': float(parts[1]) if parts[1] != '-' else 0, 'small_net': float(parts[2]) if parts[2] != '-' else 0, 'mid_net': float(parts[3]) if parts[3] != '-' else 0, 'large_net': float(parts[4]) if parts[4] != '-' else 0, 'super_net': float(parts[5]) if parts[5] != '-' else 0})
    return rows
import requests
import re
import json

def eastmoney_stock_news(code: str, page_size: int=20) -> list[dict]:
    """
    东财个股新闻（JSONP 接口）。
    返回: [{title, content, time, source, url}]
    """
    cb = 'jQuery_news'
    url = 'https://search-api-web.eastmoney.com/search/jsonp'
    inner_params = json.dumps({'uid': '', 'keyword': code, 'type': ['cmsArticleWebOld'], 'client': 'web', 'clientType': 'web', 'clientVersion': 'curr', 'param': {'cmsArticleWebOld': {'searchScope': 'default', 'sort': 'default', 'pageIndex': 1, 'pageSize': page_size, 'preTag': '', 'postTag': ''}}}, separators=(',', ':'))
    params = {'cb': cb, 'param': inner_params}
    headers = {'User-Agent': UA, 'Referer': 'https://so.eastmoney.com/'}
    r = em_get(url, params=params, headers=headers, timeout=15)
    text = r.text
    json_str = text[text.index('(') + 1:text.rindex(')')]
    d = json.loads(json_str)
    rows = []
    articles = d.get('result', {}).get('cmsArticleWebOld', []) or []
    for a in articles:
        rows.append({'title': re.sub('<[^>]+>', '', a.get('title', '')), 'content': re.sub('<[^>]+>', '', a.get('content', ''))[:200], 'time': a.get('date', ''), 'source': a.get('mediaName', ''), 'url': a.get('url', '')})
    return rows
import requests
import hashlib
from datetime import datetime

def cls_telegraph(page_size: int=50) -> list[dict]:
    """
    财联社电报（全市场实时快讯）。v1 API + 本地签名，零 key。
    返回: [{title, content, time}]  time 已转为 'YYYY-MM-DD HH:MM:SS'
    """
    params = {'appName': 'CailianpressWeb', 'os': 'web', 'sv': '7.7.5', 'last_time': '', 'refresh_type': '1', 'rn': str(page_size)}
    qs = '&'.join((f'{k}={params[k]}' for k in sorted(params)))
    sign = hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()
    url = f'https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}'
    headers = {'User-Agent': UA, 'Referer': 'https://www.cls.cn/'}
    r = requests.get(url, headers=headers, timeout=10)
    d = r.json()
    rows = []
    for item in d.get('data', {}).get('roll_data', []) or []:
        ts = item.get('ctime')
        t = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else ''
        rows.append({'title': item.get('title', '') or item.get('brief', ''), 'content': item.get('content', '') or item.get('brief', ''), 'time': t})
    return rows
import requests
import uuid

def eastmoney_global_news(page_size: int=50) -> list[dict]:
    """
    东方财富全球财经资讯（7x24 滚动）。
    返回: [{title, summary, time}]
    """
    url = 'https://np-weblist.eastmoney.com/comm/web/getFastNewsList'
    params = {'client': 'web', 'biz': 'web_724', 'fastColumn': '102', 'sortEnd': '', 'pageSize': str(page_size), 'req_trace': str(uuid.uuid4())}
    headers = {'User-Agent': UA, 'Referer': 'https://kuaixun.eastmoney.com/'}
    r = em_get(url, params=params, headers=headers, timeout=10)
    d = r.json()
    rows = []
    for item in d.get('data', {}).get('fastNewsList', []):
        rows.append({'title': item.get('title', ''), 'summary': item.get('summary', '')[:200], 'time': item.get('showTime', '')})
    return rows
from mootdx.quotes import Quotes
from mootdx.quotes import Quotes
import requests

def eastmoney_stock_info(code: str) -> dict:
    """
    东财个股基本面信息。
    返回: {code, name, industry, total_shares, float_shares, mcap, float_mcap, list_date}
    """
    market_code = 1 if code.startswith('6') else 0
    url = 'https://push2.eastmoney.com/api/qt/stock/get'
    params = {'fltt': '2', 'invt': '2', 'fields': 'f57,f58,f84,f85,f127,f116,f117,f189,f43', 'secid': f'{market_code}.{code}'}
    headers = {'User-Agent': UA}
    r = em_get(url, params=params, headers=headers, timeout=10)
    d = r.json().get('data', {})
    return {'code': d.get('f57', ''), 'name': d.get('f58', ''), 'industry': d.get('f127', ''), 'total_shares': d.get('f84', 0), 'float_shares': d.get('f85', 0), 'mcap': d.get('f116', 0), 'float_mcap': d.get('f117', 0), 'list_date': str(d.get('f189', '')), 'price': d.get('f43', 0)}
import requests

def sina_financial_report(code: str, report_type: str='lrb', num: int=8) -> list[dict]:
    """
    新浪财报三表。
    code: 6位代码
    report_type: "fzb"(资产负债表) / "lrb"(利润表) / "llb"(现金流量表)
    num: 取最近 N 期（默认 8 期）
    返回: 按报告期倒序的记录列表，每期一条 dict：
          {"报告期": "2026-03-31", "<科目>": "<值>", "<科目>_同比": <同比>, ...}
          （item_value 为新浪原始字符串数值，仅在有同比时附 "_同比" 键）
    """
    prefix = 'sh' if code.startswith('6') else 'sz'
    paper_code = f'{prefix}{code}'
    url = 'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022'
    params = {'paperCode': paper_code, 'source': report_type, 'type': '0', 'page': '1', 'num': str(num)}
    headers = {'User-Agent': UA}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    report_list = r.json().get('result', {}).get('data', {}).get('report_list', {}) or {}
    rows = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        obj = report_list[period]
        rec = {'报告期': f'{period[:4]}-{period[4:6]}-{period[6:8]}'}
        for it in obj.get('data', []) or []:
            title = it.get('item_title', '')
            if not title or it.get('item_value') is None:
                continue
            rec[title] = it.get('item_value')
            tongbi = it.get('item_tongbi')
            if tongbi not in (None, ''):
                rec[title + '_同比'] = tongbi
        rows.append(rec)
    return rows
import requests
from datetime import datetime

def _cninfo_ts_to_date(ts):
    """巨潮 announcementTime 返回 Unix 毫秒整数，需转换为日期字符串。"""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
    return str(ts)[:10] if ts else ''
_CNINFO_ORGID_MAP = {}

def _cninfo_orgid(code: str) -> str:
    """查股票真实 orgId。巨潮 orgId 并非统一 `gssx0{code}` 格式（如 601318→9900002221、
    601398→jjxt0000019、688017→9900041602），硬编码会导致大量股票（尤其 601xxx 段）
    返回 totalAnnouncement=0、查不到公告（#19）。优先动态查官方映射表，查不到再回退硬编码。"""
    global _CNINFO_ORGID_MAP
    if not _CNINFO_ORGID_MAP:
        try:
            r = requests.get('http://www.cninfo.com.cn/new/data/szse_stock.json', headers={'User-Agent': UA}, timeout=15)
            _CNINFO_ORGID_MAP = {s['code']: s['orgId'] for s in r.json().get('stockList', [])}
        except Exception as e:
            print(f'[WARN] 巨潮 orgId 映射表拉取失败，回退硬编码规则: {e}')
    org = _CNINFO_ORGID_MAP.get(code)
    if org:
        return org
    if code.startswith('6'):
        return f'gssh0{code}'
    elif code.startswith('8') or code.startswith('4'):
        return f'gsbj0{code}'
    return f'gssz0{code}'

def cninfo_announcements(code: str, page_size: int=30) -> list[dict]:
    """
    巨潮公告全文检索。
    返回: [{title, type, date, url}]
    """
    url = 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
    org_id = _cninfo_orgid(code)
    payload = {'stock': f'{code},{org_id}', 'tabName': 'fulltext', 'pageSize': str(page_size), 'pageNum': '1', 'column': '', 'category': '', 'plate': '', 'seDate': '', 'searchkey': '', 'secid': '', 'sortName': '', 'sortType': '', 'isHLtitle': 'true'}
    headers = {'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded', 'Referer': 'https://www.cninfo.com.cn/new/disclosure', 'Origin': 'https://www.cninfo.com.cn'}
    r = requests.post(url, data=payload, headers=headers, timeout=15)
    d = r.json()
    rows = []
    for item in d.get('announcements', []) or []:
        rows.append({'title': item.get('announcementTitle', ''), 'type': item.get('announcementTypeName', ''), 'date': _cninfo_ts_to_date(item.get('announcementTime')), 'url': f'https://www.cninfo.com.cn/new/disclosure/detail?annoId={item.get('announcementId', '')}'})
    return rows
from mootdx.quotes import Quotes
import requests
ZTB_UT = '7eea3edcaed734bea9cbfc24409ed989'

def _fmt_zt_time(t) -> str:
    """涨停板时间整数 → HH:MM:SS（92500 → 09:25:00）。"""
    s = str(t).zfill(6)
    return f'{s[0:2]}:{s[2:4]}:{s[4:6]}'

def _em_zt_api(endpoint: str, sort: str, date: str) -> list[dict]:
    """东财涨停板行情中心通用请求（push2ex，走 em_get 限流）。
    endpoint: getTopicZTPool / getTopicZBPool / getTopicDTPool / getYesterdayZTPool
    返回 data.pool 原始列表（data 为 null = 非交易日 / 参数错）。"""
    url = f'https://push2ex.eastmoney.com/{endpoint}'
    params = {'ut': ZTB_UT, 'dpt': 'wz.ztzt', 'Pageindex': 0, 'pagesize': 10000, 'sort': sort, 'date': date}
    headers = {'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        return (r.json().get('data') or {}).get('pool') or []
    except Exception as e:
        print(f'[WARN] 涨停板池 {endpoint} 请求失败: {e}')
        return []

def em_zt_pool(date: str) -> list[dict]:
    """涨停池。date=YYYYMMDD（交易日）。
    返回每只: code/name/price/pct/amount/float_cap/turnover/limit_days(连板数)/
    first_seal/last_seal(封板时间)/seal_fund(封板资金,元)/break_times(炸板次数)/
    industry/zt_stat(N天M板)"""
    out = []
    for p in _em_zt_api('getTopicZTPool', 'fbt:asc', date):
        out.append({'code': p['c'], 'name': p['n'], 'price': p['p'] / 1000, 'pct': round(p['zdp'], 2), 'amount': p['amount'], 'float_cap': p['ltsz'], 'turnover': round(p['hs'], 2), 'limit_days': p['lbc'], 'first_seal': _fmt_zt_time(p['fbt']), 'last_seal': _fmt_zt_time(p['lbt']), 'seal_fund': p['fund'], 'break_times': p['zbc'], 'industry': p.get('hybk', ''), 'zt_stat': f'{(p.get('zttj') or {}).get('days', '?')}天{(p.get('zttj') or {}).get('ct', '?')}板'})
    return out

def em_zb_pool(date: str) -> list[dict]:
    """炸板池（涨停后开板）。返回 code/name/price/limit_price(涨停价)/pct/turnover/
    first_seal/break_times/amplitude(振幅)/speed(涨速)/industry/zt_stat"""
    out = []
    for p in _em_zt_api('getTopicZBPool', 'fbt:asc', date):
        out.append({'code': p['c'], 'name': p['n'], 'price': p['p'] / 1000, 'limit_price': p['ztp'] / 1000, 'pct': round(p['zdp'], 2), 'turnover': round(p['hs'], 2), 'first_seal': _fmt_zt_time(p['fbt']), 'break_times': p['zbc'], 'amplitude': round(p['zf'], 2), 'speed': round(p['zs'], 2), 'industry': p.get('hybk', ''), 'zt_stat': f'{(p.get('zttj') or {}).get('days', '?')}天{(p.get('zttj') or {}).get('ct', '?')}板'})
    return out

def em_dt_pool(date: str) -> list[dict]:
    """跌停池。返回 code/name/price/pct/turnover/pe/seal_fund(封单资金)/last_seal/
    board_amount(板上成交额)/dt_days(连续跌停)/open_times(开板次数)/industry"""
    out = []
    for p in _em_zt_api('getTopicDTPool', 'fund:asc', date):
        out.append({'code': p['c'], 'name': p['n'], 'price': p['p'] / 1000, 'pct': round(p['zdp'], 2), 'turnover': round(p['hs'], 2), 'pe': p.get('pe'), 'seal_fund': p['fund'], 'last_seal': _fmt_zt_time(p['lbt']), 'board_amount': p.get('fba'), 'dt_days': p.get('days'), 'open_times': p.get('oc'), 'industry': p.get('hybk', '')})
    return out

def em_yzt_pool(date: str) -> list[dict]:
    """昨日涨停池（昨涨停今表现，算晋级率/赚钱效应）。返回 code/name/price/
    pct(今日涨幅)/turnover/amplitude/speed/y_first_seal(昨封板时间)/
    y_limit_days(昨连板)/industry/zt_stat"""
    out = []
    for p in _em_zt_api('getYesterdayZTPool', 'zs:desc', date):
        out.append({'code': p['c'], 'name': p['n'], 'price': p['p'] / 1000, 'pct': round(p['zdp'], 2), 'turnover': round(p['hs'], 2), 'amplitude': round(p['zf'], 2), 'speed': round(p['zs'], 2), 'y_first_seal': _fmt_zt_time(p['yfbt']), 'y_limit_days': p['ylbc'], 'industry': p.get('hybk', ''), 'zt_stat': f'{(p.get('zttj') or {}).get('days', '?')}天{(p.get('zttj') or {}).get('ct', '?')}板'})
    return out
from datetime import datetime

def ths_limit_up_pool(date: str) -> list[dict]:
    """同花顺涨停揭秘（涨停原因 + 封板质量增强源）。date=YYYYMMDD。
    返回每只: code/name/price/pct/reason(涨停原因题材)/board_type(换手板/一字板/T字板)/
    seal_rate(封板成功率,0~1)/break_times(炸板次数)/seal_amount(封单额,元)/
    high_days(几天几板)/first_time(首次涨停时间)/is_again(是否回封 0/1)"""
    url = 'https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool'
    params = {'page': 1, 'limit': 200, 'field': '199112,10,9001,330323,330324,330325,9002,330329,133971,133970,1968584,3475914,9003,9004', 'filter': 'HS,GEM2STAR', 'order_field': '330324', 'order_type': '0', 'date': date}
    try:
        r = requests.get(url, params=params, headers={'User-Agent': UA}, timeout=10)
        info = (r.json().get('data') or {}).get('info', [])
    except Exception as e:
        print(f'[WARN] 同花顺涨停揭秘请求失败: {e}')
        return []
    out = []
    for it in info:
        ft = it.get('first_limit_up_time')
        out.append({'code': it.get('code'), 'name': it.get('name'), 'price': it.get('latest'), 'pct': it.get('change_rate'), 'reason': it.get('reason_type', ''), 'board_type': it.get('limit_up_type', ''), 'seal_rate': it.get('limit_up_suc_rate'), 'break_times': it.get('open_num') or 0, 'seal_amount': it.get('order_amount'), 'high_days': it.get('high_days', ''), 'first_time': datetime.fromtimestamp(int(ft)).strftime('%H:%M:%S') if ft else '', 'is_again': it.get('is_again_limit')})
    return out

def limit_up_sentiment(date: str) -> dict:
    """打板情绪温度计：连板梯队 + 炸板率 + 涨跌停对比。"""
    zt, zb, dt = (em_zt_pool(date), em_zb_pool(date), em_dt_pool(date))
    ladder = {}
    for s in zt:
        ladder[s['limit_days']] = ladder.get(s['limit_days'], 0) + 1
    zt_n, zb_n = (len(zt), len(zb))
    return {'date': date, 'zt_count': zt_n, 'zb_count': zb_n, 'dt_count': len(dt), 'break_rate': round(zb_n / (zt_n + zb_n) * 100, 1) if zt_n + zb_n else 0, 'max_height': max((s['limit_days'] for s in zt), default=0), 'ladder': dict(sorted(ladder.items()))}
from datetime import datetime, timedelta, timezone

def cn_today() -> str:
    """北京时间的今天（YYYY-MM-DD）。"""
    return datetime.now(CN_TZ).date().isoformat()
MONITOR_URL = 'https://mobappconfig.securities.eastmoney.com/emcfg/stock_monitor.json'
_MONITOR_MARKET = {'1': 'SH', '0': 'SZ', 'B': 'BJ'}

def em_stock_monitor(only_active: bool=True) -> list[dict]:
    """东财重点监控池。
    only_active=True 只留今天仍在监控窗口内的（按 VALIDATESTARTDATE~VALIDATEENDDATE 过滤）。
    返回: [{code, name, market, start, end, link}]
    """
    r = em_get(MONITOR_URL, headers={'Referer': 'https://vipmoney.eastmoney.com/'}, timeout=20)
    rows = r.json() or []
    today = cn_today()
    out = []
    for x in rows:
        start, end = (x.get('VALIDATESTARTDATE', ''), x.get('VALIDATEENDDATE', ''))
        if only_active and (not start <= today <= end):
            continue
        raw_mkt = str(x.get('MARKET', '')).upper()
        out.append({'code': x.get('STKCODE', ''), 'name': x.get('STKNAME', ''), 'market': _MONITOR_MARKET.get(raw_mkt, f'?{raw_mkt}'), 'start': start, 'end': end, 'link': x.get('LINK_URL', '')})
    return out
ANOMALY_BASE = 'https://dycalchis.eastmoney.com/price-anomaly'
HQ_PARAMS = {'team': 'h5', 'product': 'EastMoney', 'client': 'WAP', 'version': '9001', 'name': 'WAP', 'user': '123'}
ANOMALY_RULES = {1: '主板连续10个交易日内4次出现同向异常波动', 2: '创业板连续10个交易日内3次出现同向异常波动', 3: '科创板连续10个交易日内3次出现同向异常波动', 4: '连续十个交易日内日收盘价涨跌幅偏离值累计达到+100%', 5: '连续十个交易日内日收盘价涨跌幅偏离值累计达到-50%', 6: '连续三十个交易日内日收盘价涨跌幅偏离值累计达到+200%', 7: '连续三十个交易日内日收盘价涨跌幅偏离值累计达到-70%', 8: '北交所连续10个交易日内3次出现同向异常波动', 40: '连续十个交易日内日收盘价涨跌幅偏离值累计达到+150%', 50: '连续十个交易日内日收盘价涨跌幅偏离值累计达到-60%', 60: '连续30个交易日内日收盘价涨跌幅偏离值累计达到+300%', 70: '连续30个交易日内日收盘价涨跌幅偏离值累计达到-75%'}

def _anomaly_market(code, m, board=None) -> str:
    """异动记录 → 交易所。
    ⚠️ 不能只看 m：东财体系里**北交所与深市同为 m=0**（拉北交所清单用的就是 `m:0+t:81`），
       只按 `m==1 else "SZ"` 会把北交所标的错标成 SZ——而异动规则码 8 正是北交所专用，
       说明北交所记录确实会出现在本接口。代码号段无歧义，优先用它判。
    """
    c = str(code or '')
    if c.startswith('920') or c[:2] in ('43', '83', '87') or board == 8:
        return 'BJ'
    return 'SH' if m == 1 else 'SZ'

def _anomaly_get(path: str, page_size: int, page_no: int, **extra) -> dict:
    params = {**HQ_PARAMS, 'pageSize': str(page_size), 'pageNo': str(page_no), **extra}
    r = em_get(f'{ANOMALY_BASE}/{path}', params=params, headers={'Referer': 'https://vipmoney.eastmoney.com/'}, timeout=20)
    d = r.json()
    if d.get('result') != 0:
        raise RuntimeError(f'东财异动接口拒绝: result={d.get('result')} msg={d.get('msg')!r}')
    return d

def em_price_anomaly(page_size: int=200, page_no: int=1) -> dict:
    """日内异动明细（price-anomaly/list）。返回 {date, items:[...]}"""
    d = _anomaly_get('list', page_size, page_no)
    items = []
    for x in d.get('data') or []:
        e = x.get('e')
        key = e * 10 if x.get('s') == 6 and e in (4, 5, 6, 7) else e
        items.append({'code': x.get('c'), 'name': x.get('n'), 'market': _anomaly_market(x.get('c'), x.get('m'), x.get('s')), 'change_pct': x.get('a'), 'deviation': x.get('x'), 'days': x.get('d'), 'board': x.get('s'), 'rule_code': key, 'rule': ANOMALY_RULES.get(key, f'未知规则码 {key}'), 'is_today': x.get('o') != 2})
    return {'date': str(d.get('date', '')), 'pages': d.get('pages', 0), 'items': items}

def em_price_anomaly_count(page_size: int=50, page_no: int=1, sort_key: str='', sort_dir: str='') -> dict:
    """异动统计（price-anomaly/count）：按标的聚合的异动次数 + 现价。"""
    d = _anomaly_get('count', page_size, page_no, sortKey=sort_key, sortDir=sort_dir)
    items = [{'code': x.get('c'), 'name': x.get('n'), 'market': _anomaly_market(x.get('c'), x.get('m'), x.get('s')), 'price': x.get('p'), 'change_pct': x.get('a'), 'times': x.get('t'), 'deviation': x.get('x'), 'days': x.get('d'), 'board': x.get('s')} for x in d.get('data') or []]
    return {'date': str(d.get('date', '')), 'pages': d.get('pages', 0), 'items': items}
import requests
SINA_OPT_HDR = {'Referer': 'https://stock.finance.sina.com.cn/', 'User-Agent': UA}

def _opt_f(x):
    try:
        return float(x)
    except Exception:
        return x

def _sina_opt_list(param: str) -> list:
    """新浪 hq.sinajs.cn 取值（GBK，逗号分隔，去 var hq_str_XXX="..." 壳）。"""
    r = requests.get(f'https://hq.sinajs.cn/list={param}', headers=SINA_OPT_HDR, timeout=10)
    r.encoding = 'gbk'
    t = r.text
    return t.split('"')[1].split(',') if '"' in t else []

def sina_option_codes(underlying: str='510050', call: bool=True) -> dict:
    """ETF期权合约清单。underlying: 510050/510300/588000/510500。call=True认购/False认沽。
    返回 {月份YYMM: [合约代码,...]}，第一个 key 即近月。"""
    cate = {'510050': '50ETF', '510300': '300ETF', '588000': '科创50ETF', '510500': '500ETF'}.get(underlying, '50ETF')
    url = f'https://stock.finance.sina.com.cn/futures/api/openapi.php/StockOptionService.getStockName?exchange=null&cate={cate}'
    try:
        months = requests.get(url, headers=SINA_OPT_HDR, timeout=10).json()['result']['data']['contractMonth']
    except Exception as e:
        print(f'[WARN] 期权月份获取失败: {e}')
        return {}
    months = [m.replace('-', '')[2:] for m in months[1:]]
    flag = 'OP_UP_' if call else 'OP_DOWN_'
    out = {}
    for m in months:
        codes = [c.replace('CON_OP_', '') for c in _sina_opt_list(f'{flag}{underlying}{m}') if c.startswith('CON_OP_')]
        if codes:
            out[m] = codes
    return out

def sina_option_tquote(code: str) -> dict:
    """期权T型报价。返回 bid_vol/bid/last/ask/ask_vol/open_interest(持仓量)/pct/
    strike(行权价)/prev_close/open/limit_up/limit_down/name/amplitude/high/low/volume/amount。"""
    v = _sina_opt_list(f'CON_OP_{code}')
    if len(v) < 43:
        return {}
    return {'bid_vol': _opt_f(v[0]), 'bid': _opt_f(v[1]), 'last': _opt_f(v[2]), 'ask': _opt_f(v[3]), 'ask_vol': _opt_f(v[4]), 'open_interest': _opt_f(v[5]), 'pct': _opt_f(v[6]), 'strike': _opt_f(v[7]), 'prev_close': _opt_f(v[8]), 'open': _opt_f(v[9]), 'limit_up': _opt_f(v[10]), 'limit_down': _opt_f(v[11]), 'name': v[37], 'amplitude': _opt_f(v[38]), 'high': _opt_f(v[39]), 'low': _opt_f(v[40]), 'volume': _opt_f(v[41]), 'amount': _opt_f(v[42])}

def sina_option_greeks(code: str) -> dict:
    """期权希腊字母 + 隐含波动率。返回 name/volume/delta/gamma/theta/vega/
    iv(隐含波动率,小数)/high/low/trade_code/strike/last/theory(理论价值)。"""
    raw = _sina_opt_list(f'CON_SO_{code}')
    if len(raw) < 16:
        return {}
    v = [raw[0]] + raw[4:]
    return {'name': v[0], 'volume': _opt_f(v[1]), 'delta': _opt_f(v[2]), 'gamma': _opt_f(v[3]), 'theta': _opt_f(v[4]), 'vega': _opt_f(v[5]), 'iv': _opt_f(v[6]), 'high': _opt_f(v[7]), 'low': _opt_f(v[8]), 'trade_code': v[9], 'strike': _opt_f(v[10]), 'last': _opt_f(v[11]), 'theory': _opt_f(v[12])}
import requests
from datetime import datetime

def cninfo_irm(code: str, page_size: int=30, page_num: int=1) -> list[dict]:
    """互动易问答（深沪统一走巨潮）。code: 6位代码。
    返回每条: code/company/question(投资者提问)/answer(公司回复,None=未回复)/
    answerer(回答方)/ask_time。"""
    try:
        r1 = requests.post('https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo', data={'keyWord': code}, headers={'User-Agent': UA}, timeout=10)
        d1 = r1.json().get('data') or []
        if not d1:
            return []
        org_id = d1[0].get('secid')
        params = {'_t': 1, 'stockcode': code, 'orgId': org_id, 'pageSize': page_size, 'pageNum': page_num, 'keyWord': '', 'startDay': '', 'endDay': ''}
        r2 = requests.post('https://irm.cninfo.com.cn/newircs/company/question', params=params, headers={'User-Agent': UA}, timeout=10)
        rows = r2.json().get('rows') or []
    except Exception as e:
        print(f'[WARN] 互动易请求失败: {e}')
        return []
    out = []
    for it in rows:
        pd = it.get('pubDate')
        out.append({'code': it.get('stockCode'), 'company': it.get('companyShortName'), 'question': it.get('mainContent'), 'answer': it.get('attachedContent'), 'answerer': it.get('attachedAuthor'), 'ask_time': datetime.fromtimestamp(pd / 1000).strftime('%Y-%m-%d %H:%M') if pd else ''})
    return out
EM_HOT_BODY = {'appId': 'appId01', 'globalId': '786e4c21-70dc-435a-93bb-38'}

def ths_hot_list(period: str='hour') -> list[dict]:
    """同花顺热榜（单接口拿名称+人气+概念标签+排名变化）。period: hour/day。
    返回每只: rank/code/name/heat(人气值)/pct/rank_chg(排名变化)/concepts(概念标签)/tag。"""
    try:
        r = requests.get('https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock', params={'stock_type': 'a', 'type': period, 'list_type': 'normal'}, headers={'User-Agent': UA}, timeout=10)
        lst = (r.json().get('data') or {}).get('stock_list') or []
    except Exception as e:
        print(f'[WARN] 同花顺热榜失败: {e}')
        return []
    out = []
    for it in lst:
        tag = it.get('tag') or {}
        out.append({'rank': it.get('order'), 'code': it.get('code'), 'name': it.get('name'), 'heat': it.get('rate'), 'pct': it.get('rise_and_fall'), 'rank_chg': it.get('hot_rank_chg'), 'concepts': tag.get('concept_tag') or [], 'tag': tag.get('popularity_tag', '')})
    return out

def em_hot_rank(top: int=50) -> list[dict]:
    """东财人气榜（排名 + 排名变化 + 名称/价格）。返回 rank/code/name/price/pct/rank_chg。"""
    try:
        r = requests.post('https://emappdata.eastmoney.com/stockrank/getAllCurrentList', json={**EM_HOT_BODY, 'marketType': '', 'pageNo': 1, 'pageSize': top}, headers={'User-Agent': UA}, timeout=10)
        data = r.json().get('data') or []
        if not data:
            return []
        secids = [('0.' if it['sc'].startswith('SZ') else '1.') + it['sc'][2:] for it in data]
        u = requests.get('https://push2.eastmoney.com/api/qt/ulist.np/get', params={'ut': 'f057cbcbce2a86e2866ab8877db1d059', 'fltt': 2, 'invt': 2, 'fields': 'f14,f3,f12,f2', 'secids': ','.join(secids)}, headers={'User-Agent': UA, 'Referer': 'https://quote.eastmoney.com/'}, timeout=10)
        diff = (u.json().get('data') or {}).get('diff') or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        nm = {x['f12']: (x.get('f14'), x.get('f2'), x.get('f3')) for x in diff}
    except Exception as e:
        print(f'[WARN] 东财人气榜失败: {e}')
        return []
    out = []
    for it in data:
        code = it['sc'][2:]
        name, price, pct = nm.get(code, ('', None, None))
        out.append({'rank': it['rk'], 'code': code, 'name': name, 'price': price, 'pct': pct, 'rank_chg': it.get('hisRc')})
    return out

def em_hot_concept(code: str) -> list[dict]:
    """东财个股热门概念命中（这只票当下被市场归到哪些概念在炒）。
    返回 [{concept, bk, hit(命中热度)}, ...]，按热度降序。"""
    try:
        prefix = 'SH' if code.startswith('6') else 'SZ'
        r = requests.post('https://emappdata.eastmoney.com/stockrank/getHotStockRankList', json={**EM_HOT_BODY, 'srcSecurityCode': prefix + code}, headers={'User-Agent': UA}, timeout=10)
        data = r.json().get('data') or []
    except Exception as e:
        print(f'[WARN] 东财个股概念失败: {e}')
        return []
    return [{'concept': x.get('conceptName'), 'bk': x.get('conceptId'), 'hit': x.get('hitCount')} for x in data]

def forward_pe(price: float, eps_forecast: float) -> float:
    """前向PE = 当前股价 / 未来年度一致预期EPS"""
    if eps_forecast <= 0:
        return float('inf')
    return price / eps_forecast
import math

def pe_digestion(current_pe: float, cagr: float, target_pe: float=30) -> float:
    """
    当前PE消化到目标PE需要多少年。
    target_pe 固定30x（A股成长股合理估值锚点）。
    cagr: 用 下一年EPS / 当年EPS - 1
    """
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float('inf')
    return math.log(current_pe / target_pe) / math.log(1 + cagr)

def calc_peg(pe: float, cagr: float) -> float:
    """
    PEG = 前向PE / (CAGR * 100)
    PEG < 1   → 便宜
    PEG 1-1.5 → 合理
    PEG > 1.5 → 贵
    """
    if cagr <= 0:
        return float('inf')
    return pe / (cagr * 100)
import requests
import urllib.request
import math
import pandas as pd

def full_valuation(code: str) -> dict:
    """单票完整估值分析"""
    prefix = 'bj' if code.startswith(('92', '8')) else 'sh' if code.startswith(('6', '9')) else 'sz'
    url = f'https://qt.gtimg.cn/q={prefix}{code}'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode('gbk')
    vals = data.split('"')[1].split('~')
    price = float(vals[3])
    mcap = float(vals[45])
    pe_ttm = float(vals[39]) if vals[39] else 0
    pb = float(vals[46]) if vals[46] else 0
    df = ths_eps_forecast(code)
    eps_cur = eps_next = None
    analyst_count = 0
    if not df.empty and len(df.columns) >= 3:

        def _pick(row, name):
            for c in df.columns:
                if name in str(c):
                    return row.get(c)
            return None
        try:
            r0 = df.iloc[0]
            v = _pick(r0, '均值')
            eps_cur = float(v) if pd.notna(v) else None
            cnt = _pick(r0, '预测机构数')
            analyst_count = int(cnt) if pd.notna(cnt) else 0
            if len(df) >= 2:
                vn = _pick(df.iloc[1], '均值')
                eps_next = float(vn) if pd.notna(vn) else None
        except (ValueError, TypeError) as e:
            print(f'[WARN] full_valuation EPS 解析失败({e})，估值可能不完整')
    pe_fwd = price / eps_cur if eps_cur else float('inf')
    cagr = eps_next / eps_cur - 1 if eps_cur and eps_next else 0
    peg = pe_fwd / (cagr * 100) if cagr > 0 else float('inf')
    digest = math.log(pe_fwd / 30) / math.log(1 + cagr) if pe_fwd > 30 and cagr > 0 else 0
    return {'name': vals[1], 'price': price, 'mcap_yi': mcap, 'pe_ttm': pe_ttm, 'pb': pb, 'eps_cur': eps_cur, 'eps_next': eps_next, 'pe_fwd': round(pe_fwd, 1) if eps_cur else None, 'cagr_pct': round(cagr * 100, 0) if cagr else None, 'peg': round(peg, 2) if peg != float('inf') else None, 'digest_years': round(digest, 1), 'analyst_count': analyst_count}
import json, urllib.request, ssl
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

def dragon_tiger_backup(trade_date: str) -> dict:
    """龙虎榜官方备用源（东财被封时用）：上交所+深交所官方，零鉴权权威一手，含营业部席位。"""
    out = {'date': trade_date, 'sse_raw': '', 'szse': []}
    su = f'https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1842_xxpl&TABKEY=tab1&txtStart={trade_date}&txtEnd={trade_date}&random=0.9'
    req = urllib.request.Request(su, headers={'User-Agent': UA, 'Referer': 'https://www.szse.cn/disclosure/supervision/dealinfo/index.html'})
    with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
        d = json.loads(r.read())
    for row in d[0].get('data', []):
        out['szse'].append({'code': row.get('zqdm'), 'name': row.get('zqjc'), 'amount': row.get('cjje'), 'reason': row.get('plyy')})
    eu = f'https://query.sse.com.cn/infodisplay/showTradePublicFile.do?jsonCallBack=cb&isPagination=false&dateTx={trade_date}'
    req = urllib.request.Request(eu, headers={'User-Agent': UA, 'Referer': 'https://www.sse.com.cn/disclosure/diclosure/public/'})
    with urllib.request.urlopen(req, timeout=15) as r:
        t = r.read().decode('utf-8', 'ignore')
    out['sse_raw'] = '\n'.join(json.loads(t[t.index('(') + 1:t.rindex(')')]).get('fileContents', []))
    return out

def fund_flow_backup(code: str, days: int=60) -> list:
    """个股资金流备用源（东财被封时用）：新浪，日度四档单净额。"""
    pre = ('bj' if code.startswith(('92', '8')) else 'sh' if code.startswith(('6', '9')) else 'sz') + code
    u = f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={days}&sort=opendate&asc=0&daima={pre}'
    req = urllib.request.Request(u, headers={'User-Agent': UA, 'Referer': 'https://finance.sina.com.cn/'})
    with urllib.request.urlopen(req, timeout=15) as r:
        t = r.read().decode('utf-8', 'ignore')
    arr = json.loads(t[t.index('['):t.rindex(']') + 1])
    return [{'date': x.get('opendate'), 'close': x.get('trade'), 'net_amount': x.get('netamount'), 'turnover': x.get('turnover')} for x in arr]

def announcements_backup(code: str, page_size: int=20) -> list:
    """公告备用源（巨潮被封时用）：深市走深交所官方，沪市走东财，均带 PDF 直链。"""
    if code.startswith(('0', '3')):
        body = json.dumps({'channelCode': ['listedNotice_disc'], 'pageSize': page_size, 'pageNum': 1, 'stock': [code]}).encode()
        req = urllib.request.Request('https://www.szse.cn/api/disc/announcement/annList', data=body, headers={'User-Agent': UA, 'Content-Type': 'application/json', 'Referer': 'https://www.szse.cn/disclosure/listed/notice/index.html'})
        with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
            d = json.loads(r.read())
        return [{'title': a.get('title'), 'time': a.get('publishTime', '')[:10], 'pdf': 'https://disc.static.szse.cn/download' + a.get('attachPath', '')} for a in d.get('data', [])]
    u = f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size={page_size}&page_index=1&ann_type=A&client_source=web&stock_list={code}&f_node=0&s_node=0'
    req = urllib.request.Request(u, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    return [{'title': a.get('title'), 'time': a.get('notice_date', '')[:10], 'pdf': f'https://pdf.dfcfw.com/pdf/H2_{a.get('art_code', '')}_1.pdf'} for a in d.get('data', {}).get('list', [])]
