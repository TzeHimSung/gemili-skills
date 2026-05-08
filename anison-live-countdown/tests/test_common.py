import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import split_tour_dates  # noqa: E402


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
