#!/usr/bin/env python3
"""
中港股实时快照 — 新浪财经 API (hq.sinajs.cn)
A 股芯片半导体 + 港股科技 / LLM 概念
用法:
    python3 scripts/snapshot.py              # 全量实时
    python3 scripts/snapshot.py --a-only     # 仅 A 股
    python3 scripts/snapshot.py --hk-only    # 仅港股
"""

import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    SINA_A_STOCKS, SINA_HK_STOCKS, SINA_INDICES,
    StockQuote, IndexQuote, http_get,
)

SINA_URL = "http://hq.sinajs.cn/list={tickers}"


def _parse_sina_line(line: str) -> StockQuote | IndexQuote | None:
    """解析单行新浪行情数据。"""
    import re
    m = re.match(r'var hq_str_(\w+)="(.*)"', line)
    if not m:
        return None
    ticker, data = m.group(1), m.group(2)
    fields = data.split(",")

    if not ticker:
        return None

    now = datetime.now().isoformat(timespec="seconds")

    if ticker.startswith("s_") or ticker.startswith("int_"):
        # 指数：Sina mini-index 格式为 name,price,change_amt,change_pct,...
        try:
            name = fields[0]
            price = float(fields[1])
            change_amt = float(fields[2])
            change_pct = float(fields[3])
            return IndexQuote(
                ticker=ticker, name=name, price=price,
                change_pct=change_pct, change_amt=change_amt,
                fetched_at=now, source="sina",
            )
        except (ValueError, IndexError):
            return None

    if ticker.startswith("hk"):
        # 港股：英文名,中文名,开盘,昨收,最高,最低,现价,涨跌额,涨跌幅,...
        try:
            name = fields[1] or fields[0]
            price = float(fields[6])
            prev = float(fields[3])
            change_amt = float(fields[7])
            change_pct = float(fields[8])
            return StockQuote(
                ticker=ticker, name=name, price=price,
                change_pct=change_pct, change_amt=change_amt,
                prev_close=prev,
                high=float(fields[4]),
                low=float(fields[5]),
                fetched_at=now, source="sina",
            )
        except (ValueError, IndexError):
            return None

    # A 股个股：name,open,prev_close,current,high,low,...
    try:
        name = fields[0]
        price = float(fields[3])
        prev = float(fields[2])
        change_pct = ((price - prev) / prev) * 100 if prev else 0
        return StockQuote(
            ticker=ticker, name=name, price=price,
            change_pct=change_pct, change_amt=price - prev,
            prev_close=prev,
            high=float(fields[4]),
            low=float(fields[5]),
            fetched_at=now, source="sina",
        )
    except (ValueError, IndexError):
        return None


def _fetch_sina(tickers: list[str]) -> list[StockQuote | IndexQuote]:
    """批量请求新浪实时行情。"""
    results = []
    chunk_size = 20
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        url = SINA_URL.format(tickers=",".join(chunk))
        try:
            resp = http_get(url, referer="https://finance.sina.com.cn/", timeout=10)
            for line in resp.text.strip().split("\n"):
                parsed = _parse_sina_line(line.strip())
                if parsed:
                    results.append(parsed)
        except Exception as e:
            print(f"  ⚠ 新浪请求失败: {e}", file=sys.stderr)
        time.sleep(0.2)
    return results


def main():
    import argparse
    ap = argparse.ArgumentParser(description="中港股实时快照 (新浪)")
    ap.add_argument("--a-only", action="store_true")
    ap.add_argument("--hk-only", action="store_true")
    ap.add_argument("--tickers", default="")
    args = ap.parse_args()

    if args.tickers:
        all_tk = args.tickers.split(",")
    elif args.a_only:
        all_tk = list(SINA_A_STOCKS.keys()) + [k for k in SINA_INDICES if k.startswith("s_")]
    elif args.hk_only:
        all_tk = list(SINA_HK_STOCKS.keys()) + [k for k in SINA_INDICES if k.startswith("int_")]
    else:
        all_tk = list(SINA_A_STOCKS.keys()) + list(SINA_HK_STOCKS.keys()) + list(SINA_INDICES.keys())

    quotes = _fetch_sina(all_tk)
    stocks = [q for q in quotes if isinstance(q, StockQuote)]
    indices = [q for q in quotes if isinstance(q, IndexQuote)]

    now = datetime.now()
    print(f"# 📡 中港股实时快照 — {now.strftime('%Y-%m-%d %H:%M')}")
    print()

    if indices:
        print("## 指数")
        for i in indices:
            icon = "🟢" if i.is_up else "🔴"
            print(f"- {icon} **{i.name}** {i.price:,.2f} ({i.change_sign}{i.change_pct:.2f}%)")
        print()

    if stocks:
        print("## 个股")
        print("| 股票 | 现价 | 涨跌幅 |")
        print("|---|---|---|")
        for s in sorted(stocks, key=lambda s: abs(s.change_pct), reverse=True):
            icon = "🟢" if s.is_up else "🔴"
            print(f"| {s.name} | {s.price:.2f} | {icon} {s.change_sign}{s.change_pct:.2f}% |")

    print(f"\n---\n📡 数据来源：新浪财经 hq.sinajs.cn | 更新时间 {now.strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
