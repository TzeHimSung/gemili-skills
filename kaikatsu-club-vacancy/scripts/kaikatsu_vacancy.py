#!/usr/bin/env python3
"""Find nearest Kaikatsu CLUB stores and current room/seat availability.

Data sources:
- Store catalog: https://www.kaikatsu.jp/data/shop.js
- Store coordinates: Google Maps embed URL on each official store detail page
- Vacancy: official public API used by /shop/detail/vacancy.html
- Geocoding: OpenStreetMap Nominatim, with GSI address-search fallback
"""
from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import functools
import html
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

BASE_URL = "https://www.kaikatsu.jp"
SHOP_JS_URL = f"{BASE_URL}/data/shop.js"
DETAIL_URL_TEMPLATE = f"{BASE_URL}/shop/detail/{{code}}.html"
VACANCY_URL_TEMPLATE = (
    "https://jx5rl6ilkg.execute-api.ap-northeast-1.amazonaws.com/prd/empty_seat?store_cd={code}"
)
VACANCY_JS_URL = f"{BASE_URL}/common/js/shop_vacancy.js"
USER_AGENT = "Hermes Kaikatsu Club Vacancy Skill/1.0 (+https://www.kaikatsu.jp/)"
DEFAULT_CACHE_DIR = Path(os.environ.get("KAIKATSU_CACHE_DIR", Path.home() / ".cache" / "hermes" / "kaikatsu-club-vacancy"))
STORE_CACHE_FILE = "stores_with_coordinates.json"
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


@dataclasses.dataclass(frozen=True)
class Store:
    code: str
    name: str
    prefecture: str
    address: str
    tel: str
    services: tuple[str, ...] = ()
    roomtypes: tuple[str, ...] = ()
    lat: float | None = None
    lon: float | None = None

    @property
    def detail_url(self) -> str:
        return DETAIL_URL_TEMPLATE.format(code=self.code)

    @property
    def vacancy_url(self) -> str:
        return f"{BASE_URL}/shop/detail/vacancy.html?store_code={self.code}"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Store":
        return cls(
            code=str(data["code"]),
            name=str(data["name"]),
            prefecture=str(data.get("prefecture", "")),
            address=str(data.get("address", "")),
            tel=str(data.get("tel", "")),
            services=tuple(data.get("services") or ()),
            roomtypes=tuple(data.get("roomtypes") or ()),
            lat=float(data["lat"]) if data.get("lat") is not None else None,
            lon=float(data["lon"]) if data.get("lon") is not None else None,
        )


@dataclasses.dataclass(frozen=True)
class NearestStore:
    store: Store
    distance_km: float


@dataclasses.dataclass(frozen=True)
class GeocodedPlace:
    query: str
    display_name: str
    lat: float
    lon: float


@dataclasses.dataclass(frozen=True)
class VacancyItem:
    name: str
    status: str
    category_id: str = ""
    status_no: str = ""


@dataclasses.dataclass(frozen=True)
class VacancyResult:
    store_code: str
    status: int | None
    message: str
    seats: list[VacancyItem]


class KaikatsuError(RuntimeError):
    """Raised when official data cannot be fetched or parsed."""


def http_get_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
    retries: int = 2,
    retry_delay: float = 0.25,
) -> str:
    request_headers = {"User-Agent": USER_AGENT, "Accept-Language": "ja,en-US;q=0.8,en;q=0.6"}
    if headers:
        request_headers.update(headers)
    last_error: urllib.error.URLError | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            # HTTP status errors are deterministic enough that retrying usually only delays the user.
            raise KaikatsuError(f"HTTP {exc.code} while fetching {url}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
    reason = getattr(last_error, "reason", last_error)
    raise KaikatsuError(f"Network error while fetching {url}: {reason}") from last_error


def http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 25) -> Any:
    text = http_get_text(url, headers=headers, timeout=timeout)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise KaikatsuError(f"Invalid JSON from {url}: {exc}") from exc


def clean_html_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<\s*br\s*/?\s*>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _extract_js_object_after_var(script: str, var_name: str) -> str:
    match = re.search(rf"var\s+{re.escape(var_name)}\s*=\s*", script)
    if not match:
        raise KaikatsuError(f"Cannot find var {var_name} in shop.js")
    start = script.find("{", match.end())
    if start < 0:
        raise KaikatsuError(f"Cannot find object start for var {var_name}")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(script)):
        char = script[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return script[start : index + 1]
    raise KaikatsuError(f"Cannot find object end for var {var_name}")


def parse_shop_js(shop_js: str) -> list[Store]:
    stores_json = _extract_js_object_after_var(shop_js, "stores")
    raw_by_pref = json.loads(stores_json)
    stores: list[Store] = []
    for prefecture, entries in raw_by_pref.items():
        for entry in entries:
            code = str(entry.get("store_code", "")).strip()
            if not code:
                continue
            stores.append(
                Store(
                    code=code,
                    name=str(entry.get("store_name", "")).strip(),
                    prefecture=str(prefecture),
                    address=clean_html_text(str(entry.get("address", ""))),
                    tel=str(entry.get("tel", "")).strip(),
                    services=tuple(str(item) for item in entry.get("service", []) if str(item).strip()),
                    roomtypes=tuple(str(item) for item in entry.get("roomtype", []) if str(item).strip()),
                )
            )
    if not stores:
        raise KaikatsuError("No stores parsed from shop.js")
    return stores


def extract_google_maps_coordinates(detail_html: str) -> tuple[float, float]:
    # Official detail pages embed Google Maps URLs containing !2d<lon>!3d<lat>.
    match = re.search(r"!2d(-?\d+(?:\.\d+)?)!3d(-?\d+(?:\.\d+)?)", detail_html)
    if not match:
        raise KaikatsuError("No Google Maps coordinates found in store detail page")
    lon = float(match.group(1))
    lat = float(match.group(2))
    return lat, lon


def parse_vacancy_api_key(shop_vacancy_js: str) -> str:
    match = re.search(r"prod_api_key\s*=\s*['\"]([^'\"]+)['\"]", shop_vacancy_js)
    if not match:
        raise KaikatsuError("Cannot find vacancy API key in official shop_vacancy.js")
    return match.group(1)


@functools.lru_cache(maxsize=1)
def get_vacancy_api_key() -> str:
    shop_vacancy_js = http_get_text(VACANCY_JS_URL, headers={"Referer": f"{BASE_URL}/shop/detail/vacancy.html"})
    return parse_vacancy_api_key(shop_vacancy_js)


def enrich_store_with_coordinates(store: Store) -> Store:
    detail_html = http_get_text(store.detail_url, headers={"Referer": f"{BASE_URL}/shop/"})
    lat, lon = extract_google_maps_coordinates(detail_html)
    return dataclasses.replace(store, lat=lat, lon=lon)


def cache_file_path(cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    return cache_dir / STORE_CACHE_FILE


def load_cached_stores(cache_dir: Path = DEFAULT_CACHE_DIR, *, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[Store] | None:
    path = cache_file_path(cache_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = dt.datetime.fromisoformat(payload["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=dt.timezone.utc)
        age = dt.datetime.now(dt.timezone.utc) - fetched_at.astimezone(dt.timezone.utc)
        if age.total_seconds() > ttl_seconds:
            return None
        return [Store.from_dict(item) for item in payload["stores"]]
    except Exception:
        return None


def save_cached_stores(stores: Iterable[Store], cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": SHOP_JS_URL,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stores": [store.to_dict() for store in stores],
    }
    cache_file_path(cache_dir).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_store_catalog(
    *,
    refresh_cache: bool = False,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    workers: int = 16,
    min_coordinate_coverage: float = 0.8,
) -> list[Store]:
    if not refresh_cache:
        cached = load_cached_stores(cache_dir)
        if cached:
            return cached

    shop_js = http_get_text(SHOP_JS_URL, headers={"Referer": BASE_URL})
    stores = parse_shop_js(shop_js)
    enriched: list[Store] = []
    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_store = {executor.submit(enrich_store_with_coordinates, store): store for store in stores}
        for future in concurrent.futures.as_completed(future_to_store):
            store = future_to_store[future]
            try:
                enriched.append(future.result())
            except Exception as exc:  # Keep other stores usable if one detail page changes.
                errors.append(f"{store.code} {store.name}: {exc}")

    enriched.sort(key=lambda store: store.code)
    coverage = len(enriched) / len(stores)
    if coverage < min_coordinate_coverage:
        raise KaikatsuError(
            "Store coordinate coverage "
            f"{len(enriched)}/{len(stores)} ({coverage:.2f}) is below required minimum "
            f"{min_coordinate_coverage:.2f}; cannot rank nearest stores safely"
        )
    if len(enriched) < 3:
        raise KaikatsuError("Too few stores with coordinates; cannot rank nearest stores")
    save_cached_stores(enriched, cache_dir)
    return enriched


def normalize_place_query(query: str) -> str:
    normalized = re.sub(r"\s+", "", query.strip())
    replacements = [
        ("车站", "駅"),
        ("車站", "駅"),
        ("站", "駅"),
        ("机场", "空港"),
        ("機場", "空港"),
        ("飛機場", "空港"),
        ("秋叶原", "秋葉原"),
        ("东京", "東京"),
        ("涩谷", "渋谷"),
        ("涉谷", "渋谷"),
        ("银座", "銀座"),
        ("横滨", "横浜"),
        ("难波", "難波"),
        ("筑波", "つくば"),
    ]
    for source, target in replacements:
        normalized = normalized.replace(source, target)
    return normalized


def _compact_geocode_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").casefold())


def _candidate_names(result: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("name", "display_name"):
        value = result.get(key)
        if value:
            names.append(str(value))
    namedetails = result.get("namedetails")
    if isinstance(namedetails, dict):
        names.extend(str(value) for value in namedetails.values() if value)
    return names


def _score_geocode_candidate(query: str, result: dict[str, Any]) -> float:
    query_text = _compact_geocode_text(query)
    score = 0.0
    try:
        score += float(result.get("importance") or 0.0)
    except (TypeError, ValueError):
        pass

    candidate_texts = [_compact_geocode_text(name) for name in _candidate_names(result)]
    exact_name_match = any(text == query_text for text in candidate_texts)
    contains_query = any(query_text and query_text in text for text in candidate_texts)
    contained_by_query = any(text and text in query_text for text in candidate_texts)
    if exact_name_match:
        score += 100.0
    elif contains_query:
        score += 60.0
    elif contained_by_query:
        score += 25.0

    result_class = str(result.get("class") or "").casefold()
    result_type = str(result.get("type") or "").casefold()
    poi_pairs = {
        ("railway", "station"),
        ("railway", "halt"),
        ("public_transport", "station"),
        ("aeroway", "aerodrome"),
        ("aeroway", "terminal"),
        ("amenity", "bus_station"),
    }
    if (result_class, result_type) in poi_pairs or result_type in {"station", "train_station", "airport"}:
        score += 30.0

    if result_class == "boundary" or result_type in {"administrative", "municipality", "province", "prefecture"}:
        # POIs should win for ambiguous queries such as "東京", but an exact
        # administrative query like "東京都" must not be displaced by a station
        # that only mentions the prefecture in its address/display_name.
        if exact_name_match:
            score += 20.0
        else:
            score -= 40.0
            if not contains_query:
                score -= 40.0
    return score


def _select_best_geocode_candidate(query: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None
    return max(results, key=lambda result: _score_geocode_candidate(query, result))


def geocode_place(query: str) -> GeocodedPlace:
    original_query = query.strip()
    if not original_query:
        raise KaikatsuError("地名が空です。例：秋葉原駅、羽田空港")

    normalized_query = normalize_place_query(original_query)
    candidate_queries = [normalized_query]
    if normalized_query != original_query:
        candidate_queries.append(original_query)

    for candidate_query in candidate_queries:
        nominatim_url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {
                "q": candidate_query,
                "format": "jsonv2",
                "countrycodes": "jp",
                "limit": "5",
                "accept-language": "ja",
            }
        )
        try:
            results = http_get_json(nominatim_url, timeout=25)
            if results:
                first = _select_best_geocode_candidate(candidate_query, results) or results[0]
                return GeocodedPlace(
                    query=original_query,
                    display_name=str(first.get("display_name") or first.get("name") or candidate_query),
                    lat=float(first["lat"]),
                    lon=float(first["lon"]),
                )
        except Exception:
            pass

    for candidate_query in candidate_queries:
        gsi_url = "https://msearch.gsi.go.jp/address-search/AddressSearch?" + urllib.parse.urlencode({"q": candidate_query})
        try:
            results = http_get_json(gsi_url, timeout=25)
            if results:
                first = results[0]
                lon, lat = first["geometry"]["coordinates"][:2]
                title = first.get("properties", {}).get("title") or candidate_query
                return GeocodedPlace(query=original_query, display_name=str(title), lat=float(lat), lon=float(lon))
        except Exception:
            pass
    raise KaikatsuError(f"日本国内の地名として位置を特定できませんでした：{original_query}")


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def find_nearest_stores(origin: tuple[float, float], stores: Iterable[Store], *, limit: int = 3) -> list[NearestStore]:
    ranked: list[NearestStore] = []
    for store in stores:
        if store.lat is None or store.lon is None:
            continue
        ranked.append(NearestStore(store=store, distance_km=haversine_km(origin, (store.lat, store.lon))))
    ranked.sort(key=lambda item: item.distance_km)
    return ranked[:limit]


def fetch_vacancy(store_code: str) -> VacancyResult:
    url = VACANCY_URL_TEMPLATE.format(code=urllib.parse.quote(store_code))
    data = http_get_json(
        url,
        headers={
            "x-api-key": get_vacancy_api_key(),
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/shop/detail/vacancy.html?store_code={store_code}",
            "Accept": "application/json, text/plain, */*",
        },
        timeout=25,
    )
    seats = [
        VacancyItem(
            name=str(item.get("seat_name", "")),
            status=str(item.get("seat_status", "")),
            category_id=str(item.get("category_id", "")),
            status_no=str(item.get("status_no", "")),
        )
        for item in data.get("seat_type", [])
    ]
    return VacancyResult(
        store_code=str(data.get("store_cd") or store_code),
        status=data.get("status"),
        message=str(data.get("message", "")),
        seats=seats,
    )


def fetch_vacancies(store_codes: Iterable[str], *, workers: int = 6) -> dict[str, VacancyResult]:
    results: dict[str, VacancyResult] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_code = {executor.submit(fetch_vacancy, code): code for code in store_codes}
        for future in concurrent.futures.as_completed(future_to_code):
            code = future_to_code[future]
            try:
                results[code] = future.result()
            except Exception as exc:
                results[code] = VacancyResult(store_code=code, status=None, message=f"取得失敗: {exc}", seats=[])
    return results


def jst_now_string() -> str:
    return dt.datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")


def format_markdown_report(
    geocoded: GeocodedPlace,
    nearest: list[NearestStore],
    vacancies: dict[str, VacancyResult],
    *,
    generated_at_jst: str | None = None,
) -> str:
    generated_at_jst = generated_at_jst or jst_now_string()
    lines = [
        f"# 快活CLUB 空席查询：{geocoded.query}",
        "",
        f"基准地点：{geocoded.display_name}",
        f"坐标：{geocoded.lat:.6f}, {geocoded.lon:.6f}",
        f"查询时间：{generated_at_jst}",
        "",
    ]
    for index, item in enumerate(nearest, start=1):
        store = item.store
        vacancy = vacancies.get(store.code)
        lines.extend(
            [
                f"## {index}. {store.name}（约 {item.distance_km:.2f} km）",
                f"地址：{store.address or '官网未提供'}",
                f"电话：{store.tel or '官网未提供'}",
                f"店铺页：{store.detail_url}",
                f"空席页：{store.vacancy_url}",
                "",
                "空席状况：",
            ]
        )
        if vacancy is None:
            lines.append("- 取得失败：未返回数据")
        elif vacancy.status not in (0, "0"):
            lines.append(f"- 取得失败：{vacancy.message or '官网接口返回异常'}")
        elif not vacancy.seats:
            lines.append("- 官网当前未返回任何席种/房型")
        else:
            for seat in vacancy.seats:
                lines.append(f"- {seat.name}：{seat.status}")
        lines.append("")
    lines.extend(
        [
            "※ 空席信息来自快活CLUB官网公开空席接口；到店时可能已变化，请以现场/官网实时页面为准。",
            "※ 距离为直线距离，不等于步行/乘车距离。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def query_nearest_vacancies(
    place: str,
    *,
    limit: int = 3,
    refresh_cache: bool = False,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    workers: int = 16,
) -> str:
    geocoded = geocode_place(place)
    stores = fetch_store_catalog(refresh_cache=refresh_cache, cache_dir=cache_dir, workers=workers)
    nearest = find_nearest_stores((geocoded.lat, geocoded.lon), stores, limit=limit)
    if not nearest:
        raise KaikatsuError("座標付き店舗が見つからず、最寄り店舗を判定できませんでした。")
    vacancies = fetch_vacancies([item.store.code for item in nearest])
    return format_markdown_report(geocoded, nearest, vacancies)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find nearest Kaikatsu CLUB stores and official vacancy status.")
    parser.add_argument("place", help="日本地名 / 駅名 / 空港名。例：秋葉原駅、羽田空港")
    parser.add_argument("--limit", type=int, default=3, help="返す店舗数（デフォルト: 3）")
    parser.add_argument("--refresh-cache", action="store_true", help="店舗座標キャッシュを再構築する")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help="キャッシュ保存ディレクトリ")
    parser.add_argument("--workers", type=int, default=16, help="店舗詳細取得の並列数")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        started = time.time()
        report = query_nearest_vacancies(
            args.place,
            limit=max(1, args.limit),
            refresh_cache=args.refresh_cache,
            cache_dir=args.cache_dir,
            workers=max(1, args.workers),
        )
        print(report)
        if os.environ.get("KAIKATSU_DEBUG_TIMING"):
            print(f"<!-- elapsed={time.time() - started:.2f}s -->", file=sys.stderr)
        return 0
    except KaikatsuError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
