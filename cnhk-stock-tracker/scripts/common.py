"""
中港股行情追踪 — ticker 配置 + 板块分组
数据结构和工具函数从 shared/stock_tracker_lib 导入。
"""
import sys
from datetime import date
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


def _market_from_ticker(ticker: str) -> str | None:
    """根据 Yahoo ticker 判断所属市场。"""
    if ticker.startswith("^") or ticker.endswith(".HK"):
        return "港股"
    if ticker.endswith(".SS") or ticker.endswith(".SZ"):
        return "A股"
    return None


MARKET_ORDER = ("A股", "港股")


def _sort_markets(markets: set[str]) -> list[str]:
    """稳定输出市场顺序，避免 JSON/Markdown 因 set 顺序漂移。"""
    return [market for market in MARKET_ORDER if market in markets]


def _markets_from_quotes(stocks, indices) -> set[str]:
    markets: set[str] = set()
    for item in list(stocks) + list(indices):
        market = _market_from_ticker(getattr(item, "ticker", ""))
        if market:
            markets.add(market)
    # 无法识别时按混合中港处理，避免单边假期误判整份日报休市。
    return markets or {"A股", "港股"}


def _markets_from_tickers(stock_tickers, index_tickers) -> set[str]:
    """根据本次请求的 ticker 范围判断应覆盖哪些市场。"""
    markets: set[str] = set()
    for ticker in list(stock_tickers) + list(index_tickers):
        market = _market_from_ticker(str(ticker))
        if market:
            markets.add(market)
    return markets or {"A股", "港股"}


def _filter_quotes_by_markets(stocks, indices, markets: set[str]):
    """只保留属于指定市场的行情，避免把单边休市旧数据混入正常日报。"""
    filtered_stocks = [s for s in stocks if _market_from_ticker(getattr(s, "ticker", "")) in markets]
    filtered_indices = [i for i in indices if _market_from_ticker(getattr(i, "ticker", "")) in markets]
    return filtered_stocks, filtered_indices


def _holidays_for_markets(markets: set[str]) -> dict[date, str]:
    """返回会让请求范围整体休市的假期表。

    A-only 使用 A 股假期，HK-only 使用港股假期；混合中港日报只有在
    A 股与港股同日都休市时才整体休市，避免港股单边假期误关 A 股日报。
    """
    if markets == {"A股"}:
        return CN_HOLIDAYS
    if markets == {"港股"}:
        return HK_HOLIDAYS

    common_dates = set(CN_HOLIDAYS).intersection(HK_HOLIDAYS)
    return {
        d: (
            CN_HOLIDAYS[d]
            if CN_HOLIDAYS[d] == HK_HOLIDAYS[d]
            else f"A股：{CN_HOLIDAYS[d]} / 港股：{HK_HOLIDAYS[d]}"
        )
        for d in common_dates
    }


def _market_label(markets: set[str]) -> str:
    if markets == {"A股"}:
        return "A股"
    if markets == {"港股"}:
        return "港股"
    return "中港"


def _holidays_for_market(market: str) -> dict[date, str]:
    if market == "A股":
        return CN_HOLIDAYS
    if market == "港股":
        return HK_HOLIDAYS
    return _holidays_for_markets({market})


def _official_closed_reason(market: str, today: date) -> str:
    """返回单一市场的官方休市原因；空字符串表示今天应交易。"""
    weekday_cn = "一二三四五六日"[today.weekday()]
    if today.weekday() >= 5:
        return f"周末休市（今日为周{weekday_cn}）"
    holidays = _holidays_for_market(market)
    if today in holidays:
        return f"节假日休市（{holidays[today]}）"
    return ""


def _single_market_status(market: str, stocks, indices, today=None) -> dict:
    """按单一市场判断状态；无数据但官方休市时不误报为数据问题。"""
    if today is None:
        today = date.today()
    market_stocks, market_indices = _filter_quotes_by_markets(stocks, indices, {market})
    official_reason = _official_closed_reason(market, today)
    if not market_stocks and not market_indices and official_reason:
        return {
            "open": False,
            "last_trade_date": None,
            "reason": official_reason,
            "hours": _cnhk_market_hours_str(today, with_date=False),
        }
    return check_market_status(
        market_stocks, market_indices,
        hours_fn=_cnhk_market_hours_str,
        today=today,
        holidays=_holidays_for_market(market),
        market=market,
    )


def _check_market_status_wrapper(stocks, indices, today=None, requested_markets: set[str] | None = None):
    """中港股市场状态检测（按请求范围区分 A 股 / 港股假期表）。

    对混合中港日报逐市场判断：单边官方休市时仍允许另一边生成日报；
    但若请求范围包含的市场在应交易日无/旧行情，则标记 data_issue 并阻止静默降级。
    """
    if today is None:
        today = date.today()
    markets = set(requested_markets) if requested_markets else _markets_from_quotes(stocks, indices)
    markets = {m for m in markets if m in MARKET_ORDER} or {"A股", "港股"}

    if len(markets) == 1:
        market = next(iter(markets))
        status = _single_market_status(market, stocks, indices, today=today)
        status["by_market"] = {market: dict(status)}
        status["open_markets"] = [market] if status["open"] else []
        status["closed_markets"] = [] if status["open"] else [market]
        status["data_issue"] = (not status["open"] and not _official_closed_reason(market, today))
        return status

    by_market = {
        market: _single_market_status(market, stocks, indices, today=today)
        for market in _sort_markets(markets)
    }
    open_markets = {market for market, status in by_market.items() if status["open"]}
    closed_markets = set(markets) - open_markets
    data_issues = [
        f"{market}{status['reason']}"
        for market, status in by_market.items()
        if not status["open"] and not _official_closed_reason(market, today)
    ]
    latest_dates = [status["last_trade_date"] for status in by_market.values() if status.get("last_trade_date")]
    last_trade_date = max(latest_dates) if latest_dates else None

    if data_issues:
        return {
            "open": False,
            "last_trade_date": last_trade_date,
            "reason": "；".join(data_issues),
            "hours": _cnhk_market_hours_str(today, with_date=False),
            "by_market": by_market,
            "open_markets": _sort_markets(open_markets),
            "closed_markets": _sort_markets(closed_markets),
            "data_issue": True,
        }

    if open_markets:
        closed_reason_parts = [
            f"{market}{by_market[market]['reason']}"
            for market in _sort_markets(closed_markets)
            if by_market[market].get("reason")
        ]
        return {
            "open": True,
            "last_trade_date": last_trade_date,
            "reason": "；".join(closed_reason_parts),
            "hours": _cnhk_market_hours_str(last_trade_date or today),
            "by_market": by_market,
            "open_markets": _sort_markets(open_markets),
            "closed_markets": _sort_markets(closed_markets),
            "data_issue": False,
        }

    return {
        "open": False,
        "last_trade_date": last_trade_date,
        "reason": "；".join(
            f"{market}{by_market[market]['reason']}" for market in _sort_markets(closed_markets)
        ),
        "hours": _cnhk_market_hours_str(today, with_date=False),
        "by_market": by_market,
        "open_markets": [],
        "closed_markets": _sort_markets(closed_markets),
        "data_issue": False,
    }


def _closed_reason_wrapper(latest_date, days_behind, market="中港"):
    """中港股休市原因。"""
    return closed_reason(latest_date, days_behind, market)


_check_market_status = _check_market_status_wrapper
_closed_reason = _closed_reason_wrapper
