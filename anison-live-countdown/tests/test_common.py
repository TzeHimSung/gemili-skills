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
