"""
偶像大师系列爬虫 + eplus 购票站兜底
来源：idolmaster-official.jp + eplus.jp
输出：JSON 事件列表
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path

from common import (
    http_get, strip_html, parse_jp_date,
    countdown_days, map_venue, save_events,
    is_non_live_keyword,
)

# ── 偶像大师官方站 ──────────────────────────────────────────
# ⚠️ /live_event/ 页面完全 JS 渲染，Python requests 只能拿到空 HTML shell
# 但各品牌个别イベント頁如果是直リンク（/live_event/mr_idolworld2026/ 等），
# 有时包含静态 HTML

IMAS_SITES: list[dict] = [
    {
        "name": "765AS",
        "url": "https://idolmaster-official.jp/live_event/",
        "artist": "765PRO ALLSTARS",
        "referer": "https://idolmaster-official.jp/",
    },
    {
        "name": "シンデレラガールズ",
        "url": "https://idolmaster-official.jp/live_event/",
        "artist": "シンデレラガールズ",
        "referer": "https://idolmaster-official.jp/",
    },
    {
        "name": "MILLION LIVE!",
        "url": "https://idolmaster-official.jp/live_event/",
        "artist": "MILLION STARS",
        "referer": "https://idolmaster-official.jp/",
    },
    {
        "name": "SideM",
        "url": "https://idolmaster-official.jp/live_event/",
        "artist": "SideM",
        "referer": "https://idolmaster-official.jp/",
    },
    {
        "name": "シャイニーカラーズ",
        "url": "https://idolmaster-official.jp/live_event/",
        "artist": "シャイニーカラーズ",
        "referer": "https://idolmaster-official.jp/",
    },
    {
        "name": "学園アイマス",
        "url": "https://idolmaster-official.jp/live_event/",
        "artist": "学園アイドルマスター",
        "referer": "https://idolmaster-official.jp/",
    },
]

# ── eplus JSON-LD 配置 ──────────────────────────────────────

EPLUS_ARTIST_IDS = {
    "LoveLive!": ["0000150880"],
    "BanG Dream!": ["0000084669", "0000159108"],
    "アイドルマスター": ["0000031068", "0000126198"],
}

EPLUS_BASE = "https://eplus.jp/sf/word/"


def _try_official_site() -> list[dict]:
    """尝试从官方站抓取（大概率失败，返回空列表）。"""
    events: list[dict] = []
    today = date.today()

    try:
        resp = http_get(
            "https://idolmaster-official.jp/live_event/",
            referer="https://idolmaster-official.jp/",
        )
        html = resp.text

        # 检查是否有可解析的内容
        date_pattern = re.compile(
            r"(?P<y>\d{4})[年/.\-](?P<m>\d{1,2})[月/.\-](?P<d>\d{1,2})日?"
        )
        matches = list(date_pattern.finditer(html))
        if not matches:
            print(
                "  ⚠ 官方站无可用数据（JS 渲染空壳）",
                file=sys.stderr,
            )
            return events

        for m in matches:
            try:
                d = date(int(m["y"]), int(m["m"]), int(m["d"]))
            except ValueError:
                continue
            if d < today or d > today + timedelta(days=400):
                continue
            ctx_start = max(0, m.start() - 300)
            ctx_end = min(len(html), m.end() + 300)
            context = strip_html(html[ctx_start:ctx_end])

            # 尝试识别品牌
            series = "アイドルマスター"
            for kw in ["シンデレラ", "MILLION", "SideM", "シャイニー", "学園", "765"]:
                if kw in context:
                    series = {
                        "シンデレラ": "シンデレラガールズ",
                        "MILLION": "MILLION LIVE!",
                        "SideM": "SideM",
                        "シャイニー": "シャイニーカラーズ",
                        "学園": "学園アイマス",
                        "765": "765AS",
                    }[kw]
                    break

            title = context[:80]
            ev = {
                "franchise": "アイドルマスター",
                "series": series,
                "title": title,
                "date": d.isoformat(),
                "weekday": "月火水木金土日"[d.weekday()],
                "venue": "未定",
                "venue_raw": "",
                "artists": [],
                "category": "ライブ",
                "countdown_days": countdown_days(d),
                "detail_link": "https://idolmaster-official.jp/live_event/",
                "source": "idolmaster-official.jp",
            }
            events.append(ev)
    except Exception as exc:
        print(f"  ⚠ 官方站异常: {exc}", file=sys.stderr)

    return events


def _eplus_jsonld_scrape() -> list[dict]:
    """
    从 eplus 的 JSON-LD 中提取事件。
    对每个企划的 artist IDs 发起请求，解析 Event schema。
    """
    events: list[dict] = []
    today = date.today()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9",
    }

    for franchise, ids in EPLUS_ARTIST_IDS.items():
        for aid in ids:
            url = f"{EPLUS_BASE}{aid}"
            try:
                resp = http_get(url)
                html = resp.text
            except Exception as exc:
                print(
                    f"  ⚠ eplus {franchise} ({aid}) 请求失败: {exc}",
                    file=sys.stderr,
                )
                continue

            # 提取 JSON-LD
            ld_pattern = re.compile(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                re.DOTALL,
            )
            for ld_match in ld_pattern.finditer(html):
                try:
                    import json
                    data = json.loads(ld_match.group(1))
                except json.JSONDecodeError:
                    continue

                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") not in (
                        "Event", "MusicEvent", "Festival",
                    ):
                        continue

                    start_date = item.get("startDate", "")
                    d = parse_jp_date(start_date)
                    if d is None:
                        continue
                    if d < today or d > today + timedelta(days=400):
                        continue

                    venue_raw = ""
                    loc = item.get("location", {})
                    if isinstance(loc, dict):
                        venue_raw = loc.get("name", "")
                    elif isinstance(loc, str):
                        venue_raw = loc

                    ev = {
                        "franchise": franchise,
                        "series": franchise,
                        "title": strip_html(item.get("name", "?")),
                        "date": d.isoformat(),
                        "weekday": "月火水木金土日"[d.weekday()],
                        "venue": map_venue(venue_raw),
                        "venue_raw": venue_raw,
                        "artists": [],
                        "category": "フェス" if item.get("@type") == "Festival" else "ライブ",
                        "countdown_days": countdown_days(d),
                        "detail_link": item.get("url", url),
                        "source": "eplus.jp",
                    }
                    # 过滤非 live 活动
                    if not is_non_live_keyword(ev["title"]):
                        events.append(ev)

    return events


def scrape_all() -> list[dict]:
    """主入口：先试官方站，再 eplus 兜底，合并去重。"""
    all_events: list[dict] = []

    # 1. 官方站
    offi_events = _try_official_site()
    print(
        f"[imas] 官方站解析出 {len(offi_events)} 条",
        file=sys.stderr,
    )
    all_events.extend(offi_events)

    # 2. eplus 兜底
    eplus_events = _eplus_jsonld_scrape()
    imas_eplus = [e for e in eplus_events if "マスター" in e["franchise"]]
    print(
        f"[imas] eplus 解析出 {len(imas_eplus)} 条",
        file=sys.stderr,
    )
    all_events.extend(imas_eplus)

    # 3. eplus 中 BanG Dream & LoveLive 的结果单独存储
    # （用于 cross-reference，如果主爬虫漏了事件）
    bd_eplus = [e for e in eplus_events if "BanG" in e["franchise"]]
    ll_eplus = [e for e in eplus_events if "Love" in e["franchise"]]
    print(
        f"[imas] eplus 额外: Bandori {len(bd_eplus)} / LoveLive {len(ll_eplus)}",
        file=sys.stderr,
    )

    # 去重
    seen = set()
    deduped = []
    for e in all_events:
        key = (e["date"], e.get("title", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    deduped.sort(key=lambda e: e["date"])
    print(f"[imas] 合计 {len(deduped)} 条", file=sys.stderr)
    return deduped


# ── CLI ─────────────────────────────────────────────────────
if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)

    events = scrape_all()
    out_path = out_dir / "idolmaster.json"
    save_events(events, str(out_path))
    print(f"✅ 已写入 {out_path} ({len(events)} 条)", file=sys.stderr)
