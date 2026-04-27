"""
美股分析引擎 — 大盘定调、板块分析、异动筛选、52周位置、叙事生成。

市场特定逻辑：美股指数定调、AI/NVDA 叙事、半导体 vs 软件分化。
通用分析函数（趋势检测、深度原因）从 common 导入（来自共享库）。
"""
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from common import (
    StockQuote, IndexQuote, DailyBar,
    SECTORS, YAHOO_STOCKS_CN,
    icon as _icon, pct_str as _pct_str,
    fifty_two_week_text as _fifty_two_week_text,
    detect_trend as _detect_trend,
    deep_reason_base as _deep_reason_base,
    trend_analysis_section as _shared_tsa,
    DEFAULT_TREND_THRESHOLDS,
)


# 本地 display_name 适配（绑定 YAHOO_STOCKS_CN，兼容 ticker 大小写）
def _display_name(stock: StockQuote) -> str:
    return YAHOO_STOCKS_CN.get(stock.ticker.upper(), stock.name)


# ═══════════════════════════════════════════════════
# 大盘概览叙事
# ═══════════════════════════════════════════════════

def _index_narrative(indices: list[IndexQuote]) -> str:
    """生成大盘一句话概述。"""
    up = [i for i in indices if i.is_up]
    dn = [i for i in indices if not i.is_up]

    if len(dn) == 0:
        mood = "全线收涨"
    elif len(up) == 0:
        mood = "全线收跌"
    elif len(up) > len(dn):
        mood = "多数收涨"
    else:
        mood = "多数收跌"

    strongest = max(indices, key=lambda i: i.change_pct)
    weakest = min(indices, key=lambda i: i.change_pct)

    parts = []
    if abs(strongest.change_pct) >= 3:
        parts.append(f"{strongest.name} 飙升 {strongest.change_pct:+.2f}%")
    elif abs(strongest.change_pct) >= 1:
        parts.append(f"{strongest.name} 领涨 {strongest.change_pct:+.2f}%")

    if abs(weakest.change_pct) >= 1 and weakest.ticker != strongest.ticker:
        parts.append(f"{weakest.name} {weakest.change_pct:+.2f}%")

    if parts:
        return f"{mood}，" + "，".join(parts)
    return mood


# ═══════════════════════════════════════════════════
# 原因简述（启发式）
# ═══════════════════════════════════════════════════

def _reason_brief(stock: StockQuote, all_stocks: list[StockQuote]) -> str:
    """为异动股票生成简短原因简述。"""
    reasons = []

    # 成交量异常
    if stock.volume > 0:
        sector_tickers = set()
        for label, tickers in SECTORS.items():
            if stock.ticker.upper() in {t.upper() for t in tickers}:
                sector_tickers = {t.upper() for t in tickers}
                break

        sector_stocks = [s for s in all_stocks if s.ticker.upper() in sector_tickers and s.volume > 0]
        if len(sector_stocks) >= 3:
            avg_vol = sum(s.volume for s in sector_stocks) / len(sector_stocks)
            if stock.volume > avg_vol * 3:
                reasons.append("天量成交")

    # 涨跌幅程度
    abs_pct = abs(stock.change_pct)
    if stock.is_up:
        if abs_pct >= 15:
            reasons.append("重大利好催化")
        elif abs_pct >= 10:
            reasons.append("资金集中涌入")
        elif abs_pct >= 7:
            reasons.append("消息面/财报预期驱动")
        elif abs_pct >= 5:
            reasons.append("板块联动效应")
    else:
        if abs_pct >= 15:
            reasons.append("重大利空冲击")
        elif abs_pct >= 10:
            reasons.append("资金大幅流出")
        elif abs_pct >= 7:
            reasons.append("业绩预警/负面消息")
        elif abs_pct >= 5:
            reasons.append("板块集体回调")

    # 52周位置
    if stock.high_52w > 0 and stock.is_up:
        pct_h = (stock.high_52w - stock.price) / stock.high_52w * 100
        if pct_h <= 2:
            reasons.append("逼近历史新高")
        elif pct_h <= 5:
            reasons.append("接近前高")

    if stock.low_52w > 0 and not stock.is_up:
        pct_l = (stock.price - stock.low_52w) / stock.low_52w * 100
        if pct_l <= 10:
            reasons.append("逼近52周低点")

    # 板块联动
    for label, tickers in SECTORS.items():
        if stock.ticker.upper() in {t.upper() for t in tickers}:
            members = [s for s in all_stocks if s.ticker.upper() in {t.upper() for t in tickers}]
            if len(members) >= 5:
                up_count = sum(1 for s in members if s.is_up)
                if stock.is_up and up_count >= len(members) * 0.8:
                    reasons.append(f"{label.strip('🇨🇳💾☁️🛒 ')}板块整体走强")
                elif not stock.is_up and up_count <= len(members) * 0.2:
                    reasons.append(f"{label.strip('🇨🇳💾☁️🛒 ')}板块集体回调")
            break

    if not reasons:
        if abs(stock.change_pct) < 1:
            reasons.append("缺乏短期催化剂" if stock.is_up else "横盘整理")
        elif abs(stock.change_pct) < 2:
            reasons.append("小幅波动")
        else:
            reasons.append("市场情绪波动")

    return "；".join(reasons[:3])


# ═══════════════════════════════════════════════════
# 表现综述 (叙事段落)
# ═══════════════════════════════════════════════════

def _overview_narrative(stocks: list[StockQuote], indices: list[IndexQuote]) -> str:
    """生成 表现综述 叙事段落。"""
    lines = []

    # 半导体板块
    semi = [s for s in stocks if s.ticker.upper() in SECTORS.get("💾 半导体", set())]
    if semi:
        avg_semi = sum(s.change_pct for s in semi) / len(semi)
        top_semi = max(semi, key=lambda s: s.change_pct)
        sox = next((i for i in indices if "SOX" in i.ticker.upper() or "PHLX" in i.name.upper() or "半导体" in i.name), None)
        sox_str = f"费城半导体指数涨{sox.change_pct:.2f}%" if sox else f"板块均涨{avg_semi:.1f}%"
        if avg_semi >= 3:
            lines.append(
                f"半导体板块全线爆发，{_display_name(top_semi)}以 {top_semi.change_sign}{top_semi.change_pct:.2f}% "
                f"的涨幅领跑，{sox_str}。"
            )
        elif avg_semi >= 1:
            lines.append(
                f"半导体板块温和走强，{_display_name(top_semi)}领涨 {top_semi.change_sign}{top_semi.change_pct:.2f}%，{sox_str}。"
            )
        elif avg_semi <= -2:
            bot_semi = min(semi, key=lambda s: s.change_pct)
            lines.append(f"半导体板块承压，{_display_name(bot_semi)}领跌 {bot_semi.change_pct:.2f}%，{sox_str}。")

    # 软件 vs 硬件分化
    semi_tickers = {s.ticker.upper() for s in semi}
    software = [s for s in stocks
                if s.ticker.upper() in SECTORS.get("☁️ 软件/云", set())
                and s.ticker.upper() not in semi_tickers]
    if semi and software:
        avg_semi = sum(s.change_pct for s in semi) / len(semi)
        avg_soft = sum(s.change_pct for s in software) / len(software)
        if avg_semi >= 3 and avg_soft < 0:
            lines.append(
                f"软硬分化明显：资金从软件板块撤出转向半导体，"
                f"软件板块均跌{abs(avg_soft):.1f}%而半导体均涨{avg_semi:.1f}%。"
            )
        elif avg_semi >= 2 and avg_soft <= 1:
            lines.append("硬件强于软件，AI算力叙事继续主导资金流向。")

    # 整体涨跌比
    up = [s for s in stocks if s.is_up]
    if len(up) >= len(stocks) * 0.7:
        lines.insert(0, "市场情绪积极，绝大多数科技股收涨。")
    elif len(up) <= len(stocks) * 0.3:
        lines.insert(0, "市场情绪低迷，多数科技股承压下跌。")

    # AI narrative
    nvda = next((s for s in stocks if s.ticker.upper() == "NVDA"), None)
    if nvda and nvda.is_up and nvda.change_pct >= 3:
        if nvda.high_52w > 0:
            pct_h = (nvda.high_52w - nvda.price) / nvda.high_52w * 100
            if pct_h <= 3:
                lines.append(f"NVDA 涨 {nvda.change_pct:.2f}% 逼近历史高点，AI 算力需求持续强劲。")
            else:
                lines.append(f"NVDA 涨 {nvda.change_pct:.2f}%，AI 基础设施需求未见放缓迹象。")

    return "".join(lines) if lines else "科技板块整体表现平稳。"


# ═══════════════════════════════════════════════════
# 关键动态 (编号叙事)
# ═══════════════════════════════════════════════════

def _key_dynamics(stocks: list[StockQuote], indices: list[IndexQuote]) -> list[str]:
    """生成 关键动态 编号列表。"""
    dynamics = []
    seen_tickers = set()

    # 1. 最大异动：涨跌幅 ≥ 10%
    big_movers = sorted(
        [s for s in stocks if abs(s.change_pct) >= 10],
        key=lambda s: abs(s.change_pct), reverse=True,
    )
    for s in big_movers[:2]:
        if s.ticker.upper() in seen_tickers:
            continue
        seen_tickers.add(s.ticker.upper())
        direction = "暴涨" if s.is_up else "暴跌"
        vol_note = ""
        if s.volume > 0:
            vol_m = s.volume / 1e6
            if vol_m > 100:
                vol_note = f"，成交量超{vol_m/100:.0f}亿股"
            elif vol_m > 10:
                vol_note = f"，成交量{vol_m:.0f}M"
        pos_note = ""
        if s.high_52w > 0 and s.is_up:
            pct_h = (s.high_52w - s.price) / s.high_52w * 100
            if pct_h <= 3:
                pos_note = "，逼近历史新高"

        emoji = "🔴" if not s.is_up else "🟢"
        dynamics.append(
            f"{emoji} **{_display_name(s)}史诗级{direction}**：{direction} {abs(s.change_pct):.2f}%{vol_note}{pos_note}。"
            f"此级别异动通常伴随重大基本面变化或市场情绪剧烈波动。"
        )

    # 2. AI 算力链
    ai_stocks = ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MRVL"]
    ai = [s for s in stocks if s.ticker.upper() in ai_stocks and s.is_up and s.change_pct >= 2]
    if ai:
        names = "、".join(_display_name(s).split()[-1] for s in ai[:3])
        avg_ai = sum(s.change_pct for s in ai) / len(ai)
        if avg_ai >= 5:
            dynamics.append(f"🤖 **AI 算力链全面爆发**：{names} 等同步大涨，AI 基础设施建设持续加速。")
        elif avg_ai >= 3:
            dynamics.append(f"🤖 **AI 算力链表现强势**：{names} 等集体收涨，资金持续青睐 AI 基础设施标的。")

    # 3. 软硬分化
    semi = [s for s in stocks if s.ticker.upper() in SECTORS.get("💾 半导体", set())]
    software = [s for s in stocks
                if s.ticker.upper() in SECTORS.get("☁️ 软件/云", set())
                and s.ticker.upper() not in {x.ticker.upper() for x in semi}]
    if semi and software:
        avg_semi = sum(s.change_pct for s in semi) / len(semi)
        avg_soft = sum(s.change_pct for s in software) / len(software)
        if abs(avg_semi - avg_soft) >= 2:
            if avg_semi > avg_soft:
                dynamics.append(
                    f"📉 **软硬分化显著**：半导体均涨{avg_semi:.1f}%，软件/云均涨{avg_soft:.1f}%，"
                    f"市场呈现「卖软件买硬件」的轮动特征。"
                )
            else:
                dynamics.append(
                    f"📉 **资金回流软件**：软件/云均涨{avg_soft:.1f}%，半导体均涨{avg_semi:.1f}%，"
                    f"资金从硬件切换至软件板块。"
                )

    # 4. 中概表现
    china = [s for s in stocks if s.ticker.upper() in SECTORS.get("🇨🇳 中概", set())]
    if china:
        avg_cn = sum(s.change_pct for s in china) / len(china)
        if abs(avg_cn) >= 2:
            direction = "走强" if avg_cn > 0 else "走弱"
            top_cn = max(china, key=lambda s: s.change_pct) if avg_cn > 0 else min(china, key=lambda s: s.change_pct)
            dynamics.append(
                f"🇨🇳 **中概板块{direction}**：均{avg_cn:+.1f}%，"
                f"{_display_name(top_cn).split()[-1]} {'领涨' if avg_cn > 0 else '领跌'} {abs(top_cn.change_pct):.2f}%。"
            )

    # 去重、编号
    seen = set()
    unique = []
    for d in dynamics:
        key = d[:30]
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique[:4]


# ═══════════════════════════════════════════════════
# 一句话总结
# ═══════════════════════════════════════════════════

def _one_line_summary(stocks: list[StockQuote], indices: list[IndexQuote]) -> str:
    """生成 一句话总结。"""
    semi = [s for s in stocks if s.ticker.upper() in SECTORS.get("💾 半导体", set())]
    avg_semi = sum(s.change_pct for s in semi) / len(semi) if semi else 0

    up = [s for s in stocks if s.is_up]
    up_ratio = len(up) / len(stocks) if stocks else 0

    big_mover = max(stocks, key=lambda s: abs(s.change_pct))
    strongest_idx = max(indices, key=lambda i: i.change_pct) if indices else None

    if avg_semi >= 5:
        parts = [f"半导体行业史诗级行情引爆美股"]
        if big_mover and abs(big_mover.change_pct) >= 10:
            parts.append(f"{_display_name(big_mover).split()[-1]}惊天{big_mover.change_sign}{big_mover.change_pct:.1f}%")
        if strongest_idx:
            parts.append(f"{strongest_idx.name}大涨{strongest_idx.change_pct:.1f}%")
        return "，".join(parts[:2]) + "。"
    elif avg_semi >= 2 and up_ratio >= 0.6:
        parts = ["AI 算力叙事持续主导美股"]
        if strongest_idx:
            parts.append(f"{strongest_idx.name}{strongest_idx.change_sign}{strongest_idx.change_pct:.2f}%")
        return "，".join(parts[:2]) + "。"
    elif avg_semi <= -2:
        return f"半导体板块集体回调，{strongest_idx.name if strongest_idx else '市场'}承压，风险偏好降温。"
    elif up_ratio <= 0.3:
        return "科技板块普遍走弱，市场避险情绪升温。"
    else:
        if strongest_idx:
            return f"美股科技板块涨跌互现，{strongest_idx.name} {strongest_idx.change_sign}{strongest_idx.change_pct:.2f}%，市场等待方向选择。"
        return "美股科技板块涨跌互现，市场等待方向选择。"


# ═══════════════════════════════════════════════════
# 深度原因分析（市场特定包装）
# ═══════════════════════════════════════════════════

def _deep_reason(stock: StockQuote, all_stocks: list[StockQuote]) -> str:
    """美股个股深度原因分析。包装共享库的 deep_reason_base。"""
    return _deep_reason_base(stock, all_stocks, SECTORS, DEFAULT_TREND_THRESHOLDS)


# ═══════════════════════════════════════════════════
# 📈 走势深度分析 (调用共享库)
# ═══════════════════════════════════════════════════

_trend_analysis_section = lambda stocks, top_n=3: _shared_tsa(
    stocks, SECTORS, top_n=top_n,
    trend_thresholds=DEFAULT_TREND_THRESHOLDS,
    name_fn=_display_name,
)


# ═══════════════════════════════════════════════════
# 52周位置检查（共享库代理）
# ═══════════════════════════════════════════════════

from common import fifty_two_week_check as _fifty_two_week_check


# ═══════════════════════════════════════════════════
# 旧版兼容 analyze 函数
# ═══════════════════════════════════════════════════

def _market_mood(indices: list[IndexQuote]) -> str:
    up = [i for i in indices if i.is_up]
    if len(up) >= len(indices) * 0.75:
        return "🟢 **偏多**"
    if len(up) <= len(indices) * 0.25:
        return "🔴 **偏空**"
    return "⚪ 分化"


def analyze(
    stocks: list[StockQuote],
    indices: list[IndexQuote],
    *,
    title: str = "市场分析",
    date_line: str = "",
) -> str:
    """根据行情数据生成完整分析 markdown（旧版兼容）。"""
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
        members = [s for s in stocks if s.ticker.upper() in {t.upper() for t in tickers}]
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
