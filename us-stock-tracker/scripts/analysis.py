"""
共享分析引擎 — 大盘定调、板块分析、异动筛选、52周位置。
被 snapshot.py 和 daily_report.py 共用。
"""

from datetime import datetime

from common import StockQuote, IndexQuote, SECTORS


def _icon(pct: float) -> str:
    return "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")


def _pct_str(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def analyze(
    stocks: list[StockQuote],
    indices: list[IndexQuote],
    *,
    title: str = "市场分析",
    date_line: str = "",
) -> str:
    """
    根据行情数据生成完整分析 markdown。
    
    Returns: 分析文本（多段 markdown）
    """
    lines: list[str] = []
    if date_line:
        lines.append(date_line)
    lines.append(f"### 📈 {title}")
    lines.append("")

    # ── 1. 大盘定调 ──
    mood = _market_mood(indices)
    idx_parts = [f"{i.name} {i.change_sign}{i.change_pct:.2f}%" for i in indices]
    lines.append(f"{mood} — " + " | ".join(idx_parts))
    lines.append("")

    # 涨跌比
    up = [s for s in stocks if s.is_up]
    dn = [s for s in stocks if not s.is_up]
    total = len(stocks)
    up_pct = len(up) / total * 100 if total else 0
    lines.append(f"涨跌比：🟢 {len(up)} 涨 / 🔴 {len(dn)} 跌 ({up_pct:.0f}% 上涨)")
    lines.append("")

    # ── 2. 板块分析 ──
    for label, tickers in SECTORS.items():
        members = [s for s in stocks if s.ticker in tickers or f"gb_{s.ticker.lower()}" in {t.lower() for t in tickers}]
        if not members:
            continue
        avg = sum(s.change_pct for s in members) / len(members)
        top = max(members, key=lambda s: s.change_pct)
        bot = min(members, key=lambda s: s.change_pct)
        lines.append(f"**{label}** ({len(members)} 只) — {_icon(avg)} 均{_pct_str(avg)}")
        lines.append(f"  > 领涨: {top.name} {top.change_sign}{top.change_pct:.2f}%  |  最弱: {bot.name} {bot.change_pct:+.2f}%")
        lines.append("")

    # ── 3. 异动提醒 ──
    big = [s for s in stocks if abs(s.change_pct) >= 5]
    if big:
        lines.append("### ⚡ 异动提醒")
        lines.append("")
        for s in sorted(big, key=lambda x: abs(x.change_pct), reverse=True):
            direction = "📈 大涨" if s.is_up else "📉 大跌"
            ticker_clean = s.ticker.replace("gb_", "").upper()
            lines.append(
                f"- {direction} **{s.name}** ({ticker_clean}) "
                f"{s.change_sign}{s.change_pct:.2f}%，现价 ${s.price:.2f}"
            )
        lines.append("")

    # ── 4. 52 周位置 ──
    near_high, near_low = _fifty_two_week_check(stocks)
    if near_high:
        lines.append("### 🏔️ 接近 52 周高点（距高点 < 5%）")
        lines.append("")
        for s, pct in sorted(near_high, key=lambda x: x[1]):
            lines.append(f"- **{s.name}** ${s.price:.2f} — 距 ${s.high_52w:.1f} 仅 {pct:.1f}%")
        lines.append("")

    if near_low:
        lines.append("### 📌 接近 52 周低点")
        lines.append("")
        for s, pct in sorted(near_low, key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"- {s.name} ${s.price:.2f} — 距低点 ${s.low_52w:.1f} 仅 {pct:.0f}% 上方")
        lines.append("")

    return "\n".join(lines)


def _market_mood(indices: list[IndexQuote]) -> str:
    up = [i for i in indices if i.is_up]
    if len(up) >= len(indices) * 0.75:
        return "🟢 **偏多**"
    if len(up) <= len(indices) * 0.25:
        return "🔴 **偏空**"
    return "⚪ 分化"


def _fifty_two_week_check(
    stocks: list[StockQuote],
) -> tuple[list[tuple[StockQuote, float]], list[tuple[StockQuote, float]]]:
    near_high = []
    near_low = []
    for s in stocks:
        if s.high_52w <= 0 or s.low_52w <= 0:
            continue
        pct_h = (s.high_52w - s.price) / s.high_52w * 100
        pct_l = (s.price - s.low_52w) / s.low_52w * 100
        if pct_h <= 5:
            near_high.append((s, pct_h))
        if pct_l <= 15:
            near_low.append((s, pct_l))
    return near_high, near_low
