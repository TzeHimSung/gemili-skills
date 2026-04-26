"""
中港股行情追踪 — ticker 配置 + 板块分组
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
    check_market_status, closed_reason,
    CN_HOLIDAYS, HK_HOLIDAYS,
    detect_trend, CNHK_TREND_THRESHOLDS,
    deep_reason_base, trend_analysis_section,
)

# 为向后兼容导出别名
_icon = icon
_pct_str = pct_str
_fifty_two_week_text = fifty_two_week_text
_fifty_two_week_check = fifty_two_week_check
_check_market_status = check_market_status
_closed_reason = closed_reason
_detect_trend = detect_trend
_deep_reason_base = deep_reason_base
_trend_analysis_section = trend_analysis_section

# ═══════════════════════════════════════════════════
# Ticker 配置 — 新浪财经（实时快照 / snapshot.py）
# ═══════════════════════════════════════════════════

SINA_A_STOCKS: dict[str, str] = {
    "sh688981": "中芯国际",     "sh688041": "海光信息",
    "sh688256": "寒武纪",       "sz002371": "北方华创",
    "sh603501": "韦尔股份",     "sh688008": "澜起科技",
    "sh688012": "中微公司",     "sh600584": "长电科技",
    "sz300782": "卓胜微",       "sh603986": "兆易创新",
    "sh688126": "沪硅产业",     "sh688347": "华虹公司",
    "sh688072": "拓荆科技",     "sz002049": "紫光国微",
}

SINA_HK_STOCKS: dict[str, str] = {
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

YAHOO_A_STOCKS: dict[str, str] = {
    "688981.SS": "中芯国际",     "688041.SS": "海光信息",
    "688256.SS": "寒武纪",       "002371.SZ": "北方华创",
    "603501.SS": "韦尔股份",     "688008.SS": "澜起科技",
    "688012.SS": "中微公司",     "600584.SS": "长电科技",
    "300782.SZ": "卓胜微",       "603986.SS": "兆易创新",
    "688126.SS": "沪硅产业",     "688347.SS": "华虹公司",
    "688072.SS": "拓荆科技",     "002049.SZ": "紫光国微",
}

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

# 合并 + 显示名
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
    "0700.HK", "1810.HK", "9988.HK", "3690.HK",
    "688981.SS", "688041.SS", "688256.SS", "002371.SZ",
    "9618.HK", "9999.HK", "1024.HK", "9888.HK",
    "603501.SS", "688012.SS", "688008.SS", "002049.SZ",
]

# ═══════════════════════════════════════════════════
# 市场时间（无 DST，固定北京时间）
# ═══════════════════════════════════════════════════

A_MARKET_HOURS = "A 股 9:30–11:30 / 13:00–15:00（北京时间）"
HK_MARKET_HOURS = "港股 9:30–12:00 / 13:00–16:00（北京时间）"


def market_hours_display() -> str:
    """返回交易时段描述。"""
    return f"{A_MARKET_HOURS}\n{HK_MARKET_HOURS}"


# ── display_name 适配 ──

def _display_name(stock: StockQuote) -> str:
    """获取带中文名的显示名。cnhk ticker 直接匹配（不转大小写）。"""
    return YAHOO_STOCKS_CN.get(stock.ticker, stock.name)


# ── 市场状态检测适配 ──

def _cnhk_market_hours_str(trade_date, with_date=True):
    """中港股交易时段（无 DST，始终北京时间）。"""
    from datetime import date
    if isinstance(trade_date, date):
        weekday_cn = "一二三四五六日"[trade_date.weekday()]
        date_part = trade_date.strftime(f"%Y年%m月%d日（周{weekday_cn}）")
    else:
        date_part = str(trade_date)

    tz_part = A_MARKET_HOURS + "\n" + HK_MARKET_HOURS
    if with_date:
        return f"{date_part}\n{tz_part}"
    return tz_part


def _check_market_status_wrapper(stocks, indices):
    """中港股市场状态检测（使用中港股时段函数）。"""
    return check_market_status(stocks, indices, hours_fn=_cnhk_market_hours_str)


def _closed_reason_wrapper(latest_date, days_behind, market="中港"):
    """中港股休市原因（使用合并假期表）。"""
    return closed_reason(latest_date, days_behind, market)


_check_market_status = _check_market_status_wrapper
_closed_reason = _closed_reason_wrapper
