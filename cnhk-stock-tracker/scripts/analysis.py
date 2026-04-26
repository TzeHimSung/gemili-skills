"""
共享分析引擎 — 大盘定调、板块分析、异动筛选、52周位置、叙事生成。
适配中港股市：A 股芯片 + 港股科技。
"""

from common import StockQuote, IndexQuote, DailyBar, SECTORS, YAHOO_STOCKS_CN, market_hours_display


def _icon(pct: float) -> str:
    return "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")


def _pct_str(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _display_name(stock: StockQuote) -> str:
    """获取带中文名的显示名。"""
    return YAHOO_STOCKS_CN.get(stock.ticker, stock.name)


# ═══════════════════════════════════════════════════
# 52周位置文案
# ═══════════════════════════════════════════════════

def _fifty_two_week_text(stock: StockQuote) -> str:
    """生成 52 周位置文案。"""
    if stock.high_52w <= 0 or stock.low_52w <= 0:
        return "-"
    pct_h = (stock.high_52w - stock.price) / stock.high_52w * 100
    pct_l = (stock.price - stock.low_52w) / stock.low_52w * 100
    return f"距高点 {pct_h:.1f}% / 距低点 +{pct_l:.0f}%"


# ═══════════════════════════════════════════════════
# 大盘概览叙事
# ═══════════════════════════════════════════════════

def _index_narrative(indices: list[IndexQuote]) -> str:
    """生成大盘概述。"""
    if not indices:
        return "暂无指数数据"

    up = [i for i in indices if i.is_up]
    dn = [i for i in indices if not i.is_up]

    # 按市场分组
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
    is_hk = ".HK" in stock.ticker

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

    # 小波动默认
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

    # A 股芯片
    a_chip = [s for s in stocks if s.ticker in SECTORS.get("💾 A股芯片", set())]
    hk_tech = [s for s in stocks if s.ticker in SECTORS.get("🌐 港股科技", set())]

    if a_chip:
        avg_a = sum(s.change_pct for s in a_chip) / len(a_chip)
        top_a = max(a_chip, key=lambda s: s.change_pct)
        bot_a = min(a_chip, key=lambda s: s.change_pct)
        name_top = _display_name(top_a).split()[-1] if " " in _display_name(top_a) else _display_name(top_a)
        if avg_a >= 3:
            lines.append(
                f"A 股芯片板块全面爆发，{name_top}领涨 {top_a.change_sign}{top_a.change_pct:.2f}%，"
                f"板块均涨{avg_a:.1f}%。"
            )
        elif avg_a >= 1:
            lines.append(f"A 股芯片温和走强，{name_top}领涨{top_a.change_sign}{top_a.change_pct:.2f}%，板块均涨{avg_a:.1f}%。")
        elif avg_a <= -2:
            name_bot = _display_name(bot_a).split()[-1] if " " in _display_name(bot_a) else _display_name(bot_a)
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
                vol_note = f"，成交额{s.volume/1e8:.1f}亿"
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
            names = "、".join(_display_name(s).split()[-1] for s in llm if not s.is_up)[:4]
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

    # 找最强个股
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
# 多日趋势检测
# ═══════════════════════════════════════════════════

def _detect_trend(stock: StockQuote) -> dict:
    """分析个股多日走势趋势。

    基于 StockQuote.history（list[DailyBar]）计算：
    - 区间累积涨跌幅
    - 连续同向天数（最近 N 日）
    - 涨跌比
    - 量价确认度（近5日均量 vs 全区间均量）

    返回趋势分析字典：
        direction: strong_up / up / mild_up / flat / mild_down / down / strong_down
        label: 中文趋势标签
        cumulative_return: 区间累积涨跌幅(%)
        streak: 连续同向天数（正=连阳，负=连阴）
        up_ratio, up_days, dn_days, total_days
        vol_ratio: 近5日均量 / 全区间均量
        first_close, last_close, first_date, last_date
    """
    history = stock.history
    if not history or len(history) < 3:
        return {
            "direction": "flat", "label": "横盘整理", "score": 0,
            "cumulative_return": 0, "streak": 0,
            "up_ratio": 0.5, "up_days": 0, "dn_days": 0, "total_days": 0,
            "vol_ratio": 1.0,
            "first_close": 0, "last_close": stock.price,
            "first_date": "", "last_date": "",
        }

    # 逐日涨跌幅
    daily_changes = []
    for i in range(1, len(history)):
        prev_close = history[i - 1].close
        if prev_close > 0:
            pct = (history[i].close - prev_close) / prev_close * 100
            daily_changes.append(pct)

    if not daily_changes:
        return {
            "direction": "flat", "label": "横盘整理", "score": 0,
            "cumulative_return": 0, "streak": 0,
            "up_ratio": 0.5, "up_days": 0, "dn_days": 0, "total_days": 0,
            "vol_ratio": 1.0,
            "first_close": history[0].close, "last_close": history[-1].close,
            "first_date": history[0].date, "last_date": history[-1].date,
        }

    # 累积收益
    first_close = history[0].close
    last_close = history[-1].close
    cumulative_return = (last_close - first_close) / first_close * 100 if first_close > 0 else 0

    # 最近 N 天连续同向天数
    recent = daily_changes[-10:] if len(daily_changes) >= 10 else daily_changes
    up_streak, down_streak = 0, 0
    for chg in reversed(recent):
        if chg > 0.05:          # >0.05% 算有效上涨
            up_streak += 1
            if down_streak > 0:
                break
        elif chg < -0.05:       # <-0.05% 算有效下跌
            down_streak += 1
            if up_streak > 0:
                break
        else:
            break
    streak = up_streak if up_streak >= down_streak else -down_streak

    # 涨跌比
    up_days = sum(1 for c in daily_changes if c > 0.05)
    dn_days = sum(1 for c in daily_changes if c < -0.05)
    up_ratio = up_days / len(daily_changes) if daily_changes else 0.5

    # 量价确认：近5日均量 vs 全区间均量
    all_vols = [b.volume for b in history if b.volume > 0]
    recent_vols = all_vols[-5:] if len(all_vols) >= 5 else all_vols
    avg_vol = sum(all_vols) / len(all_vols) if all_vols else 0
    avg_recent_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 0
    vol_ratio = avg_recent_vol / avg_vol if avg_vol > 0 else 1.0

    # 分类
    abs_ret = abs(cumulative_return)
    if abs_ret < 2 and abs(streak) < 2:
        direction, label = "flat", "横盘整理"
    elif cumulative_return > 0:
        if cumulative_return >= 15:
            direction, label = "strong_up", "强势拉升"
        elif cumulative_return >= 5:
            direction, label = "up", "稳步上行"
        else:
            direction, label = "mild_up", "温和走强"
    else:
        if cumulative_return <= -15:
            direction, label = "strong_down", "持续下挫"
        elif cumulative_return <= -5:
            direction, label = "down", "弱势下行"
        else:
            direction, label = "mild_down", "小幅走弱"

    return {
        "direction": direction,
        "label": label,
        "score": round(cumulative_return, 2),
        "cumulative_return": round(cumulative_return, 2),
        "streak": streak,
        "up_ratio": round(up_ratio, 2),
        "up_days": up_days,
        "dn_days": dn_days,
        "total_days": len(daily_changes),
        "vol_ratio": round(vol_ratio, 2),
        "first_close": round(first_close, 2),
        "last_close": round(last_close, 2),
        "first_date": history[0].date,
        "last_date": history[-1].date,
    }


# ═══════════════════════════════════════════════════
# 深度原因分析（强势 / 弱势个股）
# ═══════════════════════════════════════════════════

def _deep_reason(stock: StockQuote, all_stocks: list[StockQuote]) -> str:
    """为强势/弱势个股生成深度原因分析。

    综合分析五个维度：
    1. 趋势形态（连续阳线/阴线、区间振幅）
    2. 量价关系（放量/缩量配合方向判断资金意图）
    3. 52周位置（距高/低点的空间）
    4. 板块联动（个股 vs 板块均值，判断 α/β 属性）
    5. A 股涨跌停检测
    """
    trend = _detect_trend(stock)
    reasons = []

    direction = trend.get("direction", "flat")
    cumulative = trend.get("cumulative_return", 0)
    streak = trend.get("streak", 0)
    vol_ratio = trend.get("vol_ratio", 1.0)

    # ── 1. 趋势形态 ──
    if streak >= 4:
        reasons.append(f"连续 {streak} 日收阳，多头排列明显")
    elif streak <= -4:
        reasons.append(f"连续 {abs(streak)} 日收阴，空头力量持续释放")
    elif streak >= 2:
        reasons.append(f"近 {abs(streak)} 日连续走强")
    elif streak <= -2:
        reasons.append(f"近 {abs(streak)} 日连续走弱")

    # ── 2. 量价关系 ──
    if direction in ("strong_up", "up") and vol_ratio > 1.3:
        reasons.append("放量上涨，资金介入积极")
    elif direction in ("strong_up", "up") and vol_ratio < 0.8:
        reasons.append("缩量上涨，需警惕动能衰减")
    elif direction in ("strong_down", "down") and vol_ratio > 1.3:
        reasons.append("放量下跌，资金出逃明显")
    elif direction in ("strong_down", "down") and vol_ratio > 1.0:
        reasons.append("下跌伴随量能放大，抛压较重")
    elif vol_ratio > 1.5:
        reasons.append("交投显著活跃，多空博弈激烈")

    # ── 3. 52周位置 ──
    if stock.high_52w > 0:
        pct_from_high = (stock.high_52w - stock.price) / stock.high_52w * 100
        if direction in ("strong_up", "up") and pct_from_high <= 3:
            reasons.append(f"已逼近52周高点（距高点仅 {pct_from_high:.1f}%），上方阻力需关注")
        elif direction in ("strong_up", "up") and pct_from_high <= 10:
            reasons.append(f"距52周高点 {pct_from_high:.0f}%，仍有上行空间")
        elif direction in ("strong_down", "down") and pct_from_high > 30:
            reasons.append(f"距52周高点已回落 {pct_from_high:.0f}%，处于低位区间")

    if stock.low_52w > 0:
        pct_from_low = (stock.price - stock.low_52w) / stock.low_52w * 100
        if direction in ("strong_down", "down") and pct_from_low <= 10:
            reasons.append(f"逼近52周低点（距低点仅 +{pct_from_low:.0f}%），下方支撑面临考验")
        elif direction in ("strong_up", "up") and pct_from_low > 50:
            reasons.append(f"已从52周低点反弹 +{pct_from_low:.0f}%，确认底部反转")

    # ── 4. 板块联动 ──
    for label, tickers in SECTORS.items():
        if stock.ticker in tickers:
            peers = [s for s in all_stocks if s.ticker in tickers and s.ticker != stock.ticker]
            if peers:
                avg_peer = sum(s.change_pct for s in peers) / len(peers)
                if direction in ("strong_up", "up") and stock.change_pct > avg_peer + 2:
                    sector_name = label.strip("💾🌐 ")
                    reasons.append(f"显著跑赢{sector_name}板块（板块均涨{avg_peer:+.1f}%），个股α属性突出")
                elif direction in ("strong_down", "down") and stock.change_pct < avg_peer - 2:
                    sector_name = label.strip("💾🌐 ")
                    reasons.append(f"显著跑输{sector_name}板块（板块均涨{avg_peer:+.1f}%），遭遇独立利空")
                elif direction in ("strong_up", "up") and avg_peer > 1:
                    reasons.append("受益于板块整体走强，联动效应明显")
                elif direction in ("strong_down", "down") and avg_peer < -1:
                    reasons.append("受板块整体走弱拖累，系统性回调")
            break

    # ── 5. A 股涨跌停 ──
    is_a = ".SS" in stock.ticker or ".SZ" in stock.ticker
    if is_a and abs(stock.change_pct) >= 9.5:
        reasons.append("触及涨跌停板，情绪极端化")

    if not reasons:
        reasons.append("技术面未见明确信号，建议结合基本面消息判断")

    return "；".join(reasons)


# ═══════════════════════════════════════════════════
# 📈 走势深度分析 段落生成
# ═══════════════════════════════════════════════════

def _trend_analysis_section(stocks: list[StockQuote], top_n: int = 3) -> str:
    """生成 📈 走势深度分析 段落。

    筛选有足够历史数据的个股，按趋势强度排序，
    选取 top_n 只最强上涨 + top_n 只最强下跌个股做深度拆解。
    """
    # 需要有足够历史数据的个股
    candidates = [s for s in stocks if s.history and len(s.history) >= 5]
    if not candidates:
        return ""

    # 按趋势强度排序（累积涨跌幅 × 量能放大加成）
    def _trend_strength(s):
        t = _detect_trend(s)
        cum = abs(t.get("cumulative_return", 0))
        vol = t.get("vol_ratio", 1.0)
        return cum * (1 + max(0, vol - 1) * 0.5)

    sorted_stocks = sorted(candidates, key=_trend_strength, reverse=True)

    # 分组选出
    up_stocks = [s for s in sorted_stocks
                 if _detect_trend(s)["direction"] in ("strong_up", "up", "mild_up")]
    down_stocks = [s for s in sorted_stocks
                   if _detect_trend(s)["direction"] in ("strong_down", "down", "mild_down")]

    selected = []
    selected.extend(up_stocks[:top_n])
    selected.extend(down_stocks[:top_n])

    if not selected:
        return ""

    lines = ["📈 走势深度分析", ""]

    for s in selected:
        trend = _detect_trend(s)
        name = _display_name(s)
        is_up = trend["direction"] in ("strong_up", "up", "mild_up")
        emoji = "🟢" if is_up else "🔴"

        lines.append(f"### {emoji} {name}")
        lines.append("")

        # 趋势概况
        date_range = f"{trend['first_date']} → {trend['last_date']}"
        lines.append(f"- **走势形态**：{trend['label']}（{date_range}）")
        lines.append(f"- **区间涨跌**：{trend['cumulative_return']:+.2f}%")
        lines.append(f"- **涨跌比**：{trend['up_days']}涨{trend['dn_days']}跌"
                     f"（共{trend['total_days']}个交易日）")

        if abs(trend.get("streak", 0)) >= 2:
            direction_text = "连阳" if trend["streak"] > 0 else "连阴"
            lines.append(f"- **最近走势**：{abs(trend['streak'])}日{direction_text}")

        # 量能
        vol_pct = trend["vol_ratio"] * 100
        if trend["vol_ratio"] > 1.3:
            vol_note = "（显著放量 🔥）"
        elif trend["vol_ratio"] > 1.1:
            vol_note = "（温和放量）"
        elif trend["vol_ratio"] < 0.8:
            vol_note = "（缩量 ⚠️）"
        else:
            vol_note = ""
        lines.append(f"- **量能变化**：近5日均量为区间均量的 {vol_pct:.0f}%{vol_note}")

        # 52周位置
        if s.high_52w > 0 and s.low_52w > 0:
            pct_h = (s.high_52w - s.price) / s.high_52w * 100
            pct_l = (s.price - s.low_52w) / s.low_52w * 100
            lines.append(f"- **52周位置**：距高点 {pct_h:.1f}% / 距低点 +{pct_l:.0f}%")

        lines.append("")
        lines.append(f"**可能原因**：{_deep_reason(s, stocks)}")
        lines.append("")

    return "\n".join(lines)
