"""
报表生成器
合并各企划 JSON 数据，生成统一倒计时 markdown 报表。
"""

import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from common import load_events


def _countdown_icon(days: int) -> str:
    """倒计时图标。"""
    if days < 0:
        return "✅"  # 已过期
    if days <= 3:
        return "🔴"
    if days <= 7:
        return "🔥"
    if days <= 30:
        return "⏳"
    return "📅"


def _short_date(date_str: str) -> str:
    """ISO date → 简短中文日期。"""
    d = datetime.fromisoformat(date_str)
    return f"{d.month}月{d.day}日"


def _format_artists(artists: list[str], max_display: int = 2) -> str:
    """格式化艺人列表，超过 max_display 时截断。"""
    if not artists:
        return "—"
    if len(artists) <= max_display:
        return "、".join(artists)
    return f"{'、'.join(artists[:max_display])} +{len(artists) - max_display}"


def _truncate_title(title: str, max_len: int = 50) -> str:
    """截断过长的标题。"""
    if len(title) <= max_len:
        return title
    return title[:max_len - 1] + "…"


def _clean_telegram(text: str) -> str:
    """Telegram markdown 兼容清洗（不破坏表格分隔行）。"""
    return text.replace("「", "").replace("」", "").replace("｜", "·")


def _table_cell(text: object, *, telegram: bool = False) -> str:
    """清洗 markdown 表格单元格，防止标题/场地里的竖线拆列。"""
    value = str(text).replace("\r", " ").replace("\n", " ")
    value = value.replace("|", "／").replace("｜", "／")
    value = " ".join(value.split())
    if telegram:
        value = _clean_telegram(value)
    return value or "—"


# ── 企划分组 ───────────────────────────────────────────────

FRANCHISE_ORDER = ["BanG Dream!", "LoveLive!", "アイドルマスター"]
FRANCHISE_EMOJI = {
    "BanG Dream!": "🎸",
    "LoveLive!": "🎤",
    "アイドルマスター": "🎭",
}


def generate_markdown(
    data_dir: str | Path,
    platform: str = "general",
    today: date | None = None,
) -> str:
    """
    生成报表的 markdown 字符串。
    
    platform:
        - "general": 全功能（微信/QQ 用）
        - "telegram": 额外清洗特殊字符
    """
    if today is None:
        today = date.today()

    data_dir = Path(data_dir)

    # 加载各企划数据
    all_events: list[dict] = []
    for fname in ("bandori.json", "lovelive.json", "idolmaster.json"):
        path = data_dir / fname
        if path.exists():
            events = load_events(str(path))
            # 超时丢弃
            for ev in events:
                d = datetime.fromisoformat(ev["date"]).date()
                ev["_date_obj"] = d
                ev["_days"] = (d - today).days
            all_events.extend(events)
        else:
            print(f"  ⚠ 缺少数据文件: {path}", file=sys.stderr)

    if not all_events:
        return "_暂无 live 活动数据。_"

    # 过滤已结束的活动：日报只发送今天及未来的 live。
    # 爬虫数据可能仍保留过去数日作为本地参考，但对用户推送不展示“已结束”行。
    all_events = [e for e in all_events if e["_date_obj"] >= today]
    if not all_events:
        return "_暂无未来 live 活动数据。_"
    all_events.sort(key=lambda e: e["_days"])

    # ── 表头 ──
    date_label = f"{today.month}月{today.day}日"
    weekday_cn = "一二三四五六日"[today.weekday()]
    lines: list[str] = [
        f"## 🎵 Anison Live 倒计时 — {date_label} (星期{weekday_cn})",
        "",
    ]

    # ── 企划分表 ──
    for franchise in FRANCHISE_ORDER:
        f_events = [e for e in all_events if e["franchise"] == franchise]
        if not f_events:
            continue

        emoji = FRANCHISE_EMOJI.get(franchise, "🎵")
        lines.append(f"### {emoji} {franchise}")
        lines.append("")
        lines.append("| 倒计时 | 日期 | 活动 | 艺人 | 场地 |")
        lines.append("|---|---|---|---|---|")

        for ev in f_events:
            icon = _countdown_icon(ev["_days"])
            cd_display = (
                "今天!" if ev["_days"] == 0
                else f"剩{ev['_days']}天" if ev["_days"] > 0
                else f"已结束"
            )
            # 高亮临近活动
            if ev["_days"] <= 7 and ev["_days"] >= 0:
                cd_display = f"**{icon} {cd_display}**"

            title = _truncate_title(ev.get("title", "?"))
            artists = _format_artists(ev.get("artists", []))
            venue = ev.get("venue", "未定")
            s_date = _short_date(ev["date"])
            # 标记フェス
            if ev.get("category") == "フェス":
                title = f"🎪 {title}"

            row = (
                f"| {_table_cell(cd_display, telegram=platform == 'telegram')} "
                f"| {_table_cell(s_date, telegram=platform == 'telegram')} "
                f"| {_table_cell(title, telegram=platform == 'telegram')} "
                f"| {_table_cell(artists, telegram=platform == 'telegram')} "
                f"| {_table_cell(venue, telegram=platform == 'telegram')} |"
            )
            lines.append(row)

        # 小计
        upcoming = sum(1 for e in f_events if e["_days"] >= 0)
        lines.append(f"*{franchise} 未来活动: {upcoming} 场*")
        lines.append("")

    # ── 月别分布 ──
    lines.append("---")
    lines.append("")
    lines.append("### 📊 月度活动分布")
    lines.append("")
    month_counts: dict[int, int] = {}
    for ev in all_events:
        m = ev["_date_obj"].month
        month_counts[m] = month_counts.get(m, 0) + 1

    max_count = max(month_counts.values()) if month_counts else 1
    for m in sorted(month_counts):
        count = month_counts[m]
        bar = "█" * max(1, int(count / max_count * 20))
        lines.append(f"`{m:2d}月` {bar} {count} 场")

    # ── 图例 & 更新时间 ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("📅 图例：🔴 3天内 · 🔥 7天内 · ⏳ 30天内 · 📅 未来 · 🎪 合同/フェス")
    lines.append(f"_更新时间：{today.isoformat()} T{datetime.now().strftime('%H:%M')}_")

    text = "\n".join(lines)

    # Telegram 清洗
    if platform == "telegram":
        text = _clean_telegram(text)

    return text


# ── CLI ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="生成 Anison Live 倒计时报表")
    parser.add_argument(
        "data_dir", nargs="?", default="data",
        help="爬虫输出 JSON 的目录 (默认: data/)",
    )
    parser.add_argument(
        "-p", "--platform", default="general",
        choices=["general", "telegram"],
        help="目标平台 (默认: general)",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="输出文件路径 (默认: stdout)",
    )
    args = parser.parse_args()

    report = generate_markdown(args.data_dir, args.platform)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"✅ 报表已写入 {args.output}", file=sys.stderr)
    else:
        print(report)
