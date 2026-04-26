"""
anison-live-countdown 公共库
共享的 HTTP 客户端、日期解析、场地映射、日历 helper。
"""

import re
import json
import time
from datetime import date, timedelta
from typing import Optional

import requests

# ── HTTP 客户端 ─────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

NO_PROXY = {"http": None, "https": None}


def http_get(
    url: str,
    referer: str = "",
    timeout: int = 15,
    retries: int = 2,
) -> requests.Response:
    """带重试的 HTTP GET，自动绕过代理。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ja-JP,ja;q=0.9",
    }
    if referer:
        headers["Referer"] = referer

    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                proxies=NO_PROXY,
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise last_exc  # type: ignore[misc]


# ── 日期解析 ────────────────────────────────────────────────

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

# 正则：省略年份的日期（月 月 日 形式）
RE_SHORT_DATE_JA = re.compile(
    r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日"
)

# 正则：ISO date YYYY-MM-DD
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
    
    date_text:  "2026年4月17日(金)・4月26日(日)・5月1日(金)..."
    venue_text: "Zepp Fukuoka、Zepp Namba、Zepp Nagoya..."
    
    Returns: [(full_date_str, venue_str), ...]
    """
    dates = [d.strip() for d in date_text.split("・")]
    venues = [v.strip() for v in venue_text.split("、")]

    result: list[tuple[str, str]] = []
    year = None
    month = None

    for i, d in enumerate(dates):
        ym = RE_DATE_JA.match(d)
        if ym:
            year = ym["y"]
            month = ym["m"]
            result.append((d, venues[i] if i < len(venues) else "未定"))
        elif year:
            sm = RE_SHORT_DATE_JA.match(d)
            if sm:
                full = f"{year}年{sm['m']}月{sm['d']}日"
                result.append((full, venues[i] if i < len(venues) else "未定"))
            elif month:
                # 仅 "日" 省略年月："15日(日)" → 补全年+月
                dm = re.match(r"(\d{1,2})\s*日", d)
                if dm:
                    full = f"{year}年{month}月{dm.group(1)}日"
                    result.append((full, venues[i] if i < len(venues) else "未定"))

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
    """场地名标准化。「未定」保留原样。"""
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
    text = text.replace("&#039;", "'")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&nbsp;", " ")
    text = text.replace("\r", "")
    text = text.replace("\n", " ")
    # 压缩多余空格
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── 序列化 ──────────────────────────────────────────────

def is_non_live_keyword(title: str) -> bool:
    """检测标题是否包含非 live 关键词（舞台挨拶、上映会、配信等）。"""
    non_live = [
        "舞台挨拶",
        "上映会",
        "配信",
        "生放送",
        "リリース",
        "発売記念",
        "リリイベ",
        "グッズ",
        "展示",
        "コラボカフェ",
        "ポップアップ",
        "POP UP",
        "オンライン",
    ]
    t_lower = title.lower()
    for kw in non_live:
        if kw.lower() in t_lower:
            return True
    return False


def save_events(
    events: list[dict],
    path: str,
) -> None:
    """将事件列表存为 JSON。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2, default=str)


def load_events(path: str) -> list[dict]:
    """从 JSON 加载事件列表。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)
