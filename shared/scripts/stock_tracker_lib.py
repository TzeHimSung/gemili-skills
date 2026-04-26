"""
共享股票追踪库 — us-stock-tracker 和 cnhk-stock-tracker 的公共代码。

提供：
  - 数据结构 (DailyBar, StockQuote, IndexQuote)
  - HTTP 客户端 (http_get, 参数化 Accept-Language)
  - 纯工具函数 (_icon, _pct_str, _fifty_two_week_text, _display_name)
  - 市场状态检测 (_is_us_dst, _market_hours_str, _check_market_status, _closed_reason)
  - 多日趋势分析 (_detect_trend, _deep_reason_base, _trend_analysis_section)
  - 52周位置检查 (_fifty_two_week_check)
  - 假期数据 (US/CN/HK 2026-2027)

市场特定逻辑（叙事生成、板块分析）保留在各 skill 的 analysis.py 中。
"""

import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import requests

# ═══════════════════════════════════════════════════
# HTTP
# ═══════════════════════════════════════════════════

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
NO_PROXY = {"http": None, "https": None}


def http_get(
    url: str,
    referer: str = "",
    timeout: int = 15,
    retries: int = 2,
    accept_lang: str = "en-US,en;q=0.9",
) -> requests.Response:
    """通用 HTTP GET，自动绕过代理，带重试。"""
    headers = {"User-Agent": UA, "Accept-Language": accept_lang}
    if referer:
        headers["Referer"] = referer

    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, proxies=NO_PROXY)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise last_exc  # type: ignore


# ═══════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════


@dataclass
class DailyBar:
    """单日 OHLC 数据点，用于多日趋势分析。"""
    date: str          # "2026-04-24"
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass
class StockQuote:
    """个股行情。"""
    ticker: str           # Yahoo: "NVDA" | "688981.SS" / Sina: "gb_nvda" | "sh688981"
    name: str
    price: float
    change_pct: float
    change_amt: float
    prev_close: float = 0.0
    high: float = 0.0
    low: float = 0.0
    high_52w: float = 0.0
    low_52w: float = 0.0
    volume: int = 0
    time_str: str = ""
    fetched_at: str = ""
    source: str = ""       # "sina" / "yahoo"
    history: list = field(default_factory=list)  # list[DailyBar] 多日走势

    @property
    def is_up(self) -> bool:
        return self.change_pct >= 0

    @property
    def change_sign(self) -> str:
        return "+" if self.is_up else ""


@dataclass
class IndexQuote:
    """指数行情。"""
    ticker: str
    name: str
    price: float
    change_pct: float
    change_amt: float = 0.0
    fetched_at: str = ""
    source: str = ""

    @property
    def is_up(self) -> bool:
        return self.change_pct >= 0

    @property
    def change_sign(self) -> str:
        return "+" if self.is_up else ""


# ═══════════════════════════════════════════════════
# 纯工具函数（无市场依赖）
# ═══════════════════════════════════════════════════


def icon(pct: float) -> str:
    return "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")


def pct_str(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def display_name(stock: StockQuote, name_map: dict[str, str]) -> str:
    """获取显示名（从 name_map 查找，fallback 到 stock.name）。"""
    return name_map.get(stock.ticker, name_map.get(stock.ticker.upper(), stock.name))


def fifty_two_week_text(stock: StockQuote) -> str:
    """生成 52 周位置文案：'距高点 1.8% / 距低点 +100%'"""
    if stock.high_52w <= 0 or stock.low_52w <= 0:
        return "-"
    pct_h = (stock.high_52w - stock.price) / stock.high_52w * 100
    pct_l = (stock.price - stock.low_52w) / stock.low_52w * 100
    return f"距高点 {pct_h:.1f}% / 距低点 +{pct_l:.0f}%"


def fifty_two_week_check(
    stocks: list[StockQuote],
) -> tuple[list[tuple[StockQuote, float]], list[tuple[StockQuote, float]]]:
    """检测接近 52 周高/低点的股票。"""
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


# ═══════════════════════════════════════════════════
# 市场状态检测
# ═══════════════════════════════════════════════════


def is_us_dst(d: date) -> bool:
    """判断给定日期是否在美国夏令时期间。
    美国夏令时：3月第二个周日 02:00 → 11月第一个周日 02:00"""
    # 3月第二个周日
    march_second_sun = date(d.year, 3, 1)
    while march_second_sun.weekday() != 6:  # 0=Mon, 6=Sun
        march_second_sun += timedelta(days=1)
    march_second_sun += timedelta(days=7)

    # 11月第一个周日
    nov_first_sun = date(d.year, 11, 1)
    while nov_first_sun.weekday() != 6:
        nov_first_sun += timedelta(days=1)

    return march_second_sun <= d < nov_first_sun


def us_market_hours_str(trade_date: date, with_date: bool = True) -> str:
    """返回美股交易日 + 美东/北京时间交易时段描述。"""
    if is_us_dst(trade_date):
        tz_part = "美东 EDT 9:30–16:00 / 北京 CST 21:30–次日04:00"
    else:
        tz_part = "美东 EST 9:30–16:00 / 北京 CST 22:30–次日05:00"

    if not with_date:
        return tz_part

    weekday_cn = "一二三四五六日"[trade_date.weekday()]
    date_part = trade_date.strftime(f"%Y年%m月%d日（周{weekday_cn}）")
    return f"{date_part} {tz_part}"


# 假期数据（2026-2027）
# 结构：{date: "假期名称"}
US_HOLIDAYS: dict[date, str] = {
    # 2026
    date(2026,1,1):   "元旦",         date(2026,1,19):  "马丁·路德·金纪念日",
    date(2026,2,16):  "总统日",       date(2026,4,3):   "耶稣受难日",
    date(2026,5,25):  "阵亡将士纪念日", date(2026,6,19): "六月节",
    date(2026,7,3):   "独立日（补休）",  date(2026,9,7):  "劳动节",
    date(2026,11,26): "感恩节",        date(2026,12,25): "圣诞节",
    # 2027
    date(2027,1,1):   "元旦",         date(2027,1,18):  "马丁·路德·金纪念日",
    date(2027,2,15):  "总统日",       date(2027,3,26):  "耶稣受难日",
    date(2027,5,31):  "阵亡将士纪念日", date(2027,6,18): "六月节",
    date(2027,7,5):   "独立日（补休）",  date(2027,9,6):  "劳动节",
    date(2027,11,25): "感恩节",        date(2027,12,24): "圣诞节",
}

CN_HOLIDAYS: dict[date, str] = {
    # 2026
    date(2026,1,1):   "元旦",         date(2026,1,2):   "元旦假期",
    date(2026,2,16):  "春节假期",      date(2026,2,17):  "春节假期",
    date(2026,2,18):  "春节假期",      date(2026,2,19):  "春节假期",
    date(2026,2,20):  "春节假期",
    date(2026,4,6):   "清明节（补休）",  date(2026,5,1):  "劳动节假期",
    date(2026,5,4):   "劳动节假期",     date(2026,5,5):  "劳动节假期",
    date(2026,6,19):  "端午节",
    date(2026,9,25):  "中秋节",
    date(2026,10,1):  "国庆节假期",     date(2026,10,2): "国庆节假期",
    date(2026,10,5):  "国庆节假期",     date(2026,10,6): "国庆节假期",
    date(2026,10,7):  "国庆节假期",
    # 2027
    date(2027,1,1):   "元旦",         date(2027,2,5):   "春节假期",
    date(2027,2,8):   "春节假期",      date(2027,2,9):  "春节假期",
    date(2027,2,10):  "春节假期",      date(2027,2,11): "春节假期",
    date(2027,2,12):  "春节假期",
    date(2027,4,5):   "清明节",        date(2027,5,3):  "劳动节假期",
    date(2027,5,4):   "劳动节假期",     date(2027,5,5): "劳动节假期",
    date(2027,6,9):   "端午节",
    date(2027,9,15):  "中秋节",
    date(2027,10,1):  "国庆节假期",     date(2027,10,4): "国庆节假期",
    date(2027,10,5):  "国庆节假期",     date(2027,10,6): "国庆节假期",
    date(2027,10,7):  "国庆节假期",
}

HK_HOLIDAYS: dict[date, str] = {
    # 2026
    date(2026,1,1):   "元旦",
    date(2026,2,16):  "农历年初一",     date(2026,2,17): "农历年初二",
    date(2026,2,18):  "农历年初三",
    date(2026,4,3):   "耶稣受难日",     date(2026,4,6):  "复活节星期一",
    date(2026,4,7):   "清明节",
    date(2026,5,1):   "劳动节",        date(2026,5,25): "佛诞",
    date(2026,6,19):  "端午节",
    date(2026,7,1):   "香港特区成立纪念日",
    date(2026,9,25):  "中秋节翌日",     date(2026,10,1): "国庆节",
    date(2026,10,26): "重阳节",         date(2026,12,25): "圣诞节",
    # 2027
    date(2027,1,1):   "元旦",
    date(2027,2,5):   "农历年初一",     date(2027,2,6):  "农历年初二",
    date(2027,2,8):   "农历年初三",
    date(2027,3,26):  "耶稣受难日",     date(2027,3,29): "复活节星期一",
    date(2027,4,5):   "清明节",
    date(2027,5,3):   "劳动节",        date(2027,5,13): "佛诞",
    date(2027,6,9):   "端午节",
    date(2027,7,1):   "香港特区成立纪念日",
    date(2027,9,16):  "中秋节翌日",     date(2027,10,1): "国庆节",
    date(2027,10,15): "重阳节",         date(2027,12,27): "圣诞节（补休）",
}


def check_market_status(
    stocks: list[StockQuote],
    indices: list[IndexQuote],
    *,
    hours_fn=None,
) -> dict:
    """根据抓取数据判断最近一个交易日是否在昨晚。

    Args:
        stocks, indices: 抓取到的行情数据
        hours_fn: 返回交易时段描述的函数，签名为 (trade_date, with_date) -> str
                  默认用于美股（含 DST），中港股可传自己的实现

    Returns:
        {"open": bool, "last_trade_date": date|None, "reason": str, "hours": str}
    """
    if hours_fn is None:
        hours_fn = us_market_hours_str

    all_items = list(stocks) + list(indices)
    if not all_items:
        return {"open": False, "last_trade_date": None,
                "reason": "无行情数据", "hours": hours_fn(date.today(), with_date=False)}

    # 从任意股票/指数取 Unix 时间戳
    timestamps = []
    for item in all_items:
        ts = getattr(item, "time_str", "")
        if ts and ts.lstrip("-").isdigit():
            timestamps.append(int(ts))
    if not timestamps:
        return {"open": False, "last_trade_date": None,
                "reason": "无有效时间戳", "hours": hours_fn(date.today(), with_date=False)}

    latest_ts = max(timestamps)
    latest_date = datetime.fromtimestamp(latest_ts).date()
    today = date.today()
    days_behind = (today - latest_date).days

    # 生成交易时段描述（基于实际交易日）
    hours = hours_fn(latest_date)

    # 规则：如果最新数据日期是工作日（周一~周五），且距今 ≤4 天，认为开盘
    # 4 天足够覆盖长周末（周五→周二）
    if latest_date.weekday() < 5 and days_behind <= 4:
        return {"open": True, "last_trade_date": latest_date,
                "reason": "", "hours": hours}

    # 休市时：不显示交易日日期，只显示时区
    hours_simple = hours_fn(today, with_date=False)
    return {"open": False, "last_trade_date": latest_date,
            "reason": f"最近交易日 {latest_date}，距今 {days_behind} 天",
            "hours": hours_simple}


def closed_reason(
    latest_date: date,
    days_behind: int,
    market: str = "美股",
) -> str:
    """根据最近交易日推断休市原因。"""
    weekday_cn = "一二三四五六日"[latest_date.weekday()]

    # 如果是周末
    if latest_date.weekday() >= 5:
        return f"最近交易日为周{weekday_cn}（{latest_date}），{market}周末休市"

    # 选择假期表
    if market == "美股":
        holidays = US_HOLIDAYS
    elif market == "A股":
        holidays = CN_HOLIDAYS
    elif market == "港股":
        holidays = HK_HOLIDAYS
    elif market == "中港":
        holidays = {**CN_HOLIDAYS, **HK_HOLIDAYS}
    else:
        holidays = {}

    if latest_date in holidays:
        return f"最近交易日 {latest_date}（周{weekday_cn}），{market}因**{holidays[latest_date]}**休市"

    # 工作日非假期但未开市 → 异常
    return f"最近交易日 {latest_date}（周{weekday_cn}），距今 {days_behind} 天，可能为临时休市或数据延迟"


# ═══════════════════════════════════════════════════
# 多日趋势分析（参数化阈值）
# ═══════════════════════════════════════════════════

# 默认趋势阈值（美股波动较大）
DEFAULT_TREND_THRESHOLDS = {
    "strong_up": 20,     # >= 20% 累积涨幅 → 强势拉升
    "up": 7,             # >= 7% → 稳步上行
    "strong_down": -20,
    "down": -7,
}

# 中港股趋势阈值（波动较小）
CNHK_TREND_THRESHOLDS = {
    "strong_up": 15,
    "up": 5,
    "strong_down": -15,
    "down": -5,
}


def detect_trend(
    stock: StockQuote,
    thresholds: dict[str, float] | None = None,
) -> dict:
    """分析个股多日走势趋势。

    基于 StockQuote.history（list[DailyBar]）计算：
    - 区间累积涨跌幅
    - 连续同向天数（最近 N 日）
    - 涨跌比
    - 量价确认度（近5日均量 vs 全区间均量）

    Args:
        stock: 含 history 的 StockQuote
        thresholds: 趋势分类阈值，默认使用美股 DEFAULT_TREND_THRESHOLDS
                    cnhk 技能应传入 CNHK_TREND_THRESHOLDS

    Returns:
        direction: strong_up / up / mild_up / flat / mild_down / down / strong_down
        label: 中文趋势标签
        cumulative_return, streak, up_ratio, up_days, dn_days, total_days
        vol_ratio, first_close, last_close, first_date, last_date
    """
    if thresholds is None:
        thresholds = DEFAULT_TREND_THRESHOLDS

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
        if cumulative_return >= thresholds["strong_up"]:
            direction, label = "strong_up", "强势拉升"
        elif cumulative_return >= thresholds["up"]:
            direction, label = "up", "稳步上行"
        else:
            direction, label = "mild_up", "温和走强"
    else:
        if cumulative_return <= thresholds["strong_down"]:
            direction, label = "strong_down", "持续下挫"
        elif cumulative_return <= thresholds["down"]:
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


def deep_reason_base(
    stock: StockQuote,
    all_stocks: list[StockQuote],
    sectors: dict[str, set[str]],
    trend_thresholds: dict[str, float] | None = None,
    extra_checks_fn=None,
) -> str:
    """生成深度原因分析的框架层。

    分析维度：
    1. 趋势形态（连续阳线/阴线、区间振幅）
    2. 量价关系（放量/缩量配合方向判断资金意图）
    3. 52周位置（距高/低点的空间）
    4. 板块联动（个股 vs 板块均值，判断 α/β 属性）
    5. 额外检查（由调用方传入回调，如 A 股涨跌停检测 / NVDA 联动）

    Args:
        stock: 目标个股
        all_stocks: 全量个股列表
        sectors: 板块分组 {sector_name: {ticker, ...}}
        trend_thresholds: 趋势阈值
        extra_checks_fn: 回调函数 (stock, direction, trend) -> list[str]
                         返回额外的原因字符串列表
    """
    if trend_thresholds is None:
        trend_thresholds = DEFAULT_TREND_THRESHOLDS

    trend = detect_trend(stock, trend_thresholds)
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
    for label, tickers in sectors.items():
        ticker_set = {t.upper() for t in tickers}
        if stock.ticker.upper() in ticker_set:
            peers = [s for s in all_stocks
                     if s.ticker.upper() in ticker_set
                     and s.ticker.upper() != stock.ticker.upper()]
            if peers:
                avg_peer = sum(s.change_pct for s in peers) / len(peers)
                # strip emoji from label
                sector_name = label.lstrip("🇨🇳🇺🇸💾☁️🛒🌐 ").strip()
                if direction in ("strong_up", "up") and stock.change_pct > avg_peer + 2:
                    reasons.append(f"显著跑赢{sector_name}板块（板块均涨{avg_peer:+.1f}%），个股α属性突出")
                elif direction in ("strong_down", "down") and stock.change_pct < avg_peer - 2:
                    reasons.append(f"显著跑输{sector_name}板块（板块均涨{avg_peer:+.1f}%），遭遇独立利空")
                elif direction in ("strong_up", "up") and avg_peer > 1:
                    reasons.append("受益于板块整体走强，联动效应明显")
                elif direction in ("strong_down", "down") and avg_peer < -1:
                    reasons.append("受板块整体走弱拖累，系统性回调")
            break

    # ── 5. 额外检查 ──
    if extra_checks_fn:
        extra = extra_checks_fn(stock, direction, trend)
        if extra:
            reasons.extend(extra)

    if not reasons:
        reasons.append("技术面未见明确信号，建议结合财报/消息面判断")

    return "；".join(reasons)


def trend_analysis_section(
    stocks: list[StockQuote],
    sectors: dict[str, set[str]],
    *,
    top_n: int = 3,
    trend_thresholds: dict[str, float] | None = None,
    name_fn=None,
    extra_checks_fn=None,
) -> str:
    """生成 📈 走势深度分析 段落。

    筛选有足够历史数据的个股，按趋势强度排序，
    选取 top_n 只最强上涨 + top_n 只最强下跌个股做深度拆解。

    Args:
        stocks: 全量个股
        sectors: 板块分组
        top_n: 各取几只
        trend_thresholds: 趋势阈值
        name_fn: 显示名函数 (stock) -> str
        extra_checks_fn: 额外检查函数 (stock) -> list[(condition, reason)]
    """
    if trend_thresholds is None:
        trend_thresholds = DEFAULT_TREND_THRESHOLDS
    if name_fn is None:
        name_fn = lambda s: s.name
    if extra_checks_fn is None:
        extra_checks_fn = lambda s, d, t: []

    # 需要有足够历史数据的个股
    candidates = [s for s in stocks if s.history and len(s.history) >= 5]
    if not candidates:
        return ""

    # 按趋势强度排序
    def _trend_strength(s):
        t = detect_trend(s, trend_thresholds)
        cum = abs(t.get("cumulative_return", 0))
        vol = t.get("vol_ratio", 1.0)
        return cum * (1 + max(0, vol - 1) * 0.5)

    sorted_stocks = sorted(candidates, key=_trend_strength, reverse=True)

    # 分组选出
    up_stocks = [s for s in sorted_stocks
                 if detect_trend(s, trend_thresholds)["direction"] in ("strong_up", "up", "mild_up")]
    down_stocks = [s for s in sorted_stocks
                   if detect_trend(s, trend_thresholds)["direction"] in ("strong_down", "down", "mild_down")]

    selected = []
    selected.extend(up_stocks[:top_n])
    selected.extend(down_stocks[:top_n])

    if not selected:
        return ""

    lines = ["📈 走势深度分析", ""]

    for s in selected:
        trend = detect_trend(s, trend_thresholds)
        name = name_fn(s)
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
        lines.append(f"**可能原因**：{deep_reason_base(s, stocks, sectors, trend_thresholds, extra_checks_fn(s))}")
        lines.append("")

    return "\n".join(lines)
