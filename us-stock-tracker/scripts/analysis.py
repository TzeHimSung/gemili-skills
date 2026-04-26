"""
共享分析引擎 — 大盘定调、板块分析、异动筛选、52周位置、叙事生成。
被 snapshot.py 和 daily_report.py 共用。
"""

import math
from typing import Optional

from common import StockQuote, IndexQuote, DailyBar, SECTORS, YAHOO_STOCKS_CN


def _icon(pct: float) -> str:
    return "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")


def _pct_str(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _display_name(stock: StockQuote) -> str:
    """获取带中文名的显示名，如 'NVDA 英伟达'。"""
    return YAHOO_STOCKS_CN.get(stock.ticker.upper(), stock.name)


# ═══════════════════════════════════════════════════
# 52周位置文案
# ═══════════════════════════════════════════════════

def _fifty_two_week_text(stock: StockQuote) -> str:
    """生成 52 周位置文案：'距高点 1.8% / 距低点 +100%'"""
    if stock.high_52w <= 0 or stock.low_52w <= 0:
        return "-"
    pct_h = (stock.high_52w - stock.price) / stock.high_52w * 100
    pct_l = (stock.price - stock.low_52w) / stock.low_52w * 100
    from_high = f"距高点 {pct_h:.1f}%"
    from_low = f"距低点 +{pct_l:.0f}%"
    return f"{from_high} / {from_low}"


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

    # 找出最强和最弱
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
        # 找同板块平均成交量
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

    # 小波动默认
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
        # 取 SOX 指数实际涨跌
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

    return unique[:4]  # 最多4条


# ═══════════════════════════════════════════════════
# 一句话总结
# ═══════════════════════════════════════════════════

def _one_line_summary(stocks: list[StockQuote], indices: list[IndexQuote]) -> str:
    """生成 一句话总结。"""
    semi = [s for s in stocks if s.ticker.upper() in SECTORS.get("💾 半导体", set())]
    avg_semi = sum(s.change_pct for s in semi) / len(semi) if semi else 0

    up = [s for s in stocks if s.is_up]
    up_ratio = len(up) / len(stocks) if stocks else 0

    # 找最突出的特征
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
        if cumulative_return >= 20:
            direction, label = "strong_up", "强势拉升"
        elif cumulative_return >= 7:
            direction, label = "up", "稳步上行"
        else:
            direction, label = "mild_up", "温和走强"
    else:
        if cumulative_return <= -20:
            direction, label = "strong_down", "持续下挫"
        elif cumulative_return <= -7:
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
    5. NVDA/龙头股联动（AI 叙事相关）
    """
    trend = _detect_trend(stock)
    reasons = []

    direction = trend.get("direction", "flat")
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
        if stock.ticker.upper() in {t.upper() for t in tickers}:
            peers = [s for s in all_stocks
                     if s.ticker.upper() in {t.upper() for t in tickers}
                     and s.ticker.upper() != stock.ticker.upper()]
            if peers:
                avg_peer = sum(s.change_pct for s in peers) / len(peers)
                sector_name = label.strip("🇨🇳💾☁️🛒 ")
                if direction in ("strong_up", "up") and stock.change_pct > avg_peer + 2:
                    reasons.append(f"显著跑赢{sector_name}板块（板块均涨{avg_peer:+.1f}%），个股α属性突出")
                elif direction in ("strong_down", "down") and stock.change_pct < avg_peer - 2:
                    reasons.append(f"显著跑输{sector_name}板块（板块均涨{avg_peer:+.1f}%），遭遇独立利空")
                elif direction in ("strong_up", "up") and avg_peer > 1:
                    reasons.append("受益于板块整体走强，联动效应明显")
                elif direction in ("strong_down", "down") and avg_peer < -1:
                    reasons.append("受板块整体走弱拖累，系统性回调")
            break

    if not reasons:
        reasons.append("技术面未见明确信号，建议结合财报/消息面判断")

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


# ═══════════════════════════════════════════════════
# 旧版兼容 analyze 函数
# ═══════════════════════════════════════════════════

def analyze(
    stocks: list[StockQuote],
    indices: list[IndexQuote],
    *,
    title: str = "市场分析",
    date_line: str = "",
) -> str:
    """
    根据行情数据生成完整分析 markdown（旧版兼容）。
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
