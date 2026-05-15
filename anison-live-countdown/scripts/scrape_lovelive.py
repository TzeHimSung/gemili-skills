"""
LoveLive! 系列官方站爬虫
覆盖：蓮ノ空 / Liella! / 虹ヶ咲 / Aqours / μ's / スクフェス
来源：各シリーズ公式サイト
输出：JSON 事件列表
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

from common import (
    http_get, strip_html, parse_jp_date,
    countdown_days, map_venue, save_events,
    split_tour_dates, jst_today,
)

# ── 各シリーズ URL 配置 ──────────────────────────────────────

SERIES_CONFIG: list[dict] = [
    {
        "name": "蓮ノ空女学院",
        "url": "https://www.lovelive-anime.jp/hasunosora/live-event/",
        "referer": "https://www.lovelive-anime.jp/hasunosora/",
        "artist": "蓮ノ空女学院スクールアイドルクラブ",
    },
    {
        "name": "Liella!",
        "url": "https://www.lovelive-anime.jp/yuigaoka/live/",
        "referer": "https://www.lovelive-anime.jp/yuigaoka/",
        "artist": "Liella!",
    },
    {
        "name": "虹ヶ咲学園",
        "url": "https://www.lovelive-anime.jp/nijigasaki/live-event/",
        "referer": "https://www.lovelive-anime.jp/nijigasaki/",
        "artist": "虹ヶ咲学園スクールアイドル同好会",
    },
    {
        "name": "Aqours",
        "url": "https://www.lovelive-anime.jp/uranohoshi/live/",
        "referer": "https://www.lovelive-anime.jp/uranohoshi/",
        "artist": "Aqours",
    },
    {
        "name": "μ's",
        "url": "https://www.lovelive-anime.jp/news/",
        "referer": "https://www.lovelive-anime.jp/",
        "artist": "μ's",
    },
]


def official_source_urls() -> list[dict[str, str]]:
    """Return the enabled official LoveLive source URL contract."""
    return [
        {
            "franchise": "LoveLive!",
            "name": str(cfg["name"]).strip(),
            "url": str(cfg["url"]).strip(),
            "referer": str(cfg["referer"]).strip(),
        }
        for cfg in SERIES_CONFIG
    ]

# 已知 LoveLive 场地
KNOWN_VENUES_LL: dict[str, str] = {
    "Kアリーナ横浜": "K Arena 横浜",
    "ぴあアリーナMM": "Pia Arena MM (横浜)",
    "有明アリーナ": "Ariake Arena",
    "東京ドーム": "東京ドーム",
    "さいたまスーパーアリーナ": "さいたまスーパーアリーナ",
    "横浜アリーナ": "横浜アリーナ",
    "日本武道館": "日本武道館",
    "代々木第一体育館": "代々木第一体育館",
    "大阪城ホール": "大阪城ホール",
    "マリンメッセ福岡": "Marine Messe 福岡",
    "ポートメッセなごや": "Port Messe 名古屋",
    "セキスイハイムスーパー": "Sekisui Heim Super Arena",
    "西武ドーム": "西武ドーム (ベルーナドーム)",
    "メットライフドーム": "ベルーナドーム",
    "ベルーナドーム": "ベルーナドーム",
    "幕張メッセ": "幕張メッセ",
    "Zepp": None,  # 子串匹配，用 common VENUE_MAP
    "SGC HALL": None,  # 同上
}


def _parse_hasunosora_page(
    html: str,
    series_name: str,
    base_url: str,
    today: date,
) -> list[dict]:
    """
    蓮ノ空专用解析器。
    页面结构：<li> 内含 live_title / live_date / live_place 等精确字段。
    支持 ＜Stage／Date＞ 多阶段格式。
    """
    events: list[dict] = []

    # 提取所有 <li> 块（在 list__inner 内）
    list_match = re.search(
        r'<div[^>]*class="[^"]*list__inner[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</section>',
        html, re.DOTALL,
    )
    if not list_match:
        return events

    list_html = list_match.group(1)
    li_blocks = re.findall(r'<li>(.*?)</li>', list_html, re.DOTALL)

    for li in li_blocks:
        # 标题
        title_m = re.search(
            r'class="live_title"[^>]*>\s*<p>(.*?)</p>',
            li, re.DOTALL,
        )
        if not title_m:
            continue
        title = strip_html(title_m.group(1))
        # 缩短标题：去掉重复的系列前缀
        short_title = re.sub(
            r'^ラブライブ！蓮ノ空女学院スクールアイドルクラブ\s*',
            '',
            title,
        )

        # 分类标签 (シリーズ横断 等)
        ico_m = re.search(
            r'class="live_ico"[^>]*>.*?<span[^>]*>(.*?)</span>',
            li, re.DOTALL,
        )
        category_tag = strip_html(ico_m.group(1)) if ico_m else ""

        # 日期
        date_m = re.search(
            r'class="live_date"[^>]*>\s*<span>(.*?)</span>',
            li, re.DOTALL,
        )
        if not date_m:
            continue
        date_raw = date_m.group(1)

        # 场地
        venue_m = re.search(
            r'class="live_place"[^>]*>\s*<span>(.*?)</span>',
            li, re.DOTALL,
        )
        venue_raw = strip_html(venue_m.group(1)) if venue_m else ""

        # 链接
        link_m = re.search(r'<a\b[^>]*\bhref=["\']([^"\']+)', li)
        detail_link = urljoin(base_url, link_m.group(1)) if link_m else base_url

        # ── 解析日期 ──
        date_stripped = strip_html(date_raw)
        # 清理格式前缀：去掉 【日程】 等标记，合并换行
        date_stripped = re.sub(r'【[^】]+】\s*', '', date_stripped)
        date_stripped = re.sub(r'\s+', ' ', date_stripped).strip()
        
        # 清理场地
        venue_raw_clean = strip_html(venue_raw) if venue_raw else ""
        venue_raw_clean = re.sub(r'【[^】]+】\s*', '', venue_raw_clean)
        venue_raw_clean = re.sub(r'\s+', ' ', venue_raw_clean).strip()

        # 格式 A：＜Stage／Date＞ 多阶段
        stage_blocks = re.findall(
            r'＜([^／]+)／([^＞>\n]+)[＞>]?',
            date_stripped,
        )

        if stage_blocks:
            # 解析对应场地块
            venue_stage_blocks = re.findall(
                r'＜([^／]+)／([^＞>\n]+)[＞>]?',
                venue_raw,
            ) if venue_raw else []
            # 建 stage → venue 映射
            venue_map: dict[str, str] = {}
            for sn, sv in venue_stage_blocks:
                venue_map[sn.strip()] = sv.strip()

            for stage_name, stage_date_text in stage_blocks:
                stage_name = stage_name.strip()
                stage_date_text = stage_date_text.strip()

                # 拆分多日（如 "2026年5月2日(土)・3日(日)"）
                date_parts = [d.strip() for d in stage_date_text.split("・")]
                first_date = parse_jp_date(date_parts[0])
                if first_date is None:
                    continue
                if first_date < today or first_date > today + timedelta(days=400):
                    continue

                year = first_date.year
                month = first_date.month
                for dp in date_parts:
                    d = parse_jp_date(dp)
                    if d is None and year:
                        d = parse_jp_date(f"{year}年{month}月{dp}")
                    if d is None:
                        continue
                    if d < today or d > today + timedelta(days=400):
                        continue

                    stage_venue = venue_map.get(stage_name, "未定")
                    full_title = f"{short_title} {stage_name}"

                    ev = {
                        "franchise": "LoveLive!",
                        "series": series_name,
                        "title": full_title,
                        "date": d.isoformat(),
                        "weekday": "月火水木金土日"[d.weekday()],
                        "venue": map_venue(stage_venue),
                        "venue_raw": stage_venue,
                        "artists": ["蓮ノ空女学院スクールアイドルクラブ"],
                        "category": "フェス" if "フェス" in (title + category_tag) else "ライブ",
                        "countdown_days": countdown_days(d, today=today),
                        "detail_link": detail_link,
                        "source": base_url,
                    }
                    if not _is_duplicate(ev, events):
                        events.append(ev)
        else:
            # 格式 B：简单日期 "2026年11月14日(土)・15日(日)"
            d = parse_jp_date(date_stripped)
            if d is None:
                continue
            if d < today or d > today + timedelta(days=400):
                continue

            # 尝试拆分多日
            if "・" in date_stripped:
                tours = split_tour_dates(date_stripped, venue_raw_clean or "")
                if tours:
                    for full_date_str, venue_str in tours:
                        d2 = parse_jp_date(full_date_str)
                        if d2 and d2 >= today and d2 <= today + timedelta(days=400):
                            ev = {
                                "franchise": "LoveLive!",
                                "series": series_name,
                                "title": short_title,
                                "date": d2.isoformat(),
                                "weekday": "月火水木金土日"[d2.weekday()],
                                "venue": map_venue(venue_str),
                                "venue_raw": venue_str,
                                "artists": ["蓮ノ空女学院スクールアイドルクラブ"],
                                "category": "フェス" if "フェス" in (short_title + category_tag) else "ライブ",
                                "countdown_days": countdown_days(d2, today=today),
                                "detail_link": detail_link,
                                "source": base_url,
                            }
                            if not _is_duplicate(ev, events):
                                events.append(ev)
                else:
                    # 拆分失败，用单日
                    ev = _make_single_hasu_event(
                        short_title, d, venue_raw_clean, series_name, base_url,
                        detail_link, category_tag, today=today,
                    )
                    if not _is_duplicate(ev, events):
                        events.append(ev)
            else:
                ev = _make_single_hasu_event(
                    short_title, d, venue_raw_clean, series_name, base_url,
                    detail_link, category_tag, today=today,
                )
                if not _is_duplicate(ev, events):
                    events.append(ev)

    # 过滤垃圾标题
    events = [e for e in events if not _is_garbage_title(e["title"])]
    return events


def _make_single_hasu_event(
    title: str,
    d: date,
    venue_raw: str,
    series_name: str,
    base_url: str,
    detail_link: str,
    category_tag: str = "",
    today: date | None = None,
) -> dict:
    return {
        "franchise": "LoveLive!",
        "series": series_name,
        "title": title,
        "date": d.isoformat(),
        "weekday": "月火水木金土日"[d.weekday()],
        "venue": map_venue(venue_raw),
        "venue_raw": venue_raw,
        "artists": ["蓮ノ空女学院スクールアイドルクラブ"],
        "category": "フェス" if "フェス" in (title + category_tag) else "ライブ",
        "countdown_days": countdown_days(d, today=today),
        "detail_link": detail_link,
        "source": base_url,
    }


def _parse_live_list_page(
    html: str,
    series_name: str,
    base_url: str,
    today: date,
) -> list[dict]:
    """解析 Liella!/Aqours 等 live/ 列表页面（live_info schedule 结构）。"""
    events: list[dict] = []
    artist = _series_artist(series_name)

    # 找到所有 <li> 包含 schedule 的块
    li_blocks = re.findall(r"<li>(.*?)</li>", html, re.DOTALL)
    for li in li_blocks:
        if "schedule" not in li:
            continue

        # ── 提取标题 ──
        title = ""
        # 策略1: live_title 类（Liella!）
        title_m = re.search(
            r'class="live_title"[^>]*>\s*<p>(.*?)</p>',
            li, re.DOTALL,
        )
        if title_m:
            title = strip_html(title_m.group(1))
        else:
            # 策略2: h3/h4（Aqours）
            for tag in ("h3", "h4"):
                m = re.search(
                    rf"<{tag}[^>]*>(.*?)</{tag}>",
                    li, re.DOTALL,
                )
                if m:
                    title = strip_html(m.group(1))
                    break
        if not title:
            # 策略3: alt 属性
            alt_m = re.search(r'alt="([^"]+)"', li)
            if alt_m:
                title = alt_m.group(1)
        if not title or len(title) < 4:
            continue

        # ── 提取 schedule ──
        sched_m = re.search(
            r'class="[^"]*schedule[^"]*"[^>]*>(.*?)</div>',
            li, re.DOTALL,
        )
        if not sched_m:
            continue
        schedule_raw = strip_html(sched_m.group(1))
        # 去掉 "開催日時" 前缀
        schedule_raw = re.sub(r"開催日時\s*", "", schedule_raw).strip()

        # ── 提取链接 ──
        link_m = re.search(r'href=["\']([^"\']+)', li)
        detail_link = urljoin(base_url, link_m.group(1)) if link_m else base_url

        # ── 提取场地（如果有） ──
        venue_raw = ""
        venue_m = re.search(
            r'class="[^"]*place[^"]*"[^>]*>(.*?)</div>',
            li, re.DOTALL,
        )
        if venue_m:
            venue_raw = strip_html(venue_m.group(1))

        # ── 解析日期 ──
        # 清理前缀: ① ② | 等
        date_clean = re.sub(r"[①②③④⑤]\s*", "", schedule_raw)
        date_clean = re.sub(r"\|\s*", "・", date_clean)  # ｜ → ・
        date_clean = re.sub(r"\s*-\s*", "・", date_clean)  # - → ・
        date_clean = date_clean.strip()

        # 提取首段的年月，用于补全后续简写日期
        first_full = re.search(
            r"(\d{4})年(\d{1,2})月", schedule_raw
        )
        ref_year = int(first_full.group(1)) if first_full else None
        ref_month = int(first_full.group(2)) if first_full else None

        # 拆分为独立日期段（用 ・ 或 、 分隔）
        segments = [s.strip() for s in re.split(r"[・、]", date_clean) if s.strip()]

        for seg in segments:
            d = parse_jp_date(seg)
            if d is None and ref_year is not None:
                # 尝试补齐年月
                d = parse_jp_date(f"{ref_year}年{ref_month}月{seg}")
            if d is None and ref_year:
                # 再试只补年
                d = parse_jp_date(f"{ref_year}年{seg}")
            if d is None:
                continue
            if d < today or d > today + timedelta(days=400):
                continue

            ven = map_venue(venue_raw) if venue_raw else "未定"
            # 缩短标题（去系列前缀）
            short_title = title
            for prefix in [
                "ラブライブ！スーパースター!! ",
                "ラブライブ！サンシャイン!! ",
                "ラブライブ！虹ヶ咲学園スクールアイドル同好会 ",
            ]:
                if short_title.startswith(prefix):
                    short_title = short_title[len(prefix):]
                    break

            ev = {
                "franchise": "LoveLive!",
                "series": series_name,
                "title": short_title[:60],
                "date": d.isoformat(),
                "weekday": "月火水木金土日"[d.weekday()],
                "venue": ven,
                "venue_raw": venue_raw,
                "artists": [artist],
                "category": "ライブ",
                "countdown_days": countdown_days(d, today=today),
                "detail_link": detail_link,
                "source": base_url,
            }
            if not _is_duplicate(ev, events):
                events.append(ev)

    return events


def _extract_events_from_html(
    html: str,
    series_name: str,
    base_url: str,
) -> list[dict]:
    """
    从 LoveLive 系列页面 HTML 中提取事件。
    策略：搜索日期模式 + 上下文中的标题/场地。
    """
    events: list[dict] = []
    today = jst_today()

    # ── 策略 0：蓮ノ空专用解析器 ──
    if "hasunosora" in html or "live_title" in html:
        if "list__inner" in html:
            # 蓮ノ空格式：list__inner + live_title/live_date/live_place
            hasu_events = _parse_hasunosora_page(html, series_name, base_url, today)
            if hasu_events:
                events.extend(hasu_events)
                if len(hasu_events) >= 2:
                    return [
                        e
                        for e in hasu_events
                        if not _is_garbage_title(e.get("title", ""))
                    ]
        elif "live_info" in html and "schedule" in html:
            # Liella!/Aqours 格式：live_info schedule 在 <li> 内
            list_events = _parse_live_list_page(
                html, series_name, base_url, today
            )
            if list_events:
                events.extend(list_events)
                # 继续尝试其他策略以获取更多事件

    # ── 策略 1：结构化 JSON-LD（如果有） ──
    ld_pattern = re.compile(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        re.DOTALL,
    )
    for ld_match in ld_pattern.finditer(html):
        try:
            import json
            data = json.loads(ld_match.group(1))
            if isinstance(data, list):
                for item in data:
                    _parse_jsonld_event(item, events, series_name, base_url, today)
            else:
                _parse_jsonld_event(data, events, series_name, base_url, today)
        except (json.JSONDecodeError, KeyError):
            continue

    # ── 策略 2：结构化 HTML 块（live-event 卡片） ──
    # LoveLive 各站常见模式：<section> / <li> / <div> 包含日期+标题
    card_patterns = [
        r'<li[^>]*>(.*?)</li>',
        r'<div[^>]*class="[^"]*event[^"]*"[^>]*>(.*?)</div>',
        r'<section[^>]*>(.*?)</section>',
        r'<article[^>]*>(.*?)</article>',
    ]
    for pattern in card_patterns:
        for card in re.finditer(pattern, html, re.DOTALL):
            card_html = card.group(1)
            ev = _parse_ll_card(card_html, series_name, base_url, today)
            if ev and not _is_duplicate(ev, events):
                events.append(ev)

    # ── 策略 3：裸日期扫描（兜底） ──
    if not events:
        date_matches = list(re.finditer(
            r'(?P<y>\d{4})[年/.\-](?P<m>\d{1,2})[月/.\-](?P<d>\d{1,2})日?',
            html,
        ))
        for dm in date_matches:
            try:
                d = date(int(dm["y"]), int(dm["m"]), int(dm["d"]))
            except ValueError:
                continue
            if d < today or d > today + timedelta(days=400):
                continue
            # 取日期前后 200 字符作为上下文
            ctx_start = max(0, dm.start() - 200)
            ctx_end = min(len(html), dm.end() + 200)
            context = strip_html(html[ctx_start:ctx_end])
            # 尝试从上下文中提取标题
            title = _guess_title_from_context(context)
            ev = {
                "franchise": "LoveLive!",
                "series": series_name,
                "title": title,
                "date": d.isoformat(),
                "weekday": "月火水木金土日"[d.weekday()],
                "venue": "未定",
                "venue_raw": "",
                "artists": [_series_artist(series_name)],
                "category": "ライブ",
                "countdown_days": countdown_days(d, today=today),
                "detail_link": base_url,
                "source": base_url,
            }
            if not _is_duplicate(ev, events):
                events.append(ev)

    # ── 垃圾过滤 ──
    events = [e for e in events if not _is_garbage_title(e.get("title", ""))]

    return events


def _parse_jsonld_event(
    item: dict,
    events: list[dict],
    series_name: str,
    base_url: str,
    today: date,
) -> None:
    """解析 JSON-LD Event 对象。"""
    if item.get("@type") not in ("Event", "MusicEvent", "Festival"):
        return

    start_date_str = item.get("startDate", "")
    d = parse_jp_date(start_date_str) if start_date_str else None
    if d is None:
        return
    if d < today or d > today + timedelta(days=400):
        return

    venue_raw = ""
    locale = item.get("location", {})
    if isinstance(locale, dict):
        venue_raw = locale.get("name", "")
    elif isinstance(locale, str):
        venue_raw = locale

    ev = {
        "franchise": "LoveLive!",
        "series": series_name,
        "title": strip_html(item.get("name", "?")),
        "date": d.isoformat(),
        "weekday": "月火水木金土日"[d.weekday()],
        "venue": map_venue(venue_raw) or _map_ll_venue(venue_raw),
        "venue_raw": venue_raw,
        "artists": [item.get("performer", {}).get("name", "")
                     if isinstance(item.get("performer"), dict)
                     else _series_artist(series_name)],
        "category": "フェス" if item.get("@type") == "Festival" else "ライブ",
        "countdown_days": countdown_days(d, today=today),
        "detail_link": item.get("url", base_url),
        "source": base_url,
    }
    if not _is_duplicate(ev, events):
        events.append(ev)


def _parse_ll_card(
    card_html: str,
    series_name: str,
    base_url: str,
    today: date,
) -> dict | None:
    """解析 LoveLive 风格的事件卡片 HTML。"""
    full_text = strip_html(card_html)

    d = parse_jp_date(full_text)
    if d is None:
        return None
    if d < today or d > today + timedelta(days=400):
        return None

    # 标题：取日期之前的内容，或卡片内最大文本块
    title = _guess_title_from_card(card_html, d)

    # 场地：搜索已知场地关键词
    venue = "未定"
    venue_raw = ""
    for kw in KNOWN_VENUES_LL:
        if kw in full_text:
            venue_raw = kw
            mapped = KNOWN_VENUES_LL[kw]
            venue = mapped if mapped else map_venue(kw)
            break

    return {
        "franchise": "LoveLive!",
        "series": series_name,
        "title": title,
        "date": d.isoformat(),
        "weekday": "月火水木金土日"[d.weekday()],
        "venue": venue,
        "venue_raw": venue_raw,
        "artists": [_series_artist(series_name)],
        "category": "ライブ",
        "countdown_days": countdown_days(d, today=today),
        "detail_link": base_url,
        "source": base_url,
    }


def _is_garbage_title(title: str) -> bool:
    """检查标题是否是 JS 代码、HTML 残留或其他垃圾。"""
    # 已知垃圾字符串
    known_garbage = [
        "タイトル未確認",
        "お探しの記事は見つかりませんでした",
        "お探しのページは見つかりませんでした",
        "404",
        "Not Found",
        "ページが見つかりません",
    ]
    for kg in known_garbage:
        if kg in title:
            return True

    garbage_patterns = [
        r"^\(function\(",       # JS 函数
        r"^\{",                 # JSON 对象
        r"^\s*window\.",        # JS window
        r"^\s*document\.",      # JS document
        r"^\s*var\s",           # JS 变量
        r"^\s*<[a-zA-Z]",       # HTML 标签残留
        r"^\s*css\s*[\(\{]",    # CSS
        r"^\s*@(media|import|keyframes)",  # CSS at-rules
        r"^\s*#\w+\s*\{",       # CSS 选择器
        r"^LIVE&nbsp;",         # HTML 实体残留
        r"^\s*/\*",             # CSS 注释
        r"^LIVE\s*&\s*EVENT",   # 页面导航标题
        r"^ライブ・イベント",    # 日语页面导航
        r"^シリーズ横断",        # 日语页面导航
        r"gtm\.",               # GTM 代码残留
        r"new Date\(\)",         # JS 代码残留
    ]
    for pat in garbage_patterns:
        if re.search(pat, title):
            return True
    # 纯标点/空白
    if re.match(r"^[\s\.,;:!?\-_/\\|@#$%^&*()\[\]{}'\"<>]+$", title):
        return True
    # 长度过短
    if len(title) < 4:
        return True
    return False


def _series_artist(series_name: str) -> str:
    """根据系列名返回默认艺人名。"""
    mapping = {
        "蓮ノ空女学院": "蓮ノ空女学院スクールアイドルクラブ",
        "Liella!": "Liella!",
        "虹ヶ咲学園": "虹ヶ咲学園スクールアイドル同好会",
        "Aqours": "Aqours",
        "μ's": "μ's",
    }
    return mapping.get(series_name, series_name)


def _guess_title_from_context(context: str) -> str:
    """从日期周围文本猜测活动标题。"""
    # 简单策略：取第一行非日期文本
    lines = context.split("\n")
    for line in lines:
        line = line.strip()
        if line and not re.search(r"\d{4}[年/.\-]\d{1,2}[月/.\-]\d{1,2}", line):
            if len(line) > 3:
                return line[:50]
    return "タイトル未確認"


def _guess_title_from_card(card_html: str, event_date: date) -> str:
    """从卡片 HTML 中推测标题。"""
    # 优先取 h3/h4/strong 中的文本
    for tag in ("h3", "h4", "strong", "p"):
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", card_html, re.DOTALL)
        if m:
            text = strip_html(m.group(1))
            # 排除纯日期文本
            if not re.match(r"^\d{4}[年/.\-]", text) and len(text) > 3:
                return text[:60]

    # 兜底：取 strip 后的第一行非空内容
    text = strip_html(card_html)
    lines = [l for l in text.split("\n") if l.strip() and len(l.strip()) > 3]
    for line in lines:
        if not re.match(r"^\d{4}[年/.\-]", line):
            return line[:60]
    return "タイトル未確認"


def _map_ll_venue(raw: str) -> str:
    """LoveLive 专用场地映射（先查本地再 fallback 通用）。"""
    for kw, display in KNOWN_VENUES_LL.items():
        if kw in raw:
            if display:
                return display
            return map_venue(raw)
    return map_venue(raw)


def _is_duplicate(ev: dict, existing: list[dict]) -> bool:
    """检查是否与已有事件重复（同日期+同系列+标题相似）。"""
    title = ev.get("title", "")
    for e in existing:
        if e["date"] != ev["date"] or e["series"] != ev["series"]:
            continue
        e_title = e.get("title", "")
        # 精确匹配
        if e_title == title:
            return True
        # 一个标题包含另一个（去前缀/全称差异）
        if len(title) > 3 and len(e_title) > 3:
            if title in e_title or e_title in title:
                return True
    return False


def scrape_all() -> list[dict]:
    """抓取所有 LoveLive 系列，返回合并后的事件列表。"""
    all_events: list[dict] = []

    for cfg in SERIES_CONFIG:
        print(
            f"[lovelive] 抓取 {cfg['name']} ... {cfg['url']}",
            file=sys.stderr,
        )
        try:
            resp = http_get(
                cfg["url"],
                referer=cfg["referer"],
            )
            events = _extract_events_from_html(
                resp.text,
                cfg["name"],
                cfg["url"],
            )
            print(f"  → 解析出 {len(events)} 条", file=sys.stderr)
            all_events.extend(events)
        except Exception as exc:
            print(f"  ⚠ {cfg['name']} 抓取失败: {exc}", file=sys.stderr)

    # 去重 & 排序
    seen = set()
    deduped = []
    for e in all_events:
        key = (e["date"], e["series"], e["title"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    deduped.sort(key=lambda e: e["date"])
    print(
        f"[lovelive] 合计 {len(deduped)} 条事件 (去重后)",
        file=sys.stderr,
    )
    return deduped


# ── CLI ─────────────────────────────────────────────────────
if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)

    events = scrape_all()
    out_path = out_dir / "lovelive.json"
    save_events(events, str(out_path))
    print(f"✅ 已写入 {out_path} ({len(events)} 条)", file=sys.stderr)
