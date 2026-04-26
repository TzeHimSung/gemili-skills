#!/usr/bin/env python3
"""
美股行情快照 — 一键入口
用法:
    python3 scripts/snapshot.py              # 全量抓取 + 打印 markdown
    python3 scripts/snapshot.py --tech-only   # 仅科技板块
    python3 scripts/snapshot.py --json        # 输出 JSON
    python3 scripts/snapshot.py --tickers gb_nvda,gb_tsla,int_dji  # 指定 ticker

输出:
    data/snapshot.json     # JSON 格式快照
    data/snapshot.md       # Markdown 报表
"""

import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    US_STOCKS, US_INDICES, TECH_FOCUS,
    StockQuote, IndexQuote,
    fetch_raw, parse_response,
)

# gb_sox 返回完整字段但应展示为指数
PSEUDO_INDICES = {"gb_sox"}


# ═══════════════════════════════════════════════════
# 格式化
# ═══════════════════════════════════════════════════


def _pct_str(pct: float) -> str:
    """涨跌幅格式化。"""
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _color(pct: float) -> str:
    """涨跌颜色标记（用于 console）。✅" if pct > 0 else ("🔻" if pct < 0 else "➖")"""
    return "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")


def _format_stock_table(stocks: list[StockQuote]) -> str:
    """格式化为 markdown 表格。"""
    lines = [
        "| 股票 | 代码 | 现价 | 涨跌 | 涨跌幅 | 52周高 | 52周低 |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in stocks:
        ticker_clean = s.ticker.replace("gb_", "").upper()
        name = s.name[:16]
        lines.append(
            f"| {name} | {ticker_clean} | ${s.price:.2f} | "
            f"{s.change_sign}{s.change_amt:.2f} | "
            f"{_color(s.change_pct)} {_pct_str(s.change_pct)} | "
            f"${s.high_52w:.1f} | ${s.low_52w:.1f} |"
        )
    return "\n".join(lines)


def _format_index_table(indices: list[IndexQuote]) -> str:
    """格式化为指数 markdown 表格。"""
    lines = [
        "| 指数 | 最新 | 涨跌额 | 涨跌幅 |",
        "|---|---|---|---|",
    ]
    for idx in indices:
        lines.append(
            f"| {idx.name} | {idx.price:,.2f} | "
            f"{idx.change_sign}{idx.change_amt:,.2f} | "
            f"{_color(idx.change_pct)} {_pct_str(idx.change_pct)} |"
        )
    return "\n".join(lines)


def _gainers_losers(stocks: list[StockQuote], n: int = 5) -> tuple[list[StockQuote], list[StockQuote]]:
    """涨幅/跌幅 top N。"""
    sorted_stocks = sorted(stocks, key=lambda s: s.change_pct, reverse=True)
    gainers = sorted_stocks[:n]
    losers = sorted_stocks[-n:][::-1]
    return gainers, losers


# ═══════════════════════════════════════════════════
# 主逻辑
# ═══════════════════════════════════════════════════


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="新浪财经美股行情快照")
    parser.add_argument("--tech-only", action="store_true", help="仅抓取科技板块重点股")
    parser.add_argument("--tickers", default="", help="逗号分隔的 ticker 列表 (如 gb_nvda,gb_tsla)")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--data-dir", default="data", help="数据/输出目录 (默认: data/)")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # 确定抓取范围
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
        # 分离个股和指数
        stock_tickers = [t for t in tickers if t.startswith("gb_")]
        index_tickers = [t for t in tickers if t.startswith("int_")]
    elif args.tech_only:
        stock_tickers = TECH_FOCUS
        index_tickers = list(US_INDICES.keys())
    else:
        stock_tickers = list(US_STOCKS.keys())
        index_tickers = list(US_INDICES.keys())

    # 抓取
    now = datetime.now()
    if not args.quiet:
        print(f"📡 抓取行情... {len(stock_tickers)} 股 + {len(index_tickers)} 指数", file=sys.stderr)

    try:
        raw = fetch_raw(stock_tickers + index_tickers)
        stocks, indices = parse_response(raw)
    except Exception as e:
        print(f"❌ 抓取失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 分离 SOX 等伪指数
    pseudo_idx = [s for s in stocks if s.ticker in PSEUDO_INDICES]
    real_stocks = [s for s in stocks if s.ticker not in PSEUDO_INDICES]

    if not args.quiet:
        print(f"✅ 成功: {len(real_stocks)} 股, {len(indices)} 指数 + {len(pseudo_idx)} 板块指数", file=sys.stderr)

    # ── JSON 输出 ──
    snapshot_data = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "indices": [
            {
                "ticker": idx.ticker, "name": idx.name,
                "price": idx.price, "change_pct": idx.change_pct,
                "change_amt": idx.change_amt,
            }
            for idx in indices
        ] + [
            {
                "ticker": s.ticker, "name": s.name,
                "price": s.price, "change_pct": s.change_pct,
                "change_amt": s.change_amt,
            }
            for s in pseudo_idx
        ],
        "stocks": [
            {
                "ticker": s.ticker, "name": s.name,
                "price": s.price, "change_pct": s.change_pct,
                "change_amt": s.change_amt, "volume": s.volume,
                "high_52w": s.high_52w, "low_52w": s.low_52w,
            }
            for s in real_stocks
        ],
    }
    json_path = data_dir / "snapshot.json"
    json_path.write_text(json.dumps(snapshot_data, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(snapshot_data, ensure_ascii=False, indent=2))
        return

    # ── Markdown 输出 ──
    date_str = now.strftime("%m月%d日 %H:%M")

    # 指数表（含 pseudo indices）
    all_indices = indices + [
        IndexQuote(
            ticker=s.ticker, name=s.name,
            price=s.price, change_pct=s.change_pct,
            change_amt=s.change_amt, fetched_at=s.fetched_at,
        )
        for s in pseudo_idx
    ]

    lines = [
        f"## 📊 美股行情快照 — {date_str}",
        "",
        "### 指数",
        "",
        _format_index_table(all_indices),
        "",
    ]

    # 涨幅榜
    gainers, losers = _gainers_losers(real_stocks)
    lines.append("### 🔥 涨幅 Top 5")
    lines.append("")
    lines.append(_format_stock_table(gainers))
    lines.append("")

    # 跌幅榜
    lines.append("### 📉 跌幅 Top 5")
    lines.append("")
    lines.append(_format_stock_table(losers))
    lines.append("")

    # 科技板块
    tech_stocks = [s for s in real_stocks if s.ticker in TECH_FOCUS]
    if tech_stocks:
        tech_stocks.sort(key=lambda s: s.change_pct, reverse=True)
        lines.append("### 💻 科技板块")
        lines.append("")
        lines.append(_format_stock_table(tech_stocks))
        lines.append("")

    # 全部
    all_sorted = sorted(real_stocks, key=lambda s: s.change_pct, reverse=True)
    lines.append("### 📋 全部个股")
    lines.append("")
    lines.append(_format_stock_table(all_sorted))
    lines.append("")

    lines.append(f"_数据来源: 新浪财经 hq.sinajs.cn | 更新: {now.isoformat(timespec='seconds')}_")

    md_text = "\n".join(lines)
    md_path = data_dir / "snapshot.md"
    md_path.write_text(md_text, encoding="utf-8")

    print(md_text)


if __name__ == "__main__":
    main()
