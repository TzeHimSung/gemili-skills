"""
BanG Dream! 官方站爬虫
来源：https://bang-dream.com/events/
输出：JSON 事件列表，含多日巡回拆分 + 场地映射
"""

import re
import json
import sys
from datetime import date
from pathlib import Path

from datetime import timedelta

from common import (
    http_get, strip_html, split_tour_dates,
    parse_jp_date, countdown_days, map_venue,
    save_events,
)

BASE_URL = "https://bang-dream.com/events/"

# 已知 BanG Dream 艺人名 → 系列映射
ARTIST_SERIES: dict[str, str] = {
    "Poppin'Party": "Bandori",
    "Roselia": "Bandori",
    "RAISE A SUILEN": "Bandori",
    "Morfonica": "Bandori",
    "MyGO!!!!!": "Bandori",
    "Ave Mujica": "Bandori",
    "夢限大みゅーたいぷ": "Bandori",
    "Afterglow": "Bandori",
    "Pastel＊Palettes": "Bandori",
    "ハロー、ハッピーワールド": "Bandori",
    "FLOW": "Bandori",
    "FLOW THE FESTIVAL": "Bandori",
}

# 已确认非 live 的类别（イベント/フェス 仍纳入但标记）
SKIP_CATEGORIES = {"グッズ", "リリース", "配信", "メディア"}


def parse_article(article_html: str) -> dict | None:
    """解析一个 <article> 块，返回事件 dict 或 None。"""
    # 类别
    cat_m = re.search(
        r'p-live-event-list__item-category.*?<span>(.*?)</span>',
        article_html, re.DOTALL,
    )
    category = strip_html(cat_m.group(1)) if cat_m else "ライブ"
    if category in SKIP_CATEGORIES:
        return None

    # 标题
    title_m = re.search(
        r'p-live-event-list__item-title[^>]*>(.*?)</div>',
        article_html, re.DOTALL,
    )
    title = strip_html(title_m.group(1)) if title_m else "?"

    # 日期块
    date_m = re.search(
        r'p-live-event-list__item-date.*?<p>(.*?)</p>',
        article_html, re.DOTALL,
    )
    date_text = strip_html(date_m.group(1)) if date_m else "?"

    # 场地
    venue_m = re.search(
        r'p-live-event-list__item-place.*?<p>(.*?)</p>',
        article_html, re.DOTALL,
    )
    venue_raw = strip_html(venue_m.group(1)) if venue_m else "?"

    # 艺人
    artist_matches = re.findall(
        r'p-live-event-list__item-artist-item[^>]*>(.*?)</span>',
        article_html,
    )
    artists = [strip_html(a) for a in artist_matches]

    # 链接
    link_m = re.search(
        r'<a\s+href="([^"]+)"',
        article_html,
    )
    detail_link = f"https://bang-dream.com{link_m.group(1)}" if link_m else ""

    return {
        "source": "bang-dream.com",
        "title": title,
        "date_text": date_text,
        "venue_raw": venue_raw,
        "artists": artists,
        "category": category,
        "detail_link": detail_link,
    }


def scrape() -> list[dict]:
    """主抓取逻辑：返回扁平化的单日事件列表。"""
    today = date.today()
    cutoff = today + timedelta(days=400)  # 超过一年的忽略

    resp = http_get(
        BASE_URL,
        referer="https://bang-dream.com/events/",
    )
    html = resp.text

    articles = re.findall(
        r'<article class="p-live-event-list__item">(.*?)</article>',
        html,
        re.DOTALL,
    )
    print(f"[bangdream] 找到 {len(articles)} 个 article 块", file=sys.stderr)

    events: list[dict] = []
    for art in articles:
        raw = parse_article(art)
        if raw is None:
            continue

        # 拆分多日巡回
        if "・" in raw["date_text"]:
            tours = split_tour_dates(raw["date_text"], raw["venue_raw"])
            for full_date, venue in tours:
                d = parse_jp_date(full_date)
                if d is None:
                    continue
                if d > cutoff:
                    continue
                cd = countdown_days(d)
                record = {
                    "franchise": "BanG Dream!",
                    "title": raw["title"],
                    "date": d.isoformat(),
                    "weekday": "月火水木金土日"[d.weekday()],
                    "venue": map_venue(venue),
                    "venue_raw": venue,
                    "artists": raw["artists"],
                    "category": raw["category"],
                    "countdown_days": cd,
                    "detail_link": raw["detail_link"],
                    "is_tour": True,
                }
                events.append(record)
        else:
            d = parse_jp_date(raw["date_text"])
            if d is None:
                print(f"  ⚠ 无法解析日期: {raw['date_text']}", file=sys.stderr)
                continue
            if d > cutoff:
                continue
            cd = countdown_days(d)
            record = {
                "franchise": "BanG Dream!",
                "title": raw["title"],
                "date": d.isoformat(),
                "weekday": "月火水木金土日"[d.weekday()],
                "venue": map_venue(raw["venue_raw"]),
                "venue_raw": raw["venue_raw"],
                "artists": raw["artists"],
                "category": raw["category"],
                "countdown_days": cd,
                "detail_link": raw["detail_link"],
                "is_tour": False,
            }
            events.append(record)

    # 去重（同日期 + 同标题）
    seen = set()
    deduped = []
    for e in events:
        key = (e["date"], e["title"], e.get("venue_raw", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    # 按日期排序
    deduped.sort(key=lambda e: e["date"])
    print(f"[bangdream] 解析出 {len(deduped)} 条事件", file=sys.stderr)
    return deduped


# ── CLI ─────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import timedelta

    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)

    events = scrape()
    out_path = out_dir / "bandori.json"
    save_events(events, str(out_path))
    print(f"✅ 已写入 {out_path} ({len(events)} 条)", file=sys.stderr)
