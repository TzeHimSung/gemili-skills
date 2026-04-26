"""
新浪财经行情 API 公共库
https://hq.sinajs.cn/list=<tickers>
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests

# ═══════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════

API_BASE = "https://hq.sinajs.cn/list="
REFERER = "https://finance.sina.com.cn/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": REFERER,
}

NO_PROXY = {"http": None, "https": None}

# ── Ticker 配置 ──────────────────────────────────────

# 常用美股个股
US_STOCKS: dict[str, str] = {
    "gb_nvda": "NVIDIA",
    "gb_tsla": "Tesla",
    "gb_aapl": "Apple",
    "gb_msft": "Microsoft",
    "gb_goog": "Alphabet (Google)",
    "gb_amzn": "Amazon",
    "gb_meta": "Meta",
    "gb_nflx": "Netflix",
    "gb_avgo": "Broadcom",
    "gb_qcom": "Qualcomm",
    "gb_arm": "ARM Holdings",
    "gb_amd": "AMD",
    "gb_intc": "Intel",
    "gb_smci": "Supermicro",
    "gb_pltr": "Palantir",
    "gb_crm": "Salesforce",
    "gb_adbe": "Adobe",
    "gb_orcl": "Oracle",
    "gb_txn": "Texas Instruments",
    "gb_asml": "ASML",
    "gb_tsm": "TSMC",
    "gb_mrvl": "Marvell",
    "gb_now": "ServiceNow",
    "gb_panw": "Palo Alto Networks",
    "gb_crowd": "CrowdStrike",
    "gb_snow": "Snowflake",
    "gb_mdb": "MongoDB",
    "gb_uber": "Uber",
    "gb_shop": "Shopify",
    "gb_pdd": "拼多多",
    "gb_baba": "阿里巴巴",
    "gb_jd": "京东",
    "gb_bidu": "百度",
    "gb_nio": "蔚来",
    "gb_li": "理想汽车",
    "gb_xpev": "小鹏汽车",
}

# 美股指数
US_INDICES: dict[str, str] = {
    "int_dji": "道琼斯工业",
    "int_nasdaq": "纳斯达克综合",
    "int_sp500": "S&P 500",
    "gb_sox": "费城半导体 SOX",
    "int_hangseng": "恒生指数",
    "int_nikkei": "日经225",
}

# 科技板块重点跟踪（从 US_STOCKS 中选）
TECH_FOCUS: list[str] = [
    "gb_nvda", "gb_tsla", "gb_avgo", "gb_qcom", "gb_arm",
    "gb_amd", "gb_smci", "gb_pltr", "gb_asml", "gb_tsm",
    "gb_mrvl", "gb_now", "gb_panw", "gb_crowd",
]

# ═══════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════


@dataclass
class StockQuote:
    """美股个股行情。"""
    ticker: str           # e.g. "gb_nvda"
    name: str             # 中文名称
    price: float          # 当前价
    change_pct: float     # 涨跌幅 (%)
    change_amt: float     # 涨跌额
    prev_close: float     # 昨收
    high: float           # 日内最高
    low: float            # 日内最低
    high_52w: float       # 52 周最高
    low_52w: float        # 52 周最低
    volume: int           # 成交量
    time_str: str         # 时间字符串
    fetched_at: str = ""  # 抓取时间

    @property
    def is_up(self) -> bool:
        return self.change_pct >= 0

    @property
    def change_sign(self) -> str:
        return "+" if self.is_up else ""


@dataclass
class IndexQuote:
    """指数行情。"""
    ticker: str           # e.g. "int_dji"
    name: str             # 中文名称
    price: float          # 当前点数
    change_pct: float     # 涨跌幅 (%)
    change_amt: float     # 涨跌额
    fetched_at: str = ""  # 抓取时间

    @property
    def is_up(self) -> bool:
        return self.change_pct >= 0

    @property
    def change_sign(self) -> str:
        return "+" if self.is_up else ""


# ═══════════════════════════════════════════════════
# HTTP 客户端
# ═══════════════════════════════════════════════════


def fetch_raw(tickers: list[str], timeout: int = 15, retries: int = 2) -> str:
    """
    批量抓取原始行情文本。
    tickers: e.g. ["gb_nvda", "int_dji", "gb_sox"]
    返回原始响应文本。
    """
    url = API_BASE + ",".join(tickers)

    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                proxies=NO_PROXY,
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2 ** attempt)

    raise last_exc  # type: ignore[misc]


# ═══════════════════════════════════════════════════
# 解析器
# ═══════════════════════════════════════════════════


def _split_line(line: str) -> tuple[str, list[str]]:
    """拆分单行 var hq_str_<TICKER>="<fields>"; 为 (ticker, [fields])。"""
    if '=""' in line or not line.strip():
        return "", []
    m = re.match(r'var hq_str_([^=]+)="(.*)"\s*;?', line)
    if not m:
        return "", []
    ticker = m.group(1)
    fields = m.group(2).split(",")
    return ticker, fields


def parse_stock(ticker: str, fields: list[str]) -> StockQuote:
    """解析个股字段（11+ 字段）。"""
    def _f(i: int) -> float:
        try:
            return float(fields[i])
        except (ValueError, IndexError):
            return 0.0

    def _i(i: int) -> int:
        try:
            return int(float(fields[i]))
        except (ValueError, IndexError):
            return 0

    now = datetime.now().isoformat(timespec="seconds")
    return StockQuote(
        ticker=ticker,
        name=fields[0],
        price=_f(1),
        change_pct=_f(2),
        time_str=fields[3] if len(fields) > 3 else "",
        change_amt=_f(4),
        prev_close=_f(5),
        high=_f(6),
        low=_f(7),
        high_52w=_f(8),
        low_52w=_f(9),
        volume=_i(10),
        fetched_at=now,
    )


def parse_index(ticker: str, fields: list[str]) -> IndexQuote:
    """解析指数字段（4 字段）。"""
    def _f(i: int) -> float:
        try:
            return float(fields[i])
        except (ValueError, IndexError):
            return 0.0

    now = datetime.now().isoformat(timespec="seconds")
    return IndexQuote(
        ticker=ticker,
        name=fields[0],
        price=_f(1),
        change_amt=_f(2),
        change_pct=_f(3),
        fetched_at=now,
    )


def parse_response(raw_text: str) -> tuple[list[StockQuote], list[IndexQuote]]:
    """
    解析原始响应，返回 (stocks, indices)。
    """
    stocks: list[StockQuote] = []
    indices: list[IndexQuote] = []

    for line in raw_text.strip().split("\n"):
        ticker, fields = _split_line(line)
        if not ticker or not fields:
            continue

        if ticker.startswith("int_"):
            indices.append(parse_index(ticker, fields))
        else:
            stocks.append(parse_stock(ticker, fields))

    return stocks, indices


# ═══════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════


def fetch_stocks(
    tickers: Optional[list[str]] = None,
) -> list[StockQuote]:
    """抓取指定美股个股。不传 tickers 则取全量 US_STOCKS。"""
    if tickers is None:
        tickers = list(US_STOCKS.keys())
    raw = fetch_raw(tickers)
    stocks, _ = parse_response(raw)
    return stocks


def fetch_indices(
    tickers: Optional[list[str]] = None,
) -> list[IndexQuote]:
    """抓取指数。"""
    if tickers is None:
        tickers = list(US_INDICES.keys())
    raw = fetch_raw(tickers)
    _, indices = parse_response(raw)
    return indices


def fetch_all() -> tuple[list[StockQuote], list[IndexQuote]]:
    """抓取全部（个股 + 指数）。"""
    all_tickers = list(US_STOCKS.keys()) + list(US_INDICES.keys())
    raw = fetch_raw(all_tickers)
    return parse_response(raw)
