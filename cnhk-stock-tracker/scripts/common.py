"""
中港股行情追踪 — 公共库
双数据源：新浪财经 (hq.sinajs.cn) + Yahoo Finance (query1.finance.yahoo.com)
覆盖 A 股芯片半导体 + 港股科技/LLM 概念
"""

import re
import time
import subprocess
import json
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional

import requests

# ═══════════════════════════════════════════════════
# HTTP
# ═══════════════════════════════════════════════════

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
NO_PROXY = {"http": None, "https": None}


def http_get(url: str, referer: str = "", timeout: int = 15, retries: int = 2) -> requests.Response:
    """通用 HTTP GET，自动绕过代理，带重试。"""
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, proxies=NO_PROXY)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise last_exc


# ═══════════════════════════════════════════════════
# Ticker 配置 — 新浪财经（实时快照 / snapshot.py）
# ═══════════════════════════════════════════════════

SINA_A_STOCKS: dict[str, str] = {
    # A 股芯片半导体
    "sh688981": "中芯国际",     "sh688041": "海光信息",
    "sh688256": "寒武纪",       "sz002371": "北方华创",
    "sh603501": "韦尔股份",     "sh688008": "澜起科技",
    "sh688012": "中微公司",     "sh600584": "长电科技",
    "sz300782": "卓胜微",       "sh603986": "兆易创新",
    "sh688126": "沪硅产业",     "sh688347": "华虹公司",
    "sh688072": "拓荆科技",     "sz002049": "紫光国微",
}

SINA_HK_STOCKS: dict[str, str] = {
    # 港股科技 / LLM 概念
    "hk00700": "腾讯控股",      "hk01810": "小米集团",
    "hk09988": "阿里巴巴",      "hk03690": "美团",
    "hk09618": "京东集团",      "hk09999": "网易",
    "hk01024": "快手",          "hk09888": "百度集团",
    "hk00020": "商汤-W",        "hk00981": "中芯国际",
    "hk09626": "哔哩哔哩",      "hk00268": "金蝶国际",
    "hk01347": "华虹半导体",    "hk03896": "金山云",
    "hk02013": "微盟集团",      "hk01833": "平安好医生",
}

SINA_INDICES: dict[str, str] = {
    "s_sh000001": "上证指数",     "s_sz399001": "深证成指",
    "s_sz399006": "创业板指",     "s_sh000688": "科创50",
    "int_hangseng": "恒生指数",   "int_hstech": "恒生科技",
}

PSEUDO_INDICES: set[str] = set()  # 无需特殊处理


# ═══════════════════════════════════════════════════
# Ticker 配置 — Yahoo Finance v8（收盘日报 / daily_report.py）
# ═══════════════════════════════════════════════════

# Yahoo A 股格式：XXXXXX.SS (上交所) / XXXXXX.SZ (深交所)
YAHOO_A_STOCKS: dict[str, str] = {
    "688981.SS": "中芯国际",     "688041.SS": "海光信息",
    "688256.SS": "寒武纪",       "002371.SZ": "北方华创",
    "603501.SS": "韦尔股份",     "688008.SS": "澜起科技",
    "688012.SS": "中微公司",     "600584.SS": "长电科技",
    "300782.SZ": "卓胜微",       "603986.SS": "兆易创新",
    "688126.SS": "沪硅产业",     "688347.SS": "华虹公司",
    "688072.SS": "拓荆科技",     "002049.SZ": "紫光国微",
}

# Yahoo 港股格式：XXXX.HK（去掉前导零，如 00700 → 0700）
YAHOO_HK_STOCKS: dict[str, str] = {
    "0700.HK": "腾讯控股",       "1810.HK": "小米集团",
    "9988.HK": "阿里巴巴",       "3690.HK": "美团",
    "9618.HK": "京东集团",       "9999.HK": "网易",
    "1024.HK": "快手",           "9888.HK": "百度集团",
    "0020.HK": "商汤-W",         "0981.HK": "中芯国际",
    "9626.HK": "哔哩哔哩",       "0268.HK": "金蝶国际",
    "1347.HK": "华虹半导体",     "3896.HK": "金山云",
    "2013.HK": "微盟集团",       "1833.HK": "平安好医生",
}

YAHOO_INDICES: dict[str, str] = {
    "000001.SS": "上证指数",     "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",     "000688.SS": "科创50",
    "^HSI": "恒生指数",
}

# 合并配置
YAHOO_STOCKS = {**YAHOO_A_STOCKS, **YAHOO_HK_STOCKS}
YAHOO_STOCKS_CN = {k: f"{k} {v}" for k, v in YAHOO_STOCKS.items()}

# ═══════════════════════════════════════════════════
# 板块分组
# ═══════════════════════════════════════════════════

SECTORS: dict[str, set[str]] = {
    "💾 A股芯片": {
        "688981.SS", "688041.SS", "688256.SS", "002371.SZ", "603501.SS",
        "688008.SS", "688012.SS", "600584.SS", "300782.SZ", "603986.SS",
        "688126.SS", "688347.SS", "688072.SS", "002049.SZ",
    },
    "🌐 港股科技": {
        "0700.HK", "1810.HK", "9988.HK", "3690.HK", "9618.HK",
        "9999.HK", "1024.HK", "9888.HK", "0020.HK", "0981.HK",
        "9626.HK", "0268.HK", "1347.HK", "3896.HK", "2013.HK", "1833.HK",
    },
}

# 核心展示股（日报 🔍 核心科技股 展示顺序）
DISPLAY_PRIORITY = [
    # 港股科技龙头
    "0700.HK", "1810.HK", "9988.HK", "3690.HK",
    # A股芯片龙头
    "688981.SS", "688041.SS", "688256.SS", "002371.SZ",
    # 其他重要
    "9618.HK", "9999.HK", "1024.HK", "9888.HK",
    "603501.SS", "688012.SS", "688008.SS", "002049.SZ",
]

# ═══════════════════════════════════════════════════
# 市场时间
# ═══════════════════════════════════════════════════

A_MARKET_HOURS = "A 股 9:30–11:30 / 13:00–15:00（北京时间）"
HK_MARKET_HOURS = "港股 9:30–12:00 / 13:00–16:00（北京时间）"


def market_hours_display() -> str:
    """返回交易时段描述。"""
    return f"{A_MARKET_HOURS}\n{HK_MARKET_HOURS}"


def _check_market_status(stocks: list, indices: list) -> dict:
    """根据抓取数据判断最近交易日是否在昨晚。与美股版逻辑一致。"""
    hours = market_hours_display()

    all_items = list(stocks) + list(indices)
    if not all_items:
        return {"open": False, "last_trade_date": None, "reason": "无行情数据", "hours": hours}

    timestamps = []
    for item in all_items:
        ts = getattr(item, "time_str", "")
        if ts and ts.lstrip("-").isdigit():
            timestamps.append(int(ts))
    if not timestamps:
        return {"open": False, "last_trade_date": None, "reason": "无有效时间戳", "hours": hours}

    latest_ts = max(timestamps)
    latest_date = datetime.fromtimestamp(latest_ts).date()
    today = date.today()
    days_behind = (today - latest_date).days

    # 与美股版相同规则：最新数据日期是工作日 且 ≤4 天 → 开盘
    if latest_date.weekday() < 5 and days_behind <= 4:
        return {"open": True, "last_trade_date": latest_date, "reason": "", "hours": hours}

    return {
        "open": False, "last_trade_date": latest_date,
        "reason": f"最近交易日 {latest_date}，距今 {days_behind} 天", "hours": hours,
    }


def _closed_reason(latest_date: date, days_behind: int, market: str = "中港") -> str:
    """根据最近交易日推断休市原因。"""
    weekday_cn = "一二三四五六日"[latest_date.weekday()]

    if latest_date.weekday() >= 5:
        return f"最近交易日为周{weekday_cn}（{latest_date}），{market}市场周末休市"

    # 中国假期（2026）
    cn_holidays_2026 = {
        date(2026,1,1):   "元旦",
        date(2026,1,2):   "元旦假期",
        date(2026,2,16):  "春节假期", date(2026,2,17): "春节假期",
        date(2026,2,18):  "春节假期", date(2026,2,19): "春节假期",
        date(2026,2,20):  "春节假期",
        date(2026,4,6):   "清明节（补休）",
        date(2026,5,1):   "劳动节假期", date(2026,5,4): "劳动节假期",
        date(2026,5,5):   "劳动节假期",
        date(2026,6,19):  "端午节",
        date(2026,9,25):  "中秋节",
        date(2026,10,1):  "国庆节假期", date(2026,10,2): "国庆节假期",
        date(2026,10,5):  "国庆节假期", date(2026,10,6): "国庆节假期",
        date(2026,10,7):  "国庆节假期",
    }
    # 港股假期（2026）
    hk_holidays_2026 = {
        date(2026,1,1):   "元旦",
        date(2026,2,16):  "农历年初一", date(2026,2,17): "农历年初二",
        date(2026,2,18):  "农历年初三",
        date(2026,4,3):   "耶稣受难日", date(2026,4,6): "复活节星期一",
        date(2026,4,7):   "清明节",
        date(2026,5,1):   "劳动节",     date(2026,5,25): "佛诞",
        date(2026,6,19):  "端午节",
        date(2026,7,1):   "香港特区成立纪念日",
        date(2026,9,25):  "中秋节翌日", date(2026,10,1): "国庆节",
        date(2026,10,26): "重阳节",     date(2026,12,25): "圣诞节",
    }

    if market == "A股":
        holidays = cn_holidays_2026
    elif market == "港股":
        holidays = hk_holidays_2026
    elif market == "中港":
        holidays = {**cn_holidays_2026, **hk_holidays_2026}
    else:
        holidays = {}

    if latest_date in holidays:
        return f"最近交易日 {latest_date}（周{weekday_cn}），因**{holidays[latest_date]}**休市"

    return f"最近交易日 {latest_date}（周{weekday_cn}），距今 {days_behind} 天，可能为临时休市或数据延迟"


# ═══════════════════════════════════════════════════
# 数据结构（与美股版一致）
# ═══════════════════════════════════════════════════

@dataclass
class StockQuote:
    """个股行情。"""
    ticker: str          # Yahoo: "688981.SS" / Sina: "sh688981"
    name: str
    price: float
    change_pct: float
    change_amt: float
    prev_close: float = 0.0
    high: float = 0.0
    low: float = 0.0
    high_52w: float = 0.0
    low_52w: float = 0.0
    volume: int = 0
    time_str: str = ""
    fetched_at: str = ""
    source: str = ""

    @property
    def is_up(self) -> bool:
        return self.change_pct >= 0

    @property
    def change_sign(self) -> str:
        return "+" if self.is_up else ""


@dataclass
class IndexQuote:
    """指数行情。"""
    ticker: str
    name: str
    price: float
    change_pct: float
    change_amt: float = 0.0
    fetched_at: str = ""
    source: str = ""

    @property
    def is_up(self) -> bool:
        return self.change_pct >= 0

    @property
    def change_sign(self) -> str:
        return "+" if self.is_up else ""
