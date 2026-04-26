"""
美股行情追踪 — ticker 配置 + 板块分组
数据结构和工具函数从 shared/stock_tracker_lib 导入。
"""
import sys
from pathlib import Path

# 导入共享库
_SHARED = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"
sys.path.insert(0, str(_SHARED))

from stock_tracker_lib import (  # noqa: E402
    DailyBar, StockQuote, IndexQuote,
    http_get, UA, NO_PROXY,
    icon, pct_str, display_name,
    fifty_two_week_text, fifty_two_week_check,
    is_us_dst, us_market_hours_str, check_market_status, closed_reason,
    US_HOLIDAYS, CN_HOLIDAYS, HK_HOLIDAYS,
    detect_trend, DEFAULT_TREND_THRESHOLDS, CNHK_TREND_THRESHOLDS,
    deep_reason_base, trend_analysis_section,
)

# 为向后兼容导出别名
_icon = icon
_pct_str = pct_str
_fifty_two_week_text = fifty_two_week_text
_fifty_two_week_check = fifty_two_week_check
_is_us_dst = is_us_dst
_market_hours_str = us_market_hours_str
_check_market_status = check_market_status
_closed_reason = closed_reason
_detect_trend = detect_trend
_deep_reason_base = deep_reason_base
_trend_analysis_section = trend_analysis_section

# ═══════════════════════════════════════════════════
# Ticker 配置 — 新浪财经（实时快照）
# ═══════════════════════════════════════════════════

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

PSEUDO_INDICES = {"gb_sox"}  # Sina: gb_前缀但显示为指数

# ═══════════════════════════════════════════════════
# Ticker 配置 — Yahoo Finance v8（收盘日报）
# ═══════════════════════════════════════════════════

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

# 带中文名的显示名（日报用）
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

# ═══════════════════════════════════════════════════
# 板块分组
# ═══════════════════════════════════════════════════

SECTORS: dict[str, set[str]] = {
    "💾 半导体": {"NVDA", "AMD", "AVGO", "QCOM", "ARM", "TSM", "ASML", "MRVL", "TXN", "INTC", "SMCI"},
    "☁️ 软件/云": {"MSFT", "CRM", "ADBE", "ORCL", "NOW", "SNOW", "MDB", "PANW", "CRWD", "PLTR"},
    "🛒 消费科技": {"AAPL", "AMZN", "TSLA", "GOOGL", "META", "NFLX", "UBER", "SHOP"},
    "🇨🇳 中概": {"BABA", "JD", "PDD", "BIDU", "NIO", "LI", "XPEV"},
}

# 科技板块重点股（Sina 格式，用于 --tech-only）
TECH_FOCUS = [
    "gb_nvda", "gb_tsla", "gb_avgo", "gb_qcom", "gb_arm",
    "gb_amd", "gb_smci", "gb_pltr", "gb_asml", "gb_tsm",
    "gb_mrvl", "gb_now", "gb_panw", "gb_crowd",
]

# 核心展示股（日报 🔍 核心科技股 展示顺序）
DISPLAY_PRIORITY = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA",
    "AMD", "AVGO", "INTC", "QCOM", "ARM", "TSM", "ASML", "SNOW", "BABA",
]

# ── display_name 适配 ──

def _display_name(stock: StockQuote) -> str:
    """获取带中文名的显示名，如 'NVDA 英伟达'。兼容 ticker 大小写。"""
    return YAHOO_STOCKS_CN.get(stock.ticker.upper(), stock.name)
