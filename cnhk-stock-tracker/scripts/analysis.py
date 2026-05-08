"""
中港股分析引擎 — A 股芯片 + 港股科技叙事。

市场特定逻辑：A/港股指数分组定调、涨跌停检测、LLM 概念、跨市场联动。
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
    _display_name,
    _fifty_two_week_text,
    _detect_trend,
    _deep_reason_base,
    _trend_analysis_section as _shared_tsa,
    CNHK_TREND_THRESHOLDS,
    market_hours_display,
)


# ═══════════════════════════════════════════════════
# 大盘概览叙事
# ═══════════════════════════════════════════════════

def _index_narrative(indices: list[IndexQuote]) -> str:
    """生成大盘概述 — 分别评价 A 股和港股指数。"""
    if not indices:
        return "暂无指数数据"

    a_idx = [i for i in indices if ".SS" in i.ticker or ".SZ" in i.ticker]
    hk_idx = [i for i in indices if ".HK" in i.ticker or i.ticker.startswith("^")]

    parts = []
    if a_idx:
        strongest_a = max(a_idx, key=lambda i: i.change_pct) if a_idx else None
        a_up = sum(1 for i in a_idx if i.is_up)
        if a_up == len(a_idx):
            parts.append("A 股主要指数全线收涨")
        elif a_up == 0:
            parts.append("A 股主要指数全线收跌")
        elif a_up >= len(a_idx) * 0.6:
            parts.append("A 股多数指数收涨")
        else:
            parts.append("A 股多数指数收跌")
        if strongest_a and abs(strongest_a.change_pct) >= 1:
            parts.append(f"{strongest_a.name} {strongest_a.change_sign}{strongest_a.change_pct:.2f}%")

    if hk_idx:
        strongest_hk = max(hk_idx, key=lambda i: i.change_pct) if hk_idx else None
        hk_all = len(hk_idx)
        hk_up = sum(1 for i in hk_idx if i.is_up)
        if hk_up == hk_all:
            parts.append("港股指数全线上涨")
        elif hk_up == 0:
            parts.append("港股指数全线下跌")
        elif hk_up >= hk_all * 0.6:
            parts.append("港股指数多数上涨")
        else:
            parts.append("港股指数多数下跌")
        if strongest_hk and abs(strongest_hk.change_pct) >= 1:
            parts.append(f"{strongest_hk.name} {strongest_hk.change_sign}{strongest_hk.change_pct:.2f}%")

    return "，".join(parts) if parts else "市场窄幅震荡"


# ═══════════════════════════════════════════════════
# 原因简述（启发式）
# ═══════════════════════════════════════════════════

def _reason_brief(stock: StockQuote, all_stocks: list[StockQuote]) -> str:
    """为异动股票生成简短原因简述。"""
    reasons = []
    abs_pct = abs(stock.change_pct)

    # A 股涨跌停
    is_a = ".SS" in stock.ticker or ".SZ" in stock.ticker

    if is_a and abs_pct >= 9.5:
        reasons.append("逼近涨跌停")
    if is_a and abs_pct >= 7:
        reasons.append("主力资金异动")

    # 涨跌幅程度
    if stock.is_up:
        if abs_pct >= 7:
            reasons.append("重大利好催化")
        elif abs_pct >= 5:
            reasons.append("资金集中涌入")
        elif abs_pct >= 3:
            reasons.append("板块联动效应")
    else:
        if abs_pct >= 7:
            reasons.append("重大利空冲击")
        elif abs_pct >= 5:
            reasons.append("资金大幅流出")
        elif abs_pct >= 3:
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
        if stock.ticker in tickers:
            members = [s for s in all_stocks if s.ticker in tickers]
            if len(members) >= 3:
                up_count = sum(1 for s in members if s.is_up)
                sector_name = label.strip("💾🌐 ")
                if stock.is_up and up_count >= len(members) * 0.7:
                    reasons.append(f"{sector_name}板块整体走强")
                elif not stock.is_up and up_count <= len(members) * 0.3:
                    reasons.append(f"{sector_name}板块集体回调")
            break

    if not reasons:
        if abs(stock.change_pct) < 1:
            reasons.append("横盘整理" if not stock.is_up else "小幅收涨")
        elif abs(stock.change_pct) < 2:
            reasons.append("小幅波动")
        else:
            reasons.append("市场情绪波动")

    return "；".join(reasons[:3])


# ═══════════════════════════════════════════════════
# 表现综述
# ═══════════════════════════════════════════════════

def _overview_narrative(stocks: list[StockQuote], indices: list[IndexQuote]) -> str:
    """生成 表现综述 叙事段落。"""
    lines = []

    a_chip = [s for s in stocks if s.ticker in SECTORS.get("💾 A股芯片", set())]
    hk_tech = [s for s in stocks if s.ticker in SECTORS.get("🌐 港股科技", set())]

    if a_chip:
        avg_a = sum(s.change_pct for s in a_chip) / len(a_chip)
        top_a = max(a_chip, key=lambda s: s.change_pct)
        name_top = _display_name(top_a).split()[-1] if " " in _display_name(top_a) else _display_name(top_a)
        if avg_a >= 3:
            lines.append(
                f"A 股芯片板块全面爆发，{name_top}领涨 {top_a.change_sign}{top_a.change_pct:.2f}%，"
                f"板块均涨{avg_a:.1f}%。"
            )
        elif avg_a >= 1:
            lines.append(f"A 股芯片温和走强，{name_top}领涨{top_a.change_sign}{top_a.change_pct:.2f}%，板块均涨{avg_a:.1f}%。")
        elif avg_a <= -2:
            name_bot = _display_name(min(a_chip, key=lambda s: s.change_pct)).split()[-1]
            bot_a = min(a_chip, key=lambda s: s.change_pct)
            lines.append(f"A 股芯片集体承压，{name_bot}领跌 {bot_a.change_pct:.2f}%，板块均跌{abs(avg_a):.1f}%。")

    if hk_tech:
        avg_hk = sum(s.change_pct for s in hk_tech) / len(hk_tech)
        top_hk = max(hk_tech, key=lambda s: s.change_pct)
        name_top = _display_name(top_hk).split()[-1] if " " in _display_name(top_hk) else _display_name(top_hk)
        if avg_hk >= 3:
            lines.append(
                f"港股科技全线走强，{name_top}领涨 {top_hk.change_sign}{top_hk.change_pct:.2f}%，"
                f"板块均涨{avg_hk:.1f}%。"
            )
        elif avg_hk >= 1:
            lines.append(f"港股科技温和反弹，{name_top}领涨{top_hk.change_sign}{top_hk.change_pct:.2f}%。")
        elif avg_hk <= -2:
            bot_hk = min(hk_tech, key=lambda s: s.change_pct)
            name_bot = _display_name(bot_hk).split()[-1] if " " in _display_name(bot_hk) else _display_name(bot_hk)
            lines.append(f"港股科技承压，{name_bot}领跌 {bot_hk.change_pct:.2f}%。")

    # 整体涨跌比
    up = [s for s in stocks if s.is_up]
    up_ratio = len(up) / len(stocks) if stocks else 0
    if up_ratio >= 0.7:
        lines.insert(0, "市场情绪偏积极，超七成个股收涨。")
    elif up_ratio <= 0.3:
        lines.insert(0, "市场情绪低迷，多数个股承压下跌。")

    return "".join(lines) if lines else "中港科技板块整体表现平稳。"


# ═══════════════════════════════════════════════════
# 关键动态
# ═══════════════════════════════════════════════════

def _key_dynamics(stocks: list[StockQuote], indices: list[IndexQuote]) -> list[str]:
    """生成 关键动态 编号列表。"""
    dynamics = []

    a_chip = [s for s in stocks if s.ticker in SECTORS.get("💾 A股芯片", set())]
    hk_tech = [s for s in stocks if s.ticker in SECTORS.get("🌐 港股科技", set())]

    # 1. A 股芯片动向
    if a_chip:
        big_a = sorted([s for s in a_chip if abs(s.change_pct) >= 5], key=lambda s: abs(s.change_pct), reverse=True)
        if big_a:
            s = big_a[0]
            name = _display_name(s).split()[-1] if " " in _display_name(s) else _display_name(s)
            direction = "暴涨" if s.is_up else "暴跌"
            emoji = "🟢" if s.is_up else "🔴"
            vol_note = ""
            if s.volume > 0 and s.volume > 1e8:
                vol_note = f"，成交量{s.volume/1e8:.1f}亿股"
            dynamics.append(
                f"{emoji} **A 股芯片异动**：{name} {direction} {abs(s.change_pct):.2f}%{vol_note}。"
            )

    # 2. 港股科技动向
    if hk_tech:
        big_hk = sorted([s for s in hk_tech if abs(s.change_pct) >= 5], key=lambda s: abs(s.change_pct), reverse=True)
        if big_hk:
            s = big_hk[0]
            name = _display_name(s).split()[-1] if " " in _display_name(s) else _display_name(s)
            direction = "暴涨" if s.is_up else "暴跌"
            emoji = "🟢" if s.is_up else "🔴"
            dynamics.append(
                f"{emoji} **港股科技异动**：{name} {direction} {abs(s.change_pct):.2f}%。"
            )

    # 3. LLM/AI 概念
    llm_tickers = {"0700.HK", "1810.HK", "9988.HK", "9888.HK", "0020.HK", "1024.HK"}
    llm = [s for s in stocks if s.ticker in llm_tickers]
    if llm:
        up_llm = [s for s in llm if s.is_up]
        if len(up_llm) >= len(llm) * 0.7:
            names = "、".join(_display_name(s).split()[-1] for s in up_llm[:4])
            dynamics.append(f"🤖 **LLM/AI 概念活跃**：{names} 等集体走强，AI 叙事持续发酵。")
        elif len(up_llm) <= len(llm) * 0.3:
            down_llm = [s for s in llm if not s.is_up][:4]
            names = "、".join(_display_name(s).split()[-1] for s in down_llm)
            dynamics.append(f"📉 **LLM/AI 概念承压**：{names} 等走弱，资金获利了结。")

    # 4. 跨市场联动
    if a_chip and hk_tech:
        avg_a = sum(s.change_pct for s in a_chip) / len(a_chip)
        avg_hk = sum(s.change_pct for s in hk_tech) / len(hk_tech)
        if avg_a >= 2 and avg_hk >= 2:
            dynamics.append("🔗 **A 股港股芯片/科技共振**：两个市场科技板块同步走强，显示资金对半导体/AI 方向的一致性看好。")
        elif avg_a <= -2 and avg_hk <= -2:
            dynamics.append("🔗 **A 股港股同步走弱**：两个市场科技板块均承压，市场风险偏好全面降温。")

    return dynamics[:4]


# ═══════════════════════════════════════════════════
# 一句话总结
# ═══════════════════════════════════════════════════

def _one_line_summary(stocks: list[StockQuote], indices: list[IndexQuote]) -> str:
    """生成 一句话总结。"""
    a_chip = [s for s in stocks if s.ticker in SECTORS.get("💾 A股芯片", set())]
    hk_tech = [s for s in stocks if s.ticker in SECTORS.get("🌐 港股科技", set())]
    up = [s for s in stocks if s.is_up]

    avg_a = sum(s.change_pct for s in a_chip) / len(a_chip) if a_chip else 0
    avg_hk = sum(s.change_pct for s in hk_tech) / len(hk_tech) if hk_tech else 0
    up_ratio = len(up) / len(stocks) if stocks else 0

    if stocks:
        biggest = max(stocks, key=lambda s: abs(s.change_pct))
        big_name = _display_name(biggest).split()[-1] if " " in _display_name(biggest) else _display_name(biggest)
    else:
        biggest, big_name = None, ""

    if avg_a >= 3 and avg_hk >= 3:
        return f"A 股芯片与港股科技同步大涨，{big_name} {biggest.change_sign}{biggest.change_pct:.1f}% 领跑全场。"
    elif avg_a >= 3:
        return f"A 股芯片板块独领风骚，{big_name} {biggest.change_sign}{biggest.change_pct:.1f}%，港股科技相对平淡。"
    elif avg_hk >= 3:
        return f"港股科技全面回暖，{big_name} {biggest.change_sign}{biggest.change_pct:.1f}%，A 股芯片表现平稳。"
    elif up_ratio <= 0.3:
        return "中港科技板块普遍走弱，市场避险情绪升温。"
    elif up_ratio >= 0.7:
        return f"中港科技全线收涨，{big_name} {biggest.change_sign}{biggest.change_pct:.1f}% 领涨。"
    else:
        return "中港科技板块涨跌互现，市场等待方向选择。"


# ═══════════════════════════════════════════════════
# 深度原因分析（市场特定包装，含涨跌停检测）
# ═══════════════════════════════════════════════════

def _cnhk_extra_checks(stock: StockQuote, direction: str, trend: dict) -> list[str]:
    """中港股额外检查：A 股涨跌停。"""
    extra = []
    is_a = ".SS" in stock.ticker or ".SZ" in stock.ticker
    if is_a and abs(stock.change_pct) >= 9.5:
        extra.append("触及涨跌停板，情绪极端化")
    return extra


def _deep_reason(stock: StockQuote, all_stocks: list[StockQuote]) -> str:
    """中港股个股深度原因分析。包装共享库的 deep_reason_base + 涨跌停检测。"""
    return _deep_reason_base(
        stock, all_stocks, SECTORS, CNHK_TREND_THRESHOLDS,
        extra_checks_fn=_cnhk_extra_checks,
    )


# ═══════════════════════════════════════════════════
# 📈 走势深度分析 (调用共享库)
# ═══════════════════════════════════════════════════

def _trend_analysis_section_wrapper(stocks: list[StockQuote], top_n: int = 3) -> str:
    """中港股走势深度分析（绑定 CNHK 阈值 + SECTORS + 显示名）。"""
    return _shared_tsa(
        stocks, SECTORS, top_n=top_n,
        trend_thresholds=CNHK_TREND_THRESHOLDS,
        name_fn=_display_name,
        extra_checks_fn=_cnhk_extra_checks,
    )


_trend_analysis_section = _trend_analysis_section_wrapper
