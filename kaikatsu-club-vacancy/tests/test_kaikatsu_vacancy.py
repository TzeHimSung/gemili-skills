import json
import pytest
import urllib.error
import urllib.parse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import kaikatsu_vacancy as kv


def test_extract_stores_from_shop_js_flattens_prefecture_groups():
    shop_js = '''
var pref = {"13":"東京都"};
var stores =
{
  "東京都": [
    {"store_code":"20315","store_name":"秋葉原駅前店","tel":"03-5289-3288","address":"東京都千代田区外神田1-13-3<br>受付4F","service":["鍵付完全個室"],"roomtype":["レギュラールーム（多機能）"],"biz":["KC"]},
    {"store_code":"20980","store_name":"秋葉原駅前2号店","tel":"03-6260-7180","address":"東京都千代田区外神田3-15-1","service":[],"roomtype":[],"biz":["KC"]}
  ]
};
'''
    stores = kv.parse_shop_js(shop_js)

    assert [s.code for s in stores] == ["20315", "20980"]
    assert stores[0].prefecture == "東京都"
    assert stores[0].address == "東京都千代田区外神田1-13-3 受付4F"
    assert stores[0].detail_url == "https://www.kaikatsu.jp/shop/detail/20315.html"


def test_extract_google_maps_embed_coordinates_from_detail_html():
    html = '''<iframe src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d810.0254372771138!2d139.77106142823482!3d35.699113667806564!2m3"></iframe>'''

    lat, lon = kv.extract_google_maps_coordinates(html)

    assert round(lat, 6) == 35.699114
    assert round(lon, 6) == 139.771061


def test_parse_vacancy_api_key_from_official_shop_vacancy_js():
    js = '''
    prod_ajax_url = "https://example.com/empty_seat?store_cd=" + store_code;
    prod_api_key = "pk";
    '''

    assert kv.parse_vacancy_api_key(js) == "pk"


def test_normalize_chinese_place_aliases_for_documented_examples():
    assert kv.normalize_place_query("秋叶原站") == "秋葉原駅"
    assert kv.normalize_place_query("羽田机场") == "羽田空港"
    assert kv.normalize_place_query("新宿站") == "新宿駅"


def test_find_nearest_stores_sorts_by_haversine_distance():
    origin = (35.6979189, 139.7754511)  # 秋葉原駅
    stores = [
        kv.Store(code="far", name="遠い店", prefecture="東京都", address="", tel="", lat=35.6764, lon=139.6500),
        kv.Store(code="near", name="近い店", prefecture="東京都", address="", tel="", lat=35.6980, lon=139.7750),
        kv.Store(code="mid", name="中間店", prefecture="東京都", address="", tel="", lat=35.7000, lon=139.7800),
    ]

    nearest = kv.find_nearest_stores(origin, stores, limit=2)

    assert [item.store.code for item in nearest] == ["near", "mid"]
    assert nearest[0].distance_km < nearest[1].distance_km


def test_geocode_scores_multiple_candidates_and_prefers_exact_station_or_airport(monkeypatch):
    requested_urls = []

    def fake_http_get_json(url, *, headers=None, timeout=25):
        requested_urls.append(url)
        if "nominatim.openstreetmap.org" in url:
            return [
                {
                    "display_name": "大田区, 東京都, 日本",
                    "name": "大田区",
                    "lat": "35.5612577",
                    "lon": "139.7160511",
                    "class": "boundary",
                    "type": "administrative",
                    "importance": 0.9,
                },
                {
                    "display_name": "羽田空港, 大田区, 東京都, 日本",
                    "name": "羽田空港",
                    "lat": "35.5493932",
                    "lon": "139.7798386",
                    "class": "aeroway",
                    "type": "aerodrome",
                    "importance": 0.2,
                },
            ]
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(kv, "http_get_json", fake_http_get_json)

    place = kv.geocode_place("羽田空港")

    assert place.display_name == "羽田空港, 大田区, 東京都, 日本"
    assert place.lat == 35.5493932
    assert place.lon == 139.7798386
    nominatim_query = urllib.parse.parse_qs(urllib.parse.urlparse(requested_urls[0]).query)
    assert nominatim_query["limit"] == ["5"]


def test_fetch_store_catalog_raises_when_coordinate_coverage_below_threshold(monkeypatch, tmp_path):
    stores = [
        kv.Store(code=str(index), name=f"店舗{index}", prefecture="東京都", address="", tel="")
        for index in range(1, 6)
    ]

    def fake_enrich(store):
        if store.code in {"4", "5"}:
            raise kv.KaikatsuError("missing coordinates")
        return kv.dataclasses.replace(store, lat=35.0 + int(store.code), lon=139.0 + int(store.code))

    monkeypatch.setattr(kv, "http_get_text", lambda *args, **kwargs: "shop js")
    monkeypatch.setattr(kv, "parse_shop_js", lambda shop_js: stores)
    monkeypatch.setattr(kv, "enrich_store_with_coordinates", fake_enrich)

    with pytest.raises(kv.KaikatsuError) as excinfo:
        kv.fetch_store_catalog(
            refresh_cache=True,
            cache_dir=tmp_path,
            workers=1,
            min_coordinate_coverage=0.8,
        )

    message = str(excinfo.value)
    assert "coordinate coverage" in message
    assert "3/5" in message
    assert "0.80" in message


def test_http_get_text_retries_transient_url_errors(monkeypatch):
    calls = {"count": 0}

    class FakeHeaders:
        def get_content_charset(self):
            return "utf-8"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return "成功".encode("utf-8")

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError("temporary ssl eof")
        return FakeResponse()

    monkeypatch.setattr(kv.urllib.request, "urlopen", fake_urlopen)

    assert kv.http_get_text("https://example.test") == "成功"
    assert calls["count"] == 2


def test_format_report_includes_every_official_seat_type_and_source_links():
    geocoded = kv.GeocodedPlace(query="秋葉原駅", display_name="秋葉原駅, 東京", lat=35.6979, lon=139.7754)
    store = kv.Store(
        code="20315",
        name="秋葉原駅前店",
        prefecture="東京都",
        address="東京都千代田区外神田1-13-3 AOKIの上 3F～6F（受付4F）",
        tel="03-5289-3288",
        lat=35.6991136678,
        lon=139.7710614282,
    )
    nearest = [kv.NearestStore(store=store, distance_km=0.41)]
    vacancies = {
        "20315": kv.VacancyResult(
            store_code="20315",
            status=0,
            message="",
            seats=[
                kv.VacancyItem(name="鍵付個室（チェア）", status="満席", category_id="12", status_no="4"),
                kv.VacancyItem(name="ブース（禁煙）", status="残10席以上", category_id="1", status_no="1"),
            ],
        )
    }

    report = kv.format_markdown_report(geocoded, nearest, vacancies, generated_at_jst="2026-05-10 01:23 JST")

    assert "快活CLUB 空席查询：秋葉原駅" in report
    assert "秋葉原駅前店" in report
    assert "鍵付個室（チェア）：満席" in report
    assert "ブース（禁煙）：残10席以上" in report
    assert "https://www.kaikatsu.jp/shop/detail/20315.html" in report
    assert "https://www.kaikatsu.jp/shop/detail/vacancy.html?store_code=20315" in report
