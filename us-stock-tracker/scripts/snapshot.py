#!/usr/bin/env python3
"""新浪财经实时行情快照。用法见 SKILL.md。"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    http_get, UA, NO_PROXY,
    SINA_STOCKS, SINA_INDICES, PSEUDO_INDICES, TECH_FOCUS,
    StockQuote, IndexQuote,
)
from analysis import analyze, _pct_str, _icon

SINA_URL = "https://hq.sinajs.cn/list="
SINA_REFERER = "https://finance.sina.com.cn/"

# ── Sina fetching ────────────────────────────────────

def _fetch_sina_raw(tickers: list[str]) -> str:
    url = SINA_URL + ",".join(tickers)
    return http_get(url, referer=SINA_REFERER).text


def _parse_sina(raw: str) -> tuple[list[StockQuote], list[IndexQuote]]:
    stocks, indices = [], []
    now = datetime.now().isoformat(timespec="seconds")
    for line in raw.strip().split("\n"):
        if '=""' in line or not line.strip():
            continue
        m = re.match(r'var hq_str_([^=]+)="(.*)"\s*;?', line)
        if not m:
            continue
        ticker, fields = m.group(1), m.group(2).split(",")

        def _f(i):
            try: return float(fields[i])
            except: return 0.0

        if ticker.startswith("int_"):
            indices.append(IndexQuote(
                ticker=ticker, name=fields[0], price=_f(1),
                change_amt=_f(2), change_pct=_f(3),
                fetched_at=now, source="sina",
            ))
        else:
            stocks.append(StockQuote(
                ticker=ticker, name=fields[0], price=_f(1),
                change_pct=_f(2), time_str=fields[3] if len(fields) > 3 else "",
                change_amt=_f(4), prev_close=_f(5),
                high=_f(6), low=_f(7), high_52w=_f(8), low_52w=_f(9),
                volume=int(_f(10)), fetched_at=now, source="sina",
            ))
    return stocks, indices


# ── Formatting ───────────────────────────────────────

def _stock_table(stocks: list[StockQuote]) -> str:
    lines = ["| 股票 | 代码 | 现价 | 涨跌幅 | 52周高 | 52周低 |", "|---|---|---|---|---|---|"]
    for s in stocks:
        code = s.ticker.replace("gb_", "").upper()
        lines.append(
            f"| {s.name[:16]} | {code} | ${s.price:.2f} | "
            f"{_icon(s.change_pct)} {_pct_str(s.change_pct)} | "
            f"${s.high_52w:.1f} | ${s.low_52w:.1f} |"
        )
    return "\n".join(lines)


def _index_table(indices: list[IndexQuote]) -> str:
    lines = ["| 指数 | 最新 | 涨跌幅 |", "|---|---|---|"]
    for i in indices:
        lines.append(f"| {i.name} | {i.price:,.2f} | {_icon(i.change_pct)} {_pct_str(i.change_pct)} |")
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser(description="新浪财经实时快照")
    ap.add_argument("--tech-only", action="store_true")
    ap.add_argument("--tickers", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    data_dir = Path(args.data_dir); data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    if args.tickers:
        stock_tk = [t.strip() for t in args.tickers.split(",") if t.startswith("gb_")]
        idx_tk = [t.strip() for t in args.tickers.split(",") if t.startswith("int_")]
    elif args.tech_only:
        stock_tk = TECH_FOCUS; idx_tk = list(SINA_INDICES.keys())
    else:
        stock_tk = list(SINA_STOCKS.keys()); idx_tk = list(SINA_INDICES.keys())

    if not args.quiet:
        print(f"📡 Sina {len(stock_tk)}股 + {len(idx_tk)}指数 ...", file=sys.stderr)

    raw = _fetch_sina_raw(stock_tk + idx_tk)
    stocks, indices = _parse_sina(raw)

    # 分离伪指数
    pseudo = [s for s in stocks if s.ticker in PSEUDO_INDICES]
    real = [s for s in stocks if s.ticker not in PSEUDO_INDICES]
    all_idx = indices + [IndexQuote(ticker=s.ticker, name=s.name, price=s.price,
                                     change_pct=s.change_pct, change_amt=s.change_amt,
                                     fetched_at=s.fetched_at, source="sina") for s in pseudo]

    if not args.quiet:
        print(f"✅ {len(real)}股 + {len(all_idx)}指数", file=sys.stderr)

    # JSON
    snap = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "indices": [{"ticker": i.ticker, "name": i.name, "price": i.price,
                      "change_pct": i.change_pct} for i in all_idx],
        "stocks": [{"ticker": s.ticker, "name": s.name, "price": s.price,
                     "change_pct": s.change_pct, "volume": s.volume,
                     "high_52w": s.high_52w, "low_52w": s.low_52w} for s in real],
    }
    (data_dir / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps(snap, ensure_ascii=False, indent=2)); return

    # Markdown
    date_str = now.strftime("%m月%d日 %H:%M")
    report = [
        f"## 📊 美股实时快照 — {date_str}",
        "", "### 指数", "", _index_table(all_idx), "",
        analyze(real, all_idx, title="实时分析"),
        "", "### 📋 全部个股", "", _stock_table(sorted(real, key=lambda s: s.change_pct, reverse=True)),
        "", f"_来源: 新浪财经 | {now.isoformat(timespec='seconds')}_",
    ]
    md = "\n".join(report)
    (data_dir / "snapshot.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
