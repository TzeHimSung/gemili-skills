import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import common  # noqa: E402
from common import split_tour_dates  # noqa: E402


def test_jst_today_uses_asia_tokyo_and_is_datetime_monkeypatchable(monkeypatch):
    class FrozenDatetime:
        seen_tz = None

        @classmethod
        def now(cls, tz=None):
            cls.seen_tz = tz
            return datetime(2026, 5, 16, 0, 30, tzinfo=tz)

    monkeypatch.setattr(common, "datetime", FrozenDatetime)

    assert common.jst_today() == date(2026, 5, 16)
    assert isinstance(FrozenDatetime.seen_tz, ZoneInfo)
    assert FrozenDatetime.seen_tz.key == "Asia/Tokyo"


def test_jst_now_uses_asia_tokyo_and_keeps_time(monkeypatch):
    class FrozenDatetime:
        seen_tz = None

        @classmethod
        def now(cls, tz=None):
            cls.seen_tz = tz
            return datetime(2026, 5, 16, 0, 30, tzinfo=tz)

    monkeypatch.setattr(common, "datetime", FrozenDatetime)

    assert common.jst_now().strftime("%Y-%m-%d %H:%M") == "2026-05-16 00:30"
    assert isinstance(FrozenDatetime.seen_tz, ZoneInfo)
    assert FrozenDatetime.seen_tz.key == "Asia/Tokyo"


def test_countdown_days_accepts_captured_today_to_avoid_midnight_race():
    assert common.countdown_days(date(2026, 5, 15), today=date(2026, 5, 15)) == 0


def test_split_tour_dates_keeps_latest_explicit_month_for_day_only_fragment():
    tours = split_tour_dates(
        "2026年6月18日・6月26日・8月14日・15日",
        "東京・大阪・名古屋・福岡",
    )

    assert tours == [
        ("2026年6月18日", "東京"),
        ("2026年6月26日", "大阪"),
        ("2026年8月14日", "名古屋"),
        ("2026年8月15日", "福岡"),
    ]


def test_split_tour_dates_splits_venues_on_japanese_dot_newline_and_slash():
    tours = split_tour_dates(
        "2026年6月18日・6月26日・8月14日",
        "SGC HALL ARIAKE・神戸国際会館こくさいホール\nAsiaWorld-Expo",
    )

    assert [venue for _, venue in tours] == [
        "SGC HALL ARIAKE",
        "神戸国際会館こくさいホール",
        "AsiaWorld-Expo",
    ]

    slash_tours = split_tour_dates(
        "2026年9月1日・9月2日",
        "Kアリーナ横浜 / 大阪城ホール",
    )
    assert [venue for _, venue in slash_tours] == ["Kアリーナ横浜", "大阪城ホール"]


def test_split_tour_dates_accepts_slash_and_range_date_separators():
    slash_tours = split_tour_dates(
        "2026年6月18日 / 6月26日",
        "東京 / 大阪",
    )
    range_tours = split_tour_dates(
        "2026年6月18日〜19日（木・金）",
        "東京",
    )

    assert slash_tours == [("2026年6月18日", "東京"), ("2026年6月26日", "大阪")]
    assert range_tours == [("2026年6月18日", "東京"), ("2026年6月19日", "東京")]


def test_split_tour_dates_expands_three_day_japanese_date_range():
    tours = split_tour_dates(
        "2026年5月2日(土)〜4日(月)",
        "Kアリーナ横浜",
    )

    assert tours == [
        ("2026年5月2日", "Kアリーナ横浜"),
        ("2026年5月3日", "Kアリーナ横浜"),
        ("2026年5月4日", "Kアリーナ横浜"),
    ]


def test_split_tour_dates_expands_only_pairs_joined_by_range_separator():
    tours = split_tour_dates(
        "2026年5月2日(土)〜4日(月)・6日(水)",
        "Kアリーナ横浜",
    )

    assert tours == [
        ("2026年5月2日", "Kアリーナ横浜"),
        ("2026年5月3日", "Kアリーナ横浜"),
        ("2026年5月4日", "Kアリーナ横浜"),
        ("2026年5月6日", "Kアリーナ横浜"),
    ]


def test_split_tour_dates_range_uses_start_venue_before_next_venue():
    tours = split_tour_dates(
        "2026年5月2日(土)〜4日(月)・6日(水)",
        "東京・大阪",
    )

    assert tours == [
        ("2026年5月2日", "東京"),
        ("2026年5月3日", "東京"),
        ("2026年5月4日", "東京"),
        ("2026年5月6日", "大阪"),
    ]


def test_split_tour_dates_range_endpoint_does_not_consume_next_venue_slot():
    tours = split_tour_dates(
        "2026年5月2日(土)〜4日(月)・6日(水)・8日(金)",
        "東京・大阪・名古屋",
    )

    assert tours == [
        ("2026年5月2日", "東京"),
        ("2026年5月3日", "東京"),
        ("2026年5月4日", "東京"),
        ("2026年5月6日", "大阪"),
        ("2026年5月8日", "名古屋"),
    ]


def test_split_tour_dates_keeps_newline_separator_alignment_before_range():
    tours = split_tour_dates(
        "2026年5月1日\n5月2日〜4日",
        "東京\n大阪",
    )

    assert tours == [
        ("2026年5月1日", "東京"),
        ("2026年5月2日", "大阪"),
        ("2026年5月3日", "大阪"),
        ("2026年5月4日", "大阪"),
    ]


def test_split_tour_dates_expands_cross_year_range_when_end_month_wraps():
    tours = split_tour_dates(
        "2026年12月31日(水)〜1月2日(金)",
        "東京",
    )

    assert tours == [
        ("2026年12月31日", "東京"),
        ("2027年1月1日", "東京"),
        ("2027年1月2日", "東京"),
    ]


def _load_lovelive_module(module_name: str):
    import importlib.util

    script = SCRIPTS / "scrape_lovelive.py"
    sys.modules.pop("common", None)
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(module_name, script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        while str(SCRIPTS) in sys.path:
            sys.path.remove(str(SCRIPTS))


def test_lovelive_jsonld_uses_lovelive_specific_venue_mapping():
    module = _load_lovelive_module("lovelive_jsonld_venue_under_test")
    events = []

    module._parse_jsonld_event(
        {
            "@type": "Event",
            "name": "LoveLive! Test Live",
            "startDate": "2026-06-01",
            "location": {"name": "西武ドーム"},
            "performer": {"name": "Aqours"},
            "url": "https://example.test/live",
        },
        events,
        "Aqours",
        "https://www.lovelive-anime.jp/uranohoshi/live/",
        date(2026, 5, 1),
    )

    assert events[0]["venue"] == "西武ドーム (ベルーナドーム)"


def test_lovelive_card_fallback_keeps_detail_href():
    module = _load_lovelive_module("lovelive_card_href_under_test")

    ev = module._parse_ll_card(
        """
        <a href="./detail/live-2026.html">
          <h3>ラブライブ！テストライブ</h3>
          <p>2026年6月1日(月)</p>
          <p>Kアリーナ横浜</p>
        </a>
        """,
        "Liella!",
        "https://www.lovelive-anime.jp/yuigaoka/live/",
        date(2026, 5, 1),
    )

    assert ev is not None
    assert ev["detail_link"] == "https://www.lovelive-anime.jp/yuigaoka/live/detail/live-2026.html"
