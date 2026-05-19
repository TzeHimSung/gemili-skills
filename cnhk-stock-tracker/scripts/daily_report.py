#!/usr/bin/env python3
"""
中港股收盘日报 — Yahoo Finance v8 API
覆盖 A 股芯片半导体 + 港股科技 / LLM 概念
用法:
    python3 scripts/daily_report.py              # 全量日报
    python3 scripts/daily_report.py --a-only     # 仅 A 股芯片
    python3 scripts/daily_report.py --hk-only    # 仅港股科技
    python3 scripts/daily_report.py --json       # JSON 输出
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
    YAHOO_A_STOCKS, YAHOO_HK_STOCKS, YAHOO_STOCKS, YAHOO_INDICES,
    YAHOO_STOCKS_CN, SECTORS, DISPLAY_PRIORITY,
    StockQuote, IndexQuote, DailyBar, market_hours_display, _check_market_status, _closed_reason,
    _markets_from_tickers, _filter_quotes_by_markets,
)
from analysis import (
    _icon, _pct_str, _display_name,
    _fifty_two_week_text, _reason_brief,
    _index_narrative, _overview_narrative,
    _key_dynamics, _one_line_summary, _trend_analysis_section,
)

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d"


# ═══════════════════════════════════════════════════
# Yahoo v8 fetching (curl — Python requests 可能被封)
# ═══════════════════════════════════════════════════

def _yahoo_fetch_one(ticker: str) -> dict | None:
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


def _valid_ohlcv_indices(result: dict) -> list[int]:
    """返回 Yahoo timestamp/quote 数组中 close/high/low 对齐且非空的 bar 下标。"""
    timestamps = result.get("timestamp", [])
    quotes = result["indicators"]["quote"][0]
    highs = quotes.get("high", [])
    lows = quotes.get("low", [])
    closes = quotes.get("close", [])
    valid = []
    for i, ts in enumerate(timestamps):
        if ts is None:
            continue
        if i >= len(closes) or closes[i] is None:
            continue
        if i >= len(highs) or highs[i] is None:
            continue
        if i >= len(lows) or lows[i] is None:
            continue
        valid.append(i)
    return valid


def _extract_history(ticker: str, result: dict) -> list:
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
    for i in _valid_ohlcv_indices(result):
        ts = timestamps[i]
        o = opens[i] if i < len(opens) and opens[i] is not None else 0
        h = highs[i]
        l = lows[i]
        c = closes[i]
        v = int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0

        date_str = dt.fromtimestamp(ts).strftime("%Y-%m-%d")
        bars.append(DailyBar(date=date_str, open=round(o, 2), high=round(h, 2),
                             low=round(l, 2), close=round(c, 2), volume=v))
    return bars


def _parse_yahoo_result(ticker: str, result: dict) -> StockQuote | IndexQuote | None:
    meta = result["meta"]
    quotes = result["indicators"]["quote"][0]
    valid_indices = _valid_ohlcv_indices(result)
    if len(valid_indices) < 2:
        return None

    prev_i, latest_i = valid_indices[-2], valid_indices[-1]
    latest = quotes["close"][latest_i]
    prev = quotes["close"][prev_i]
    change_pct = ((latest - prev) / prev) * 100 if prev else 0
    change_amt = latest - prev

    now = datetime.now().isoformat(timespec="seconds")
    name = meta.get("shortName") or meta.get("longName") or YAHOO_STOCKS.get(ticker, ticker)

    if ticker.startswith("^") or ticker in YAHOO_INDICES:
        # 指数（上证/深证/恒生 等）。不要仅凭 .SS/.SZ 后缀把用户自定义 A 股误归类为指数。
        return IndexQuote(
            ticker=ticker, name=name, price=latest,
            change_pct=change_pct, change_amt=change_amt,
            fetched_at=now, source="yahoo",
            time_str=str(result["timestamp"][latest_i]) if result.get("timestamp") else "",
        )

    volumes = quotes.get("volume", [])
    vol = int(volumes[latest_i]) if latest_i < len(volumes) and volumes[latest_i] is not None else 0
    history = _extract_history(ticker, result)

    return StockQuote(
        ticker=ticker, name=name, price=latest,
        change_pct=change_pct, change_amt=change_amt,
        prev_close=prev,
        high=float(quotes["high"][latest_i] or 0),
        low=float(quotes["low"][latest_i] or 0),
        high_52w=float(meta.get("fiftyTwoWeekHigh", 0)),
        low_52w=float(meta.get("fiftyTwoWeekLow", 0)),
        volume=vol,
        time_str=str(result["timestamp"][latest_i]) if result.get("timestamp") else "",
        fetched_at=now, source="yahoo",
        history=history,
    )


def _yahoo_fetch_all(
    stock_tickers: list[str], index_tickers: list[str],
) -> tuple[list[StockQuote], list[IndexQuote]]:
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
        if i < len(all_tickers) - 1:
            _time.sleep(0.35)
    return stocks, indices


# ═══════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════

def _index_table(indices: list[IndexQuote]) -> str:
    """🏛 大盘概览 表格。"""
    lines = ["| 指数 | 收盘价 | 涨跌幅 |", "|---|---|---|"]
    for i in indices:
        lines.append(f"| {i.name} | {i.price:,.2f} | {_icon(i.change_pct)} {_pct_str(i.change_pct)} |")
    return "\n".join(lines)


def _core_tech_table(stocks: list[StockQuote], top_n: int = 12) -> str:
    """🔍 核心科技股 表格 — 带 52周位置。"""
    lines = ["| 股票 | 收盘价 | 涨跌幅 | 52周位置 |", "|---|---|---|---|"]
    stock_map = {s.ticker: s for s in stocks}
    shown = set()

    for tk in DISPLAY_PRIORITY:
        s = stock_map.get(tk)
        if s and tk not in shown:
            shown.add(tk)
            name = _display_name(s)
            pos = _fifty_two_week_text(s)
            lines.append(
                f"| {name} | {s.price:.2f} | {_icon(s.change_pct)} {_pct_str(s.change_pct)} | {pos} |"
            )
        if len(shown) >= top_n:
            break

    return "\n".join(lines)


def _movers_section(stocks: list[StockQuote], n: int = 5) -> str:
    """🔥 科技板块异动 — 涨幅前五 + 跌幅前五。"""
    sorted_stocks = sorted(stocks, key=lambda s: s.change_pct, reverse=True)
    gainers = sorted_stocks[:n]
    losers = sorted([s for s in stocks if s.change_pct < 0], key=lambda s: s.change_pct)[:n]
    if not losers:
        losers = sorted_stocks[-n:][::-1]

    lines = ["🔥 科技板块异动", ""]

    lines.append("🟢 涨幅前五")
    lines.append("| 股票 | 收盘价 | 涨跌幅 | 原因简述 |")
    lines.append("|---|---|---|---|")
    for s in gainers:
        lines.append(f"| {_display_name(s)} | {s.price:.2f} | {_pct_str(s.change_pct)} | {_reason_brief(s, stocks)} |")
    lines.append("")

    lines.append("🔴 跌幅前五")
    lines.append("| 股票 | 收盘价 | 涨跌幅 | 原因简述 |")
    lines.append("|---|---|---|---|")
    for s in losers:
        lines.append(f"| {_display_name(s)} | {s.price:.2f} | {_pct_str(s.change_pct)} | {_reason_brief(s, stocks)} |")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

def _split_custom_tickers(raw: str) -> tuple[list[str], list[str]]:
    tickers = [part.strip() for part in raw.split(",") if part.strip()]
    stock_tk = [ticker for ticker in tickers if not ticker.startswith("^")]
    idx_tk = [ticker for ticker in tickers if ticker.startswith("^")]
    return stock_tk, idx_tk


def main():
    import argparse
    ap = argparse.ArgumentParser(description="中港股收盘日报 (Yahoo v8)")
    ap.add_argument("--a-only", action="store_true")
    ap.add_argument("--hk-only", action="store_true")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    data_dir = Path(args.data_dir); data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    if args.tickers:
        stock_tk, idx_tk = _split_custom_tickers(args.tickers)
    elif args.a_only:
        stock_tk = list(YAHOO_A_STOCKS.keys())
        idx_tk = [k for k in YAHOO_INDICES if k.endswith(".SS") or k.endswith(".SZ")]
    elif args.hk_only:
        stock_tk = list(YAHOO_HK_STOCKS.keys())
        idx_tk = [k for k in YAHOO_INDICES if k.startswith("^")]
    else:
        stock_tk = list(YAHOO_STOCKS.keys())
        idx_tk = list(YAHOO_INDICES.keys())

    if not args.quiet:
        print(f"📡 Yahoo v8 {len(idx_tk)}指数 + {len(stock_tk)}股 ...", file=sys.stderr)

    stocks, indices = _yahoo_fetch_all(stock_tk, idx_tk)

    if not args.quiet:
        print(f"✅ {len(indices)}指数 + {len(stocks)}股", file=sys.stderr)

    requested_markets = _markets_from_tickers(stock_tk, idx_tk)
    status = _check_market_status(stocks, indices, requested_markets=requested_markets)
    partial_market_notice = ""
    if status["open"] and status.get("open_markets"):
        open_markets = set(status["open_markets"])
        if open_markets != requested_markets:
            stocks, indices = _filter_quotes_by_markets(stocks, indices, open_markets)
            partial_market_notice = f"⚠️ {'、'.join(status.get('closed_markets', []))}休市，本报告仅展示{'、'.join(status['open_markets'])}有效行情。"

    report_data = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "market_open": status["open"],
        "last_trade_date": str(status["last_trade_date"]) if status["last_trade_date"] else None,
        "market_hours": status["hours"],
        "requested_markets": sorted(requested_markets),
        "open_markets": status.get("open_markets", []),
        "closed_markets": status.get("closed_markets", []),
        "data_issue": status.get("data_issue", False),
        "market_reason": status.get("reason", ""),
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
        json.dumps(report_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(report_data, ensure_ascii=False, indent=2)); return

    # ── 休市 / 数据异常处理 ──
    if not status["open"]:
        days_behind = (date.today() - status["last_trade_date"]).days if status["last_trade_date"] else 999
        reason = status.get("reason") or _closed_reason(
            status["last_trade_date"] or date.today(), days_behind, "中港"
        )
        if status.get("data_issue"):
            section_title = "## ⚠️ 数据异常"
            body = f"请求的中港市场行情不完整：{reason}。为避免静默降级或混入旧数据，本次不生成正常收盘日报。"
        else:
            section_title = "## 🏖️ 市场休市"
            body = f"昨晚中港市场未开盘。{reason}。"
        report = [
            f"📊 中港股收盘日报 — {now.strftime('%Y年%m月%d日')}（周{'一二三四五六日'[now.weekday()]}）",
            "",
            section_title,
            "",
            body,
            "",
            f"⏰ 常规交易时段：\n{status['hours']}",
            "",
            "---",
            f"📡 数据来源：Yahoo Finance v8 API | 🤖 Hermes Agent 自动日报",
        ]
        md = "\n".join(report)
        (data_dir / "daily_report.md").write_text(md, encoding="utf-8")
        print(md)
        return

    # ═══════════════════════════════════════════════════
    # Markdown 日报
    # ═══════════════════════════════════════════════════

    date_str = now.strftime("%Y年%m月%d日")
    weekday = "一二三四五六日"[now.weekday()]

    report = []
    report.append(f"📊 中港股收盘日报 — {date_str}（周{weekday}）")
    report.append("")
    report.append(f"⏰ 交易时段：\n{status['hours']}")
    if partial_market_notice:
        report.append("")
        report.append(partial_market_notice)
    report.append("")

    report.append("🏛 大盘概览")
    report.append("")
    report.append(_index_table(indices))
    report.append("")
    report.append(_index_narrative(indices))
    report.append("")

    report.append("🔍 核心科技股")
    report.append("")
    report.append(_core_tech_table(stocks))
    report.append("")

    report.append("表现综述")
    report.append("")
    report.append(_overview_narrative(stocks, indices))
    report.append("")

    report.append(_movers_section(stocks))
    report.append("")

    trend_section = _trend_analysis_section(stocks)
    if trend_section:
        report.append(trend_section)
        report.append("")

    dynamics = _key_dynamics(stocks, indices)
    if dynamics:
        report.append("🧠 关键动态")
        report.append("")
        for i, d in enumerate(dynamics, 1):
            report.append(f"{i}. {d}")
        report.append("")

    report.append("📈 一句话总结")
    report.append("")
    report.append(_one_line_summary(stocks, indices))
    report.append("")

    report.append("---")
    report.append(
        f"📡 数据来源：Yahoo Finance v8 API | ⏰ 数据时间：{date_str} 收盘 "
        f"| 🤖 报告生成：Hermes Agent 自动日报"
    )

    md = "\n".join(report)
    (data_dir / "daily_report.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
