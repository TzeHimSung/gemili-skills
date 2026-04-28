from datetime import date
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import scrape_idolmaster as imas  # noqa: E402


def test_parse_official_article_splits_multi_day_without_hi_marker():
    article = {
        "title": "315 Production presents F＠NTASTIC BATTLE FES ～Wanna step in～ 幕張公演",
        "event_dspdate": "2027年1月23(土)・24(日)",
        "event_place": "幕張イベントホール\n※詳細は後日発表予定",
        "event_url": "https://idolmaster-official.jp/news/01_18429",
        "article_type": "url_link",
        "brand": [{"name": "SideM", "code": "SIDEM"}],
    }

    events = imas._parse_official_article(article, today=date(2026, 4, 28))

    assert [e["date"] for e in events] == ["2027-01-23", "2027-01-24"]
    assert {e["series"] for e in events} == {"SideM"}
    assert all(e["venue"] == "幕張イベントホール" for e in events)
    assert all(e["detail_link"] == "https://idolmaster-official.jp/news/01_18429" for e in events)


def test_parse_official_article_handles_holiday_dot_inside_weekday():
    article = {
        "title": "学園アイドルマスター LIVE TOUR -標- 岩手公演",
        "event_dspdate": "2026年9月22日(火・祝)・23日(水・祝)",
        "event_place": "トーサイクラシックホール岩手（岩手県民会館） 大ホール",
        "event_url": "https://idolmaster-official.jp/live_event/gkmas_livetour_shirube/",
        "article_type": "url_link",
        "brand": [{"name": "学園アイドルマスター", "code": "GAKUEN"}],
    }

    events = imas._parse_official_article(article, today=date(2026, 4, 28))

    assert [e["date"] for e in events] == ["2026-09-22", "2026-09-23"]
    assert {e["series"] for e in events} == {"学園アイマス"}
    assert all(e["artists"] == ["学園アイドルマスター"] for e in events)


def test_parse_official_article_maps_venue_by_matching_multiblock_date_section():
    article = {
        "title": "学園アイドルマスター The 2nd Period H.I.F選抜試験 / Hatsuboshi IDOL FESTIVAL",
        "event_dspdate": (
            "学園アイドルマスター The 2nd Period H.I.F選抜試験(セレクション)\n"
            "2026年5月16日(土) 開場 16:00 / 開演 17:00\n"
            "2026年5月17日(日） 開場 15:00 / 開演 16:00\n\n"
            "学園アイドルマスター The 2nd Period Hatsuboshi IDOL FESTIVAL\n"
            "2026年6月6日(土) 開場 15:30 / 開演 17:00\n"
            "2026年6月7日(日) 開場 15:30 / 開演 17:00"
        ),
        "event_place": (
            "学園アイドルマスター The 2nd Period H.I.F選抜試験(セレクション)\n"
            "幕張メッセ・イベントホール\n\n"
            "学園アイドルマスター The 2nd Period Hatsuboshi IDOL FESTIVAL\n"
            "横浜アリーナ"
        ),
        "event_url": "https://idolmaster-official.jp/live_event/gkmas_2ndperiod/",
        "article_type": "url_link",
        "brand": [{"name": "学園アイドルマスター", "code": "GAKUEN"}],
    }

    events = imas._parse_official_article(article, today=date(2026, 4, 28))

    assert [(e["date"], e["venue"]) for e in events] == [
        ("2026-05-16", "幕張メッセ"),
        ("2026-05-17", "幕張メッセ"),
        ("2026-06-06", "横浜アリーナ"),
        ("2026-06-07", "横浜アリーナ"),
    ]


def test_parse_official_article_maps_millionlive_brand_code():
    article = {
        "title": "THE IDOLM@STER MILLION LIVE! 13thLIVE",
        "event_dspdate": "2026年5月5日(火･祝)",
        "event_place": "有明アリーナ",
        "event_url": "https://idolmaster-official.jp/live_event/million13th/",
        "article_type": "url_link",
        "brand": [{"name": "ミリオンライブ！", "code": "MILLIONLIVE"}],
    }

    events = imas._parse_official_article(article, today=date(2026, 4, 28))

    assert events[0]["series"] == "MILLION LIVE!"


def test_parse_official_article_filters_museum_non_live_event():
    article = {
        "title": "THE IDOLM@STER SideM STAGE COSTUME MUSEUM",
        "event_dspdate": "2026年7月10日（金）～7月16日（木）",
        "event_place": "渋谷BEAM「BEAMギャラリー」",
        "event_url": "https://idolmaster-official.jp/live_event/sidem_stage_costume_museum/",
        "article_type": "url_link",
        "brand": [{"name": "SideM", "code": "SIDEM"}],
    }

    assert imas._parse_official_article(article, today=date(2026, 4, 28)) == []


def test_cms_get_json_retries_transient_connection_error(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"statusCode": 200, "data": {"ok": True}}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise imas.requests.ConnectionError("reset")
        return FakeResponse()

    monkeypatch.setattr(imas.requests, "get", fake_get)
    monkeypatch.setattr(imas.time, "sleep", lambda _: None)

    assert imas._cms_get_json("https://example.invalid") == {"statusCode": 200, "data": {"ok": True}}
    assert calls["count"] == 2


def test_build_official_cms_request_uses_article_list_not_html_shell():
    token = "dummy-token"

    endpoint, params = imas._build_official_cms_request(
        token,
        today=date(2026, 4, 28),
    )

    assert endpoint.endswith("idolmaster/Article/list")
    assert params["site"] == "jp"
    assert params["ip"] == "idolmaster"
    assert params["token"] == token
    assert '"category":["LIVE-EVENT"]' in params["data"]
    assert '"article_type":["url_link","detail_page"]' in params["data"]
    assert "target_start_date" in params["data"]
    assert "target_end_date" in params["data"]
