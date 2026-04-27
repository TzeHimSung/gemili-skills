#!/usr/bin/env python3
"""
美股收盘日报 — Yahoo Finance v8 API
用法:
    python3 scripts/daily_report.py              # 全量日报
    python3 scripts/daily_report.py --tech-only   # 仅科技板块
    python3 scripts/daily_report.py --json        # JSON 输出

输出:
    data/daily_report.json    # JSON
    data/daily_report.md      # Markdown 日报
"""

import json
import subprocess
import sys
import time as _time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    YAHOO_STOCKS, YAHOO_INDICES, YAHOO_STOCKS_CN, SECTORS,
    StockQuote, IndexQuote, DailyBar,
)
from analysis import (
    _icon, _pct_str, _display_name,
    _fifty_two_week_text, _reason_brief,
    _index_narrative, _overview_narrative,
    _key_dynamics, _one_line_summary, _trend_analysis_section,
)

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d"


# ═══════════════════════════════════════════════════
# Yahoo v8 fetching (curl — Python requests 被封 403)
# ═══════════════════════════════════════════════════

def _yahoo_fetch_one(ticker: str) -> dict | None:
    """用 curl 抓取单个 ticker 的 5 天数据。"""
    url = YAHOO_CHART.format(ticker=ticker)
    try:
        result = subprocess.run(
            ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", url],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        data = json.loads(result.stdout)
        return data["chart"]["result"][0]
    except Exception:
        return None


def _extract_history(result: dict) -> list:
    """从 Yahoo 响应中提取 DailyBar 历史数据。"""
    from datetime import datetime as dt
    timestamps = result.get("timestamp", [])
    quotes = result["indicators"]["quote"][0]
    opens = quotes.get("open", [])
    highs = quotes.get("high", [])
    lows = quotes.get("low", [])
    closes = quotes.get("close", [])
    volumes = quotes.get("volume", [])

    bars = []
    for i, ts in enumerate(timestamps):
        o = opens[i] if i < len(opens) and opens[i] is not None else 0
        h = highs[i] if i < len(highs) and highs[i] is not None else 0
        l = lows[i] if i < len(lows) and lows[i] is not None else 0
        c = closes[i] if i < len(closes) and closes[i] is not None else 0
        v = int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0

        if o == 0 and c == 0:
            continue

        date_str = dt.fromtimestamp(ts).strftime("%Y-%m-%d")
        bars.append(DailyBar(date=date_str, open=round(o, 2), high=round(h, 2),
                             low=round(l, 2), close=round(c, 2), volume=v))
    return bars


def _parse_yahoo_result(ticker: str, result: dict) -> StockQuote | IndexQuote | None:
    """解析 Yahoo v8 返回为 StockQuote 或 IndexQuote。"""
    meta = result["meta"]
    quotes = result["indicators"]["quote"][0]
    closes = [c for c in quotes["close"] if c is not None]

    if len(closes) < 2:
        return None

    latest = closes[-1]
    prev = closes[-2]
    change_pct = ((latest - prev) / prev) * 100 if prev else 0
    change_amt = latest - prev

    now = datetime.now().isoformat(timespec="seconds")
    name = meta.get("shortName") or meta.get("longName") or YAHOO_STOCKS.get(ticker, ticker)

    if ticker.startswith("^"):
        return IndexQuote(
            ticker=ticker, name=name, price=latest,
            change_pct=change_pct, change_amt=change_amt,
            fetched_at=now, source="yahoo",
        )

    # Volume: take the latest day's volume
    volumes = [v for v in quotes.get("volume", []) if v is not None]
    vol = int(volumes[-1]) if volumes else 0
    history = _extract_history(result)

    return StockQuote(
        ticker=ticker, name=name, price=latest,
        change_pct=change_pct, change_amt=change_amt,
        prev_close=prev,
        high=float(quotes["high"][-1] or 0),
        low=float(quotes["low"][-1] or 0),
        high_52w=float(meta.get("fiftyTwoWeekHigh", 0)),
        low_52w=float(meta.get("fiftyTwoWeekLow", 0)),
        volume=vol,
        time_str=str(result["timestamp"][-1]) if result.get("timestamp") else "",
        fetched_at=now, source="yahoo",
        history=history,
    )


def _yahoo_fetch_all(
    stock_tickers: list[str],
    index_tickers: list[str],
) -> tuple[list[StockQuote], list[IndexQuote]]:
    """批量抓取 Yahoo v8，逐个请求（避免 rate limit）。"""
    stocks, indices = [], []

    all_tickers = index_tickers + stock_tickers
    for i, tk in enumerate(all_tickers):
        result = _yahoo_fetch_one(tk)
        if result is None:
            print(f"  ⚠ {tk} 抓取失败", file=sys.stderr)
            continue

        parsed = _parse_yahoo_result(tk, result)
        if parsed is None:
            continue

        if isinstance(parsed, IndexQuote):
            indices.append(parsed)
        else:
            stocks.append(parsed)

        # 避免 rate limit
        if i < len(all_tickers) - 1:
            _time.sleep(0.35)

    return stocks, indices


# ═══════════════════════════════════════════════════
# Market status detection
# ═══════════════════════════════════════════════════

def _is_us_dst(d: date) -> bool:
    """判断给定日期是否在美国夏令时期间。
    美国夏令时：3月第二个周日 02:00 → 11月第一个周日 02:00"""
    # 3月第二个周日
    march_second_sun = date(d.year, 3, 1)
    while march_second_sun.weekday() != 6:  # 0=Mon, 6=Sun
        march_second_sun += timedelta(days=1)
    march_second_sun += timedelta(days=7)  # second Sunday

    # 11月第一个周日
    nov_first_sun = date(d.year, 11, 1)
    while nov_first_sun.weekday() != 6:
        nov_first_sun += timedelta(days=1)

    return march_second_sun <= d < nov_first_sun


def _market_hours_str(trade_date: date, with_date: bool = True) -> str:
    """返回交易日 + 美东/北京时间交易时段描述。
    形如: 2026年04月24日（周五）美东 EDT 9:30–16:00 / 北京 CST 21:30–次日04:00"""
    if _is_us_dst(trade_date):
        tz_part = "美东 EDT 9:30–16:00 / 北京 CST 21:30–次日04:00"
    else:
        tz_part = "美东 EST 9:30–16:00 / 北京 CST 22:30–次日05:00"

    if not with_date:
        return tz_part

    weekday_cn = "一二三四五六日"[trade_date.weekday()]
    date_part = trade_date.strftime(f"%Y年%m月%d日（周{weekday_cn}）")
    return f"{date_part} {tz_part}"


def _check_market_status(
    stocks: list[StockQuote],
    indices: list[IndexQuote],
) -> dict:
    """根据抓取数据判断最近一个交易日是否在昨晚（北京时间判断）。
    
    Returns:
        {"open": bool, "last_trade_date": date|None, "reason": str, "hours": str}
    """
    all_items = stocks + indices
    if not all_items:
        return {"open": False, "last_trade_date": None,
                "reason": "无行情数据", "hours": "未知"}

    # 从任意股票/指数取 Unix 时间戳
    timestamps = []
    for item in all_items:
        ts = getattr(item, "time_str", "")
        if ts and ts.lstrip("-").isdigit():
            timestamps.append(int(ts))
    if not timestamps:
        return {"open": False, "last_trade_date": None,
                "reason": "无有效时间戳", "hours": "未知"}

    latest_ts = max(timestamps)
    latest_date = datetime.fromtimestamp(latest_ts).date()
    today = date.today()
    yesterday = today - timedelta(days=1)  # "昨晚"美东时间对应日期

    # ═══════════════════════════════════════════════════
    # 核心判断：昨晚（美东时间）是不是交易日？
    # 北京时间早上 7:00，"昨晚" = 昨天美东日期。
    # 例：周一 7:00 北京 → 周日美东 → 周末休市
    #     周二 7:00 北京 → 周一美东 → 开盘
    # ═══════════════════════════════════════════════════

    # ── 昨晚是周末 → 必定休市 ──
    if yesterday.weekday() >= 5:
        weekday_cn = "一二三四五六日"[yesterday.weekday()]
        hours = _market_hours_str(today, with_date=False)
        return {"open": False, "last_trade_date": latest_date,
                "reason": f"周末休市（昨晚为美东周{weekday_cn}）",
                "hours": hours}

    # ── 昨晚是工作日 → 检查是否为节假日 ──
    # 美股假期（2026-2027）
    us_holidays = {
        date(2026,1,1):   "元旦",        date(2027,1,1):   "元旦",
        date(2026,1,19):  "马丁·路德·金纪念日", date(2027,1,18): "马丁·路德·金纪念日",
        date(2026,2,16):  "总统日",      date(2027,2,15):  "总统日",
        date(2026,4,3):   "耶稣受难日",  date(2027,3,26):  "耶稣受难日",
        date(2026,5,25):  "阵亡将士纪念日", date(2027,5,31): "阵亡将士纪念日",
        date(2026,6,19):  "六月节",      date(2027,6,19):  "六月节",
        date(2026,7,3):   "独立日（补休）", date(2027,7,5): "独立日（补休）",
        date(2026,9,7):   "劳动节",      date(2027,9,6):   "劳动节",
        date(2026,11,26): "感恩节",      date(2027,11,25): "感恩节",
        date(2026,12,25): "圣诞节",      date(2027,12,25): "圣诞节",
    }
    if yesterday in us_holidays:
        hours = _market_hours_str(today, with_date=False)
        return {"open": False, "last_trade_date": latest_date,
                "reason": f"节假日休市（{us_holidays[yesterday]}）",
                "hours": hours}

    # ── 昨晚是普通交易日 → 开盘 → 显示最新数据 ──
    hours = _market_hours_str(latest_date)
    return {"open": True, "last_trade_date": latest_date,
            "reason": "", "hours": hours}


def _closed_reason(latest_date: date, days_behind: int, market: str = "美股") -> str:
    """根据最近交易日推断休市原因。"""
    weekday_cn = "一二三四五六日"[latest_date.weekday()]

    # 如果是周末
    if latest_date.weekday() >= 5:
        return f"最近交易日为周{weekday_cn}（{latest_date}），{market}周末休市"

    # 工作日但未开市 → 判断是否节假日
    # 美股假期（2026）
    us_holidays_2026 = {
        date(2026,1,1):   "元旦",
        date(2026,1,19):  "马丁·路德·金纪念日",
        date(2026,2,16):  "总统日",
        date(2026,4,3):   "耶稣受难日",
        date(2026,5,25):  "阵亡将士纪念日",
        date(2026,6,19):  "六月节",
        date(2026,7,3):   "独立日（补休）",
        date(2026,9,7):   "劳动节",
        date(2026,11,26): "感恩节",
        date(2026,12,25): "圣诞节",
    }
    # 中国假期（2026，含调休影响的工作日休市）
    cn_holidays_2026 = {
        date(2026,1,1):   "元旦",
        date(2026,1,2):   "元旦假期",
        date(2026,2,16):  "春节假期",
        date(2026,2,17):  "春节假期",
        date(2026,2,18):  "春节假期",
        date(2026,2,19):  "春节假期",
        date(2026,2,20):  "春节假期",
        date(2026,4,6):   "清明节（补休）",
        date(2026,5,1):   "劳动节假期",
        date(2026,5,4):   "劳动节假期",
        date(2026,5,5):   "劳动节假期",
        date(2026,6,19):  "端午节",
        date(2026,9,25):  "中秋节",
        date(2026,10,1):  "国庆节假期",
        date(2026,10,2):  "国庆节假期",
        date(2026,10,5):  "国庆节假期",
        date(2026,10,6):  "国庆节假期",
        date(2026,10,7):  "国庆节假期",
    }
    # 港股假期（2026，含中西方假期）
    hk_holidays_2026 = {
        date(2026,1,1):   "元旦",
        date(2026,2,16):  "农历年初一",
        date(2026,2,17):  "农历年初二",
        date(2026,2,18):  "农历年初三",
        date(2026,4,3):   "耶稣受难日",
        date(2026,4,6):   "复活节星期一",
        date(2026,4,7):   "清明节",
        date(2026,5,1):   "劳动节",
        date(2026,5,25):  "佛诞",
        date(2026,6,19):  "端午节",
        date(2026,7,1):   "香港特区成立纪念日",
        date(2026,9,25):  "中秋节翌日",
        date(2026,10,1):  "国庆节",
        date(2026,10,26): "重阳节",
        date(2026,12,25): "圣诞节",
    }

    if market == "美股":
        holidays = us_holidays_2026
    elif market == "A股":
        holidays = cn_holidays_2026
    elif market == "港股":
        holidays = hk_holidays_2026
    else:
        holidays = {}

    if latest_date in holidays:
        return f"最近交易日 {latest_date}（周{weekday_cn}），{market}因**{holidays[latest_date]}**休市"

    # 工作日非假期但未开市 → 异常
    return f"最近交易日 {latest_date}（周{weekday_cn}），距今 {days_behind} 天，可能为临时休市或数据延迟"


# ═══════════════════════════════════════════════════
# Formatting — 4/24 风格
# ═══════════════════════════════════════════════════

def _index_table(indices: list[IndexQuote]) -> str:
    """🏛 大盘概览 表格。"""
    lines = ["| 指数 | 收盘价 | 涨跌幅 |", "|---|---|---|"]
    for i in indices:
        lines.append(f"| {i.name} | {i.price:,.2f} | {_icon(i.change_pct)} {_pct_str(i.change_pct)} |")
    return "\n".join(lines)


def _core_tech_table(stocks: list[StockQuote], top_n: int = 10) -> str:
    """🔍 核心科技股 表格 — 带 52周位置。"""
    lines = ["| 股票 | 收盘价 | 涨跌幅 | 52周位置 |", "|---|---|---|---|"]
    # 按市值/重要性排序：七大科技 + 重要半导体
    priority = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA",
                "AMD", "AVGO", "INTC", "QCOM", "ARM", "TSM", "ASML", "SNOW", "BABA"]
    stock_map = {s.ticker.upper(): s for s in stocks}
    shown = set()

    for tk in priority:
        s = stock_map.get(tk)
        if s and tk not in shown:
            shown.add(tk)
            name = _display_name(s)
            pos = _fifty_two_week_text(s)
            lines.append(
                f"| {name} | ${s.price:.2f} | {_icon(s.change_pct)} {_pct_str(s.change_pct)} | {pos} |"
            )
        if len(shown) >= top_n:
            break

    return "\n".join(lines)


def _movers_section(stocks: list[StockQuote], n: int = 5) -> str:
    """🔥 科技板块异动 — 涨幅前五 + 跌幅前五，带原因简述。"""
    sorted_stocks = sorted(stocks, key=lambda s: s.change_pct, reverse=True)
    gainers = sorted_stocks[:n]
    # 跌幅榜：只取实际下跌的
    losers = sorted([s for s in stocks if s.change_pct < 0],
                    key=lambda s: s.change_pct)[:n]
    if not losers:
        # 如果全部上涨，取涨幅最小的
        losers = sorted_stocks[-n:][::-1]

    lines = ["🔥 科技板块异动", ""]

    # ── 涨幅前五 ──
    lines.append("🟢 涨幅前五")
    lines.append("| 股票 | 收盘价 | 涨跌幅 | 原因简述 |")
    lines.append("|---|---|---|---|")
    for s in gainers:
        name = _display_name(s)
        reason = _reason_brief(s, stocks)
        lines.append(f"| {name} | ${s.price:.2f} | {_pct_str(s.change_pct)} | {reason} |")
    lines.append("")

    # ── 跌幅前五 ──
    lines.append("🔴 跌幅前五")
    lines.append("| 股票 | 收盘价 | 涨跌幅 | 原因简述 |")
    lines.append("|---|---|---|---|")
    for s in losers:
        name = _display_name(s)
        reason = _reason_brief(s, stocks)
        lines.append(f"| {name} | ${s.price:.2f} | {_pct_str(s.change_pct)} | {reason} |")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description="美股收盘日报 (Yahoo v8)")
    ap.add_argument("--tech-only", action="store_true")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    data_dir = Path(args.data_dir); data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    # 确定范围
    if args.tickers:
        stock_tk = [t.upper() for t in args.tickers.split(",") if not t.startswith("^")]
        idx_tk = [t for t in args.tickers.split(",") if t.startswith("^")]
    elif args.tech_only:
        stock_tk = list(YAHOO_STOCKS.keys())[:14]
        idx_tk = list(YAHOO_INDICES.keys())
    else:
        stock_tk = list(YAHOO_STOCKS.keys())
        idx_tk = list(YAHOO_INDICES.keys())

    if not args.quiet:
        print(f"📡 Yahoo v8 {len(idx_tk)}指数 + {len(stock_tk)}股 ...", file=sys.stderr)

    stocks, indices = _yahoo_fetch_all(stock_tk, idx_tk)

    if not args.quiet:
        print(f"✅ {len(indices)}指数 + {len(stocks)}股", file=sys.stderr)

    # ── 市场状态检测 ──
    status = _check_market_status(stocks, indices)

    # ── JSON ──
    report_data = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "market_open": status["open"],
        "last_trade_date": str(status["last_trade_date"]) if status["last_trade_date"] else None,
        "market_hours": status["hours"],
        "indices": [{"ticker": i.ticker, "name": i.name, "price": i.price,
                      "change_pct": i.change_pct} for i in indices],
        "stocks": [{"ticker": s.ticker, "name": s.name, "price": s.price,
                     "change_pct": s.change_pct, "volume": s.volume,
                     "high_52w": s.high_52w, "low_52w": s.low_52w,
                     "history_days": len(s.history),
                     "history": [{"date": b.date, "open": b.open, "high": b.high,
                                  "low": b.low, "close": b.close, "volume": b.volume}
                                 for b in s.history]} for s in stocks],
    }
    (data_dir / "daily_report.json").write_text(
        json.dumps(report_data, ensure_ascii=False, indent=2))
    if args.json:
        print(json.dumps(report_data, ensure_ascii=False, indent=2)); return

    # ── 休市处理 ──
    if not status["open"]:
        reason = status.get("reason", "休市")
        report = [
            f"📊 美股收盘日报 — {now.strftime('%Y年%m月%d日')}（周{'一二三四五六日'[now.weekday()]}）",
            "",
            "## 🏖️ 美股休市",
            "",
            f"昨晚美股未开盘。{reason}。",
            "",
            f"⏰ 常规交易时段：{status['hours']}",
            "",
            "---",
            f"📡 数据来源：Yahoo Finance v8 API | 🤖 Hermes Agent 自动日报",
        ]
        md = "\n".join(report)
        (data_dir / "daily_report.md").write_text(md)
        print(md)
        return

    # ═══════════════════════════════════════════════════
    # Markdown 日报 — 4/24 风格
    # ═══════════════════════════════════════════════════

    trade_date_str = status["last_trade_date"].strftime("%Y年%m月%d日") if status["last_trade_date"] else now.strftime("%Y年%m月%d日")
    date_str = now.strftime("%Y年%m月%d日")
    weekday = "一二三四五六日"[now.weekday()]

    # 摘要行
    idx_summary = " | ".join(
        f"{i.name} {i.change_sign}{i.change_pct:.2f}%" for i in indices
    )

    report = []

    # ═══ 标题 ═══
    report.append(f"📊 美股收盘日报 — {date_str}（周{weekday}）")
    report.append("")
    report.append(f"⏰ 交易时段：{status['hours']}")
    report.append("")

    # ═══ 🏛 大盘概览 ═══
    report.append("🏛 大盘概览")
    report.append("")
    report.append(_index_table(indices))
    report.append("")
    report.append(_index_narrative(indices))
    report.append("")

    # ═══ 🔍 核心科技股 ═══
    report.append("🔍 核心科技股")
    report.append("")
    report.append(_core_tech_table(stocks))
    report.append("")

    # ═══ 表现综述 ═══
    report.append("表现综述")
    report.append("")
    report.append(_overview_narrative(stocks, indices))
    report.append("")

    # ═══ 🔥 科技板块异动 ═══
    report.append(_movers_section(stocks))
    report.append("")

    # ═══ 📈 走势深度分析 ═══
    trend_section = _trend_analysis_section(stocks)
    if trend_section:
        report.append(trend_section)
        report.append("")

    # ═══ 🧠 关键动态 ═══
    dynamics = _key_dynamics(stocks, indices)
    if dynamics:
        report.append("🧠 关键动态")
        report.append("")
        for i, d in enumerate(dynamics, 1):
            report.append(f"{i}. {d}")
        report.append("")

    # ═══ 📈 一句话总结 ═══
    report.append("📈 一句话总结")
    report.append("")
    report.append(_one_line_summary(stocks, indices))
    report.append("")

    # ═══ Footer ═══
    report.append("---")
    report.append(
        f"📡 数据来源：Yahoo Finance v8 API | ⏰ 数据时间：{date_str} 美股收盘 "
        f"| 🤖 报告生成：Hermes Agent 自动日报"
    )

    md = "\n".join(report)
    (data_dir / "daily_report.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
