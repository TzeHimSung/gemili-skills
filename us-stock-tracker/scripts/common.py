"""
美股行情追踪 — 公共库
双数据源：新浪财经 (hq.sinajs.cn) + Yahoo Finance (query1.finance.yahoo.com)
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

# ═══════════════════════════════════════════════════
# HTTP
# ═══════════════════════════════════════════════════

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
NO_PROXY = {"http": None, "https": None}


def http_get(
    url: str,
    referer: str = "",
    timeout: int = 15,
    retries: int = 2,
) -> requests.Response:
    """通用 HTTP GET，自动绕过代理，带重试。"""
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
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
    raise last_exc  # type: ignore


# ═══════════════════════════════════════════════════
# Ticker 配置
# ═══════════════════════════════════════════════════

# Sina 格式 → 显示名
SINA_STOCKS: dict[str, str] = {
    "gb_nvda": "NVIDIA",       "gb_tsla": "Tesla",
    "gb_aapl": "Apple",        "gb_msft": "Microsoft",
    "gb_goog": "Google",       "gb_amzn": "Amazon",
    "gb_meta": "Meta",         "gb_nflx": "Netflix",
    "gb_avgo": "Broadcom",     "gb_qcom": "Qualcomm",
    "gb_arm": "ARM",           "gb_amd": "AMD",
    "gb_intc": "Intel",        "gb_smci": "Supermicro",
    "gb_pltr": "Palantir",     "gb_crm": "Salesforce",
    "gb_adbe": "Adobe",        "gb_orcl": "Oracle",
    "gb_txn": "Texas Inst.",   "gb_asml": "ASML",
    "gb_tsm": "TSMC",          "gb_mrvl": "Marvell",
    "gb_now": "ServiceNow",    "gb_panw": "Palo Alto",
    "gb_crowd": "CrowdStrike", "gb_snow": "Snowflake",
    "gb_mdb": "MongoDB",       "gb_uber": "Uber",
    "gb_shop": "Shopify",
    "gb_pdd": "拼多多",        "gb_baba": "阿里巴巴",
    "gb_jd": "京东",           "gb_bidu": "百度",
    "gb_nio": "蔚来",           "gb_li": "理想汽车",
    "gb_xpev": "小鹏汽车",
}

SINA_INDICES: dict[str, str] = {
    "int_dji": "道琼斯",        "int_nasdaq": "纳斯达克",
    "int_sp500": "S&P 500",     "gb_sox": "费城半导体",
    "int_hangseng": "恒生指数",  "int_nikkei": "日经225",
}

# Yahoo ticker → 显示名（用于收盘日报）
YAHOO_STOCKS: dict[str, str] = {
    "NVDA": "NVIDIA",      "TSLA": "Tesla",
    "AAPL": "Apple",       "MSFT": "Microsoft",
    "GOOGL": "Google",     "AMZN": "Amazon",
    "META": "Meta",        "NFLX": "Netflix",
    "AVGO": "Broadcom",    "QCOM": "Qualcomm",
    "ARM": "ARM",          "AMD": "AMD",
    "INTC": "Intel",       "SMCI": "Supermicro",
    "PLTR": "Palantir",    "CRM": "Salesforce",
    "ADBE": "Adobe",       "ORCL": "Oracle",
    "TXN": "Texas Inst.",  "ASML": "ASML",
    "TSM": "TSMC",         "MRVL": "Marvell",
    "NOW": "ServiceNow",   "PANW": "Palo Alto",
    "CRWD": "CrowdStrike", "SNOW": "Snowflake",
    "MDB": "MongoDB",      "UBER": "Uber",
    "SHOP": "Shopify",     "PDD": "拼多多",
    "BABA": "阿里巴巴",     "JD": "京东",
    "BIDU": "百度",         "NIO": "蔚来",
    "LI": "理想汽车",       "XPEV": "小鹏汽车",
}

# Yahoo ticker → 带中文名的显示名（日报用）
YAHOO_STOCKS_CN: dict[str, str] = {
    "NVDA": "NVDA 英伟达",       "TSLA": "TSLA 特斯拉",
    "AAPL": "AAPL 苹果",          "MSFT": "MSFT 微软",
    "GOOGL": "GOOGL 谷歌",        "AMZN": "AMZN 亚马逊",
    "META": "META Meta",          "NFLX": "NFLX 奈飞",
    "AVGO": "AVGO 博通",          "QCOM": "QCOM 高通",
    "ARM": "ARM",                 "AMD": "AMD 超威",
    "INTC": "INTC 英特尔",        "SMCI": "SMCI 超微电脑",
    "PLTR": "PLTR Palantir",      "CRM": "CRM Salesforce",
    "ADBE": "ADBE Adobe",         "ORCL": "ORCL 甲骨文",
    "TXN": "TXN 德州仪器",        "ASML": "ASML 阿斯麦",
    "TSM": "TSM 台积电",          "MRVL": "MRVL Marvell",
    "NOW": "NOW ServiceNow",      "PANW": "PANW Palo Alto",
    "CRWD": "CRWD CrowdStrike",   "SNOW": "SNOW Snowflake",
    "MDB": "MDB MongoDB",         "UBER": "UBER 优步",
    "SHOP": "SHOP Shopify",       "PDD": "PDD 拼多多",
    "BABA": "BABA 阿里巴巴",      "JD": "JD 京东",
    "BIDU": "BIDU 百度",          "NIO": "NIO 蔚来",
    "LI": "LI 理想汽车",           "XPEV": "XPEV 小鹏汽车",
}

YAHOO_INDICES: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^IXIC": "纳斯达克",
    "^DJI": "道琼斯",
    "^SOX": "费城半导体",
}

# 板块分组
SECTORS: dict[str, set[str]] = {
    "💾 半导体": {"NVDA", "AMD", "AVGO", "QCOM", "ARM", "TSM", "ASML", "MRVL", "TXN", "INTC", "SMCI"},
    "☁️ 软件/云": {"MSFT", "CRM", "ADBE", "ORCL", "NOW", "SNOW", "MDB", "PANW", "CRWD", "PLTR"},
    "🛒 消费科技": {"AAPL", "AMZN", "TSLA", "GOOGL", "META", "NFLX", "UBER", "SHOP"},
    "🇨🇳 中概": {"BABA", "JD", "PDD", "BIDU", "NIO", "LI", "XPEV"},
}

PSEUDO_INDICES = {"gb_sox"}  # Sina: gb_前缀但显示为指数

# 科技板块重点股（Sina 格式，用于 --tech-only）
TECH_FOCUS = [
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
    ticker: str           # Yahoo: "NVDA" / Sina: "gb_nvda"
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
    source: str = ""       # "sina" / "yahoo"

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
