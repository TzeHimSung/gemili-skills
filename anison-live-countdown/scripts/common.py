"""
anison-live-countdown 公共库
共享的 HTTP 客户端（从 shared lib 导入）、日期解析、场地映射、日历 helper。
"""
import re
import html
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests

# ── 从共享库导入 HTTP 客户端 ──────────────────────────────

_SHARED = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"
sys.path.insert(0, str(_SHARED))

from stock_tracker_lib import http_get as _shared_http_get  # noqa: E402


def http_get(url: str, referer: str = "", timeout: int = 15, retries: int = 2, accept_lang: str = "ja-JP,ja;q=0.9"):
    """Anison 站点默认请求日文页面，底层复用 shared HTTP 客户端。"""
    return _shared_http_get(url, referer=referer, timeout=timeout, retries=retries, accept_lang=accept_lang)

# ── 公共常量 ──────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

NO_PROXY = {"http": None, "https": None}

# 日文曜日マッピング
WEEKDAY_JA = {
    "月": "Mon", "火": "Tue", "水": "Wed",
    "木": "Thu", "金": "Fri", "土": "Sat", "日": "Sun",
}

# 日文数字
NUM_JA = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

# 正则：日文日期
RE_DATE_JA = re.compile(
    r"(?P<y>\d{4})\s*[年/.]\s*"
    r"(?P<m>\d{1,2})\s*[月/.]\s*"
    r"(?P<d>\d{1,2})\s*日?"
)

# 正则：省略年份的日期
RE_SHORT_DATE_JA = re.compile(
    r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日"
)

# 正则：ISO date
RE_ISO_DATE = re.compile(r"(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})")


def parse_jp_date(text: str, default_year: Optional[int] = None) -> Optional[date]:
    """解析日文日期字符串，返回 date 对象。"""
    m = RE_DATE_JA.search(text)
    if m:
        return date(int(m["y"]), int(m["m"]), int(m["d"]))

    m = RE_SHORT_DATE_JA.search(text)
    if m and default_year:
        return date(default_year, int(m["m"]), int(m["d"]))

    m = RE_ISO_DATE.search(text)
    if m:
        return date(int(m["y"]), int(m["m"]), int(m["d"]))

    return None


def split_tour_dates(
    date_text: str,
    venue_text: str,
) -> list[tuple[str, str]]:
    """拆分多日巡回的日期与场地。

    官网常见写法包括 ``2026年6月18日・19日``、``2026年6月18日 / 6月26日``、
    ``2026年6月18日〜19日``，以及曜日/祝日括号中的 ``・``。先移除括号注记，
    再按真实日期分隔符切分，避免漏掉第二天或后续会场。
    """
    clean_date_text = re.sub(r"[（(][^）)]*[）)]", "", date_text)
    dates = [
        d.strip()
        for d in re.split(r"\s*(?:・|/|／|、|,|，|[〜～]|[;\r\n]+)\s*", clean_date_text)
        if d.strip()
    ]
    # 多日巡回的场地分隔在不同官网里不统一：読点、日文中点、换行、斜杠都出现过。
    venues = [v.strip() for v in re.split(r"\s*(?:、|・|[\r\n]+|/|／)\s*", venue_text) if v.strip()]

    def _venue_for(i: int) -> str:
        if len(venues) == 1 and venues[0]:
            return venues[0]
        if i < len(venues) and venues[i]:
            return venues[i]
        for v in reversed(venues[:i]):
            if v:
                return v
        return "未定"

    result: list[tuple[str, str]] = []
    year = None
    month = None

    for i, d in enumerate(dates):
        ym = RE_DATE_JA.search(d)
        if ym:
            year = ym["y"]
            month = ym["m"]
            result.append((f"{year}年{month}月{ym['d']}日", _venue_for(i)))
        elif year:
            sm = RE_SHORT_DATE_JA.search(d)
            if sm:
                month = sm["m"]
                full = f"{year}年{month}月{sm['d']}日"
                result.append((full, _venue_for(i)))
            elif month:
                dm = re.search(r"(\d{1,2})\s*日", d)
                if dm:
                    full = f"{year}年{month}月{dm.group(1)}日"
                    result.append((full, _venue_for(i)))

    return result


def countdown_days(event_date: date) -> int:
    """到 event_date 还有几天。"""
    return (event_date - date.today()).days


# ── 场地映射 ────────────────────────────────────────────────

VENUE_MAP: dict[str, str] = {
    "有明アリーナ": "Ariake Arena",
    "SGC HALL ARIAKE": "SGC Hall Ariake",
    "Zepp Namba": "Zepp Namba (大阪)",
    "Zepp Nagoya": "Zepp Nagoya (名古屋)",
    "Zepp Haneda": "Zepp Haneda (東京)",
    "Zepp Fukuoka": "Zepp Fukuoka (福岡)",
    "Zepp Sapporo": "Zepp Sapporo (札幌)",
    "Zepp DiverCity": "Zepp DiverCity (東京)",
    "Zepp Yokohama": "Zepp Yokohama",
    "Zepp Osaka Bayside": "Zepp Osaka Bayside",
    "Zepp Shinjuku": "Zepp Shinjuku (東京)",
    "神戸国際会館": "神戸国際会館",
    "ぴあアリーナMM": "Pia Arena MM (横浜)",
    "TACHIKAWA STAGE GARDEN": "立川 Stage Garden",
    "東京ドーム": "東京ドーム",
    "幕張メッセ": "幕張メッセ",
    "さいたまスーパー": "さいたまスーパーアリーナ",
    "横浜アリーナ": "横浜アリーナ",
    "日本武道館": "日本武道館",
    "代々木第一": "代々木第一体育館",
    "大阪城ホール": "大阪城ホール",
    "Kアリーナ横浜": "K Arena 横浜",
    "COOL JAPAN PARK OSAKA": "Cool Japan Park Osaka",
    "國立體育大學綜合體育館": "林口體育館 (台北)",
}


def map_venue(venue_raw: str) -> str:
    """场地名标准化。"""
    v = venue_raw.strip()
    if not v or v == "?":
        return "未定"
    for key, display in VENUE_MAP.items():
        if key in v:
            return display
    return v


# ── HTML 清洗 ───────────────────────────────────────────────

def strip_html(text: str) -> str:
    """去掉 HTML 标签，转义 HTML 实体。"""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\r", "")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── 序列化 ──────────────────────────────────────────────

def is_non_live_keyword(title: str) -> bool:
    """检测标题是否包含非 live 关键词。"""
    non_live = [
        "舞台挨拶", "上映会", "配信", "生放送", "リリース",
        "発売記念", "リリイベ", "グッズ", "展示",
        "コラボカフェ", "ポップアップ", "POP UP", "オンライン",
        "MUSEUM", "ミュージアム", "博物館",
    ]
    t_lower = title.lower()
    for kw in non_live:
        if kw.lower() in t_lower:
            return True
    return False


def save_events(events: list[dict], path: str) -> None:
    """将事件列表存为 JSON。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2, default=str)


def load_events(path: str) -> list[dict]:
    """从 JSON 加载事件列表。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)
