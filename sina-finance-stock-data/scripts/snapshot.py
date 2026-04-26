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


def _generate_analysis(
    stocks: list[StockQuote],
    indices: list[IndexQuote],
) -> str:
    """
    根据行情数据生成分析洞察。
    """
    lines: list[str] = []
    up_stocks = [s for s in stocks if s.is_up]
    down_stocks = [s for s in stocks if not s.is_up]

    # ── 1. 大盘定调 ──
    up_indices = [i for i in indices if i.is_up]
    down_indices = [i for i in indices if not i.is_up]
    if len(up_indices) >= len(indices) * 0.75:
        mood = "🟢 **大盘偏多**"
    elif len(down_indices) >= len(indices) * 0.75:
        mood = "🔴 **大盘偏空**"
    else:
        mood = "⚪ 大盘分化"

    lines.append(f"### 📈 市场分析")
    lines.append("")

    # 大盘概况
    idx_lines = []
    for i in indices:
        idx_lines.append(f"{i.name} {i.change_sign}{i.change_pct:.2f}%")
    lines.append(f"{mood} — " + "  |  ".join(idx_lines))
    lines.append("")

    # 涨跌比
    total = len(stocks)
    up_pct = len(up_stocks) / total * 100 if total else 0
    lines.append(f"**涨跌比：** 🟢 {len(up_stocks)} 涨 / 🔴 {len(down_stocks)} 跌 ({up_pct:.0f}% 上涨)")
    lines.append("")

    # ── 2. 板块分析 ──

    # 半导体 (NVDA, AMD, AVGO, QCOM, ARM, TSM, ASML, MRVL, TXN, INTC, SMCI)
    semi_tickers = {"gb_nvda", "gb_amd", "gb_avgo", "gb_qcom", "gb_arm",
                    "gb_tsm", "gb_asml", "gb_mrvl", "gb_txn", "gb_intc", "gb_smci"}
    semi = [s for s in stocks if s.ticker in semi_tickers]
    if semi:
        semi_up = [s for s in semi if s.is_up]
        semi_avg = sum(s.change_pct for s in semi) / len(semi)
        semi_icon = "🟢" if semi_avg > 0 else "🔴"
        lines.append(f"**💾 半导体** ({len(semi)} 只) — 平均涨跌: {semi_icon} {semi_avg:+.2f}%")
        # 找出极端
        top_semi = max(semi, key=lambda s: s.change_pct)
        bot_semi = min(semi, key=lambda s: s.change_pct)
        lines.append(f"  > 领涨: {top_semi.name} {top_semi.change_sign}{top_semi.change_pct:.2f}%  |  最弱: {bot_semi.name} {bot_semi.change_pct:+.2f}%")
        lines.append("")

    # 软件/云 (MSFT, CRM, ADBE, ORCL, NOW, SNOW, MDB, PANW, CRWD, PLTR)
    sw_tickers = {"gb_msft", "gb_crm", "gb_adbe", "gb_orcl", "gb_now",
                  "gb_snow", "gb_mdb", "gb_panw", "gb_crowd", "gb_pltr"}
    sw = [s for s in stocks if s.ticker in sw_tickers]
    if sw:
        sw_avg = sum(s.change_pct for s in sw) / len(sw)
        sw_icon = "🟢" if sw_avg > 0 else "🔴"
        lines.append(f"**☁️ 软件/云** ({len(sw)} 只) — 平均涨跌: {sw_icon} {sw_avg:+.2f}%")
        lines.append("")

    # 中概 (BABA, JD, PDD, BIDU, NIO, LI, XPEV)
    cn_tickers = {"gb_baba", "gb_jd", "gb_pdd", "gb_bidu", "gb_nio", "gb_li", "gb_xpev"}
    cn = [s for s in stocks if s.ticker in cn_tickers]
    if cn:
        cn_avg = sum(s.change_pct for s in cn) / len(cn)
        cn_icon = "🟢" if cn_avg > 0 else "🔴"
        lines.append(f"**🇨🇳 中概** ({len(cn)} 只) — 平均涨跌: {cn_icon} {cn_avg:+.2f}%")
        lines.append("")

    # ── 3. 异动个股 ──
    big_movers = [s for s in stocks if abs(s.change_pct) >= 5]
    if big_movers:
        lines.append("### ⚡ 异动提醒")
        lines.append("")
        for s in sorted(big_movers, key=lambda x: abs(x.change_pct), reverse=True):
            direction = "📈 大涨" if s.is_up else "📉 大跌"
            lines.append(
                f"- {direction} **{s.name}** ({s.ticker.replace('gb_','').upper()}) "
                f"{s.change_sign}{s.change_pct:.2f}%，现价 ${s.price:.2f}"
            )
        lines.append("")

    # ── 4. 52周位置 ──
    near_high = []
    near_low = []
    for s in stocks:
        if s.high_52w <= 0 or s.low_52w <= 0:
            continue
        pct_from_high = (s.high_52w - s.price) / s.high_52w * 100
        pct_from_low = (s.price - s.low_52w) / s.low_52w * 100
        if pct_from_high <= 5:
            near_high.append((s, pct_from_high))
        if pct_from_low <= 15:
            near_low.append((s, pct_from_low))

    if near_high:
        lines.append("### 🏔️ 接近 52 周高点（距高点 < 5%）")
        lines.append("")
        for s, pct in sorted(near_high, key=lambda x: x[1]):
            lines.append(f"- **{s.name}** ${s.price:.2f} — 距 52 周高 ${s.high_52w:.1f} 仅 {pct:.1f}%")
        lines.append("")

    if near_low:
        lines.append("### 📌 接近 52 周低点")
        lines.append("")
        for s, pct in sorted(near_low, key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"- {s.name} ${s.price:.2f} — 距 52 周低 ${s.low_52w:.1f} 仅 {pct:.0f}% 上方")
        lines.append("")

    return "\n".join(lines)


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

    # ── 分析 ──
    analysis = _generate_analysis(real_stocks, all_indices)
    lines.append(analysis)
    lines.append("")

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
