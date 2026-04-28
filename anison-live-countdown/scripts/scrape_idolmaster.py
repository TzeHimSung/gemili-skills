"""
偶像大师系列爬虫 + eplus 购票站兜底
来源：idolmaster-official.jp + eplus.jp
输出：JSON 事件列表
"""

import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from common import (
    http_get, strip_html, parse_jp_date,
    countdown_days, map_venue, save_events,
    is_non_live_keyword, USER_AGENT, NO_PROXY,
)

# ── 偶像大师官方站 ──────────────────────────────────────────
# /live_event/ 页面本体是 Next.js shell，但前端会调用公开 CMS API：
#   cmsbase/Token/get → idolmaster/Article/list
# 不能只解析 HTML shell，否则会稳定得到 0 条。

IMAS_CMS_BASE = "https://cmsapi-frontend.idolmaster-official.jp/sitern/api/"
IMAS_OFFICIAL_LIVE_URL = "https://idolmaster-official.jp/live_event/"
IMAS_CMS_PAGE_SIZE = 200
IMAS_CMS_MAX_PAGES = 10

# ── eplus JSON-LD 配置 ──────────────────────────────────────

EPLUS_ARTIST_IDS = {
    "LoveLive!": ["0000150880"],
    "BanG Dream!": ["0000084669", "0000159108"],
    "アイドルマスター": ["0000031068", "0000126198"],
}

EPLUS_BASE = "https://eplus.jp/sf/word/"


def _extract_official_dates(date_text: str) -> list[date]:
    """Extract all dates from official CMS event_dspdate text.

    The official site uses compact multi-day strings such as:
    - 2027年1月23(土)・24(日)
    - 2026年9月22日(火・祝)・23日(水・祝)

    Splitting on "・" is unsafe because the separator also appears inside
    weekday/holiday parentheses, so scan from each full date and then parse
    short dates from the following tail.
    """
    text = date_text.replace("（", "(").replace("）", ")")
    full_re = re.compile(
        r"(?P<y>\d{4})\s*年\s*(?P<m>\d{1,2})\s*月\s*"
        r"(?P<d>\d{1,2})\s*日?"
    )
    matches = list(full_re.finditer(text))
    result: list[date] = []
    seen: set[date] = set()

    for i, match in enumerate(matches):
        year = int(match["y"])
        month = int(match["m"])
        try:
            first = date(year, month, int(match["d"]))
        except ValueError:
            continue
        if first not in seen:
            result.append(first)
            seen.add(first)

        tail_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        tail = text[match.end():tail_end]
        # 24(日) has no 日 marker. Turn it into 24日 before removing weekday text.
        tail = re.sub(r"(\d{1,2})\s*\(", r"\1日(", tail)
        tail = re.sub(r"\([^)]*\)", "", tail)
        short_re = re.compile(
            r"(?:^|[・、,／/〜~–—\-\s])"
            r"(?:(?P<m>\d{1,2})\s*月\s*)?"
            r"(?P<d>\d{1,2})\s*日"
        )
        for sm in short_re.finditer(tail):
            try:
                d = date(year, int(sm["m"] or month), int(sm["d"]))
            except ValueError:
                continue
            if d not in seen:
                result.append(d)
                seen.add(d)

    return result


def _series_from_brands(brands: list[dict]) -> str:
    """Map official CMS brand objects to the report's series label."""
    if not brands:
        return "アイドルマスター"
    code = str(brands[0].get("code", "")).upper()
    name = str(brands[0].get("name", ""))
    if code == "GAKUEN" or "学園" in name:
        return "学園アイマス"
    if code == "SIDEM" or "SideM" in name:
        return "SideM"
    if code in {"MILLION", "MILLIONLIVE", "ML"} or "MILLION" in name or "ミリオン" in name:
        return "MILLION LIVE!"
    if code in {"CINDERELLA", "CG"} or "シンデレラ" in name:
        return "シンデレラガールズ"
    if code in {"SHINYCOLORS", "SHINY", "SC"} or "シャイニー" in name:
        return "シャイニーカラーズ"
    if code in {"765", "765AS"} or "765" in name:
        return "765AS"
    return name or "アイドルマスター"


def _clean_venue_raw(raw: str) -> str:
    """Keep the actual venue line and drop official notes such as ※詳細は後日."""
    return _venue_line_from_block(raw)


def _venue_line_from_block(raw: str) -> str:
    """Choose the venue-looking line from an official CMS venue block."""
    lines: list[str] = []
    for line in raw.replace("\r", "\n").split("\n"):
        line = strip_html(line)
        if line and not line.startswith("※"):
            lines.append(line)
    if not lines:
        return "未定"

    venue_keywords = [
        "アリーナ", "ホール", "メッセ", "会館", "ドーム", "劇場",
        "体育館", "パーク", "シアター", "ギャラリー", "BEAM",
        "Arena", "HALL", "Hall", "Zepp",
    ]
    for line in lines:
        if any(keyword in line for keyword in venue_keywords):
            return line
    return lines[0]


def _venue_for_official_date(article: dict, event_date: date) -> str:
    """Match an event date to its venue block when CMS has multiple sections."""
    date_blocks = [
        b.strip() for b in re.split(r"\n\s*\n", article.get("event_dspdate", ""))
        if b.strip()
    ]
    venue_blocks = [
        b.strip() for b in re.split(r"\n\s*\n", article.get("event_place", ""))
        if b.strip()
    ]
    if len(date_blocks) > 1 and len(date_blocks) == len(venue_blocks):
        for date_block, venue_block in zip(date_blocks, venue_blocks):
            if event_date in _extract_official_dates(date_block):
                return _venue_line_from_block(venue_block)
    return _clean_venue_raw(article.get("event_place", ""))


def _official_detail_link(article: dict) -> str:
    if article.get("event_url"):
        return article["event_url"]
    if article.get("article_type") == "detail_page" and article.get("url_name"):
        return f"https://idolmaster-official.jp/live_events/{article['url_name']}"
    return IMAS_OFFICIAL_LIVE_URL


def _parse_official_article(
    article: dict,
    today: date | None = None,
    max_days: int = 400,
) -> list[dict]:
    """Convert one official CMS article into one event per event date."""
    base_day = today or date.today()
    title = strip_html(article.get("title", "?"))
    if not title or is_non_live_keyword(title):
        return []

    event_dates = _extract_official_dates(article.get("event_dspdate", ""))
    brands = article.get("brand") or []
    series = _series_from_brands(brands)
    artists = [b.get("name", "") for b in brands if b.get("name")]
    detail_link = _official_detail_link(article)

    events: list[dict] = []
    for d in event_dates:
        if d < base_day or d > base_day + timedelta(days=max_days):
            continue
        venue_raw = _venue_for_official_date(article, d)
        events.append({
            "franchise": "アイドルマスター",
            "series": series,
            "title": title,
            "date": d.isoformat(),
            "weekday": "月火水木金土日"[d.weekday()],
            "venue": map_venue(venue_raw),
            "venue_raw": venue_raw,
            "artists": artists,
            "category": "フェス" if re.search(r"FES|フェス|合同", title, re.I) else "ライブ",
            "countdown_days": countdown_days(d),
            "detail_link": detail_link,
            "source": "idolmaster-official.jp",
        })
    return events


def _build_official_cms_request(
    token: str,
    today: date | None = None,
    max_days: int = 400,
    start: int = 0,
    limit: int = IMAS_CMS_PAGE_SIZE,
) -> tuple[str, dict]:
    """Build the same CMS Article/list request used by the Next.js frontend."""
    base_day = today or date.today()
    payload = {
        "category": ["LIVE-EVENT"],
        "brand": [],
        "subcategory": [],
        "article_type": ["url_link", "detail_page"],
        "target_start_date": base_day.isoformat(),
        "target_end_date": (base_day + timedelta(days=max_days)).isoformat(),
    }
    return (
        f"{IMAS_CMS_BASE}idolmaster/Article/list",
        {
            "site": "jp",
            "ip": "idolmaster",
            "token": token,
            "sort": "asc",
            "limit": limit,
            "start": start,
            "data": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    )


def _cms_get_json(url: str, params: dict | None = None, retries: int = 2) -> dict:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "ja-JP,ja;q=0.9",
                    "Referer": IMAS_OFFICIAL_LIVE_URL,
                },
                timeout=20,
                proxies=NO_PROXY,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("statusCode") != 200:
                raise RuntimeError(f"CMS returned statusCode={data.get('statusCode')}")
            return data
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(1.5 * (attempt + 1))
    raise last_exc or RuntimeError("CMS request failed")


def _official_cms_scrape(today: date | None = None) -> list[dict]:
    """Scrape the official public CMS API behind /live_event/."""
    token_data = _cms_get_json(f"{IMAS_CMS_BASE}cmsbase/Token/get")
    token = token_data.get("data", {}).get("token")
    if not token:
        raise RuntimeError("CMS token missing")

    events: list[dict] = []
    base_day = today or date.today()
    start = 0
    for _page in range(IMAS_CMS_MAX_PAGES):
        endpoint, params = _build_official_cms_request(
            token,
            today=base_day,
            start=start,
            limit=IMAS_CMS_PAGE_SIZE,
        )
        list_data = _cms_get_json(endpoint, params=params)
        articles = list_data.get("data", {}).get("article_list") or []
        for article in articles:
            events.extend(_parse_official_article(article, today=base_day))
        if len(articles) < IMAS_CMS_PAGE_SIZE:
            return events
        start += IMAS_CMS_PAGE_SIZE
    raise RuntimeError("official CMS pagination did not finish before safety limit")


def _try_official_site() -> list[dict]:
    """从官方 CMS API 抓取；失败时返回空列表让 eplus 兜底。"""
    try:
        return _official_cms_scrape()
    except Exception as exc:
        print(f"  ⚠ 官方 CMS 异常: {exc}", file=sys.stderr)
        return []


def _eplus_jsonld_scrape(franchises: list[str] | None = None) -> list[dict]:
    """
    从 eplus 的 JSON-LD 中提取事件。
    对指定企划的 artist IDs 发起请求，解析 Event schema。
    """
    events: list[dict] = []
    today = date.today()
    target_ids = EPLUS_ARTIST_IDS if franchises is None else {
        name: EPLUS_ARTIST_IDS[name]
        for name in franchises
        if name in EPLUS_ARTIST_IDS
    }

    for franchise, ids in target_ids.items():
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

    # 2. eplus 兜底：这里只补偶像大师，避免重复抓取 Bandori/LoveLive。
    eplus_events = _eplus_jsonld_scrape(franchises=["アイドルマスター"])
    imas_eplus = [e for e in eplus_events if "マスター" in e["franchise"]]
    print(
        f"[imas] eplus 解析出 {len(imas_eplus)} 条",
        file=sys.stderr,
    )
    all_events.extend(imas_eplus)

    # 3. 去重
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
