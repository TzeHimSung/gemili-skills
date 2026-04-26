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
    StockQuote, IndexQuote, market_hours_display, _check_market_status,
)
from analysis import (
    _icon, _pct_str, _display_name,
    _fifty_two_week_text, _reason_brief,
    _index_narrative, _overview_narrative,
    _key_dynamics, _one_line_summary,
)

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"


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


def _parse_yahoo_result(ticker: str, result: dict) -> StockQuote | IndexQuote | None:
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

    if ticker.startswith("^") or ticker.endswith(".SS") or ticker.endswith(".SZ"):
        # 指数（上证/深证/恒生 等）
        if ticker.startswith("^") or ticker not in YAHOO_STOCKS:
            return IndexQuote(
                ticker=ticker, name=name, price=latest,
                change_pct=change_pct, change_amt=change_amt,
                fetched_at=now, source="yahoo",
            )

    volumes = [v for v in quotes.get("volume", []) if v is not None]
    vol = int(volumes[-1]) if volumes else 0

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
        stock_tk = [t for t in args.tickers.split(",") if not t.startswith("^")]
        idx_tk = [t for t in args.tickers.split(",") if t.startswith("^")]
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

    status = _check_market_status(stocks, indices)

    report_data = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "market_open": status["open"],
        "last_trade_date": str(status["last_trade_date"]) if status["last_trade_date"] else None,
        "market_hours": status["hours"],
        "indices": [{"ticker": i.ticker, "name": i.name, "price": i.price,
                      "change_pct": i.change_pct} for i in indices],
        "stocks": [{"ticker": s.ticker, "name": s.name, "price": s.price,
                     "change_pct": s.change_pct, "volume": s.volume,
                     "high_52w": s.high_52w, "low_52w": s.low_52w} for s in stocks],
    }
    (data_dir / "daily_report.json").write_text(json.dumps(report_data, ensure_ascii=False, indent=2))
    if args.json:
        print(json.dumps(report_data, ensure_ascii=False, indent=2)); return

    # ── 休市处理 ──
    if not status["open"]:
        report = [
            f"📊 中港股收盘日报 — {now.strftime('%Y年%m月%d日')}（周{'一二三四五六日'[now.weekday()]}）",
            "",
            "## 🏖️ 市场休市",
            "",
            f"昨晚中港市场未开盘。{status['reason']}。",
            "",
            f"⏰ 常规交易时段：\n{status['hours']}",
            "",
            "---",
            f"📡 数据来源：Yahoo Finance v8 API | 🤖 Hermes Agent 自动日报",
        ]
        print("\n".join(report))
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
    (data_dir / "daily_report.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
