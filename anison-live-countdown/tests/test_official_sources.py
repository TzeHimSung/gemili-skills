import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import scrape_bangdream  # noqa: E402
import scrape_lovelive  # noqa: E402


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


def _default_official_sources() -> list[dict[str, str]]:
    return scrape_bangdream.official_source_urls() + scrape_lovelive.official_source_urls()


def test_default_official_sources_match_enabled_anison_contract():
    expected = [
        {
            "franchise": "BanG Dream!",
            "name": "BanG Dream!",
            "url": scrape_bangdream.BASE_URL,
            "referer": scrape_bangdream.BASE_URL,
        },
        *[
            {
                "franchise": "LoveLive!",
                "name": cfg["name"],
                "url": cfg["url"],
                "referer": cfg["referer"],
            }
            for cfg in scrape_lovelive.SERIES_CONFIG
        ],
    ]

    assert _default_official_sources() == expected


def test_default_official_sources_are_http_urls_and_exclude_idolmaster():
    sources = _default_official_sources()

    assert len(sources) == 1 + len(scrape_lovelive.SERIES_CONFIG)
    for source in sources:
        assert set(source) == {"franchise", "name", "url", "referer"}
        for key in ("url", "referer"):
            parts = urlsplit(source[key])
            assert parts.scheme in {"http", "https"}
            assert parts.netloc

    source_blob = "\n".join(
        str(value).lower()
        for source in sources
        for value in source.values()
    )
    assert "idolmaster" not in source_blob


def test_lovelive_html_extraction_uses_jst_today(monkeypatch):
    monkeypatch.setattr(scrape_lovelive, "jst_today", lambda: date(2026, 5, 15))
    html = """
    <html><body>
      <h2>LoveLive JST boundary live</h2>
      <p>2026年5月14日</p>
    </body></html>
    """

    events = scrape_lovelive._extract_events_from_html(
        html,
        "Liella!",
        "https://www.lovelive-anime.jp/yuigaoka/live/",
    )

    assert events == []


def test_lovelive_countdown_uses_same_captured_today_as_filter(monkeypatch):
    captured_today = date(2026, 5, 15)
    monkeypatch.setattr(scrape_lovelive, "jst_today", lambda: captured_today)

    def fake_countdown_days(event_date, *, today=None):
        assert today == captured_today
        return (event_date - today).days

    monkeypatch.setattr(scrape_lovelive, "countdown_days", fake_countdown_days)
    html = """
    <html><body>
      <section>
        <strong>LoveLive same-day live</strong>
        <p>2026年5月15日</p>
      </section>
    </body></html>
    """

    events = scrape_lovelive._extract_events_from_html(
        html,
        "Liella!",
        "https://www.lovelive-anime.jp/yuigaoka/live/",
    )

    assert events[0]["countdown_days"] == 0


def test_lovelive_list_date_range_crossing_today_keeps_today_and_future(monkeypatch):
    monkeypatch.setattr(scrape_lovelive, "jst_today", lambda: date(2026, 5, 3))
    html = """
    <html><body>
      <ul>
        <li>
          <div class="live_info">
            <div class="live_title"><p>ラブライブ！スーパースター!! Cross Today Live</p></div>
            <div class="schedule">開催日時 2026年5月2日(土)〜4日(月)</div>
            <div class="place">Kアリーナ横浜</div>
            <a href="./cross-today/">detail</a>
          </div>
        </li>
      </ul>
    </body></html>
    """

    events = scrape_lovelive._extract_events_from_html(
        html,
        "Liella!",
        "https://www.lovelive-anime.jp/yuigaoka/live/",
    )

    assert [event["date"] for event in events] == ["2026-05-03", "2026-05-04"]
    assert {event["venue"] for event in events} == {"K Arena 横浜"}


def test_lovelive_hasunosora_stage_range_crossing_today_keeps_today_only():
    html = """
    <html><body>
      <section>
        <div class="list__inner">
          <ul>
            <li>
              <a href="/hasunosora/live-event/detail/1">
                <div class="live_ico"><span>ライブ</span></div>
                <div class="live_title"><p>ラブライブ！蓮ノ空女学院スクールアイドルクラブ Stage Range Live</p></div>
                <div class="live_date"><span>【日程】＜愛知公演／2026年5月2日(土)～5月3日(日)＞</span></div>
                <div class="live_place"><span>＜愛知公演／有明アリーナ＞</span></div>
              </a>
            </li>
          </ul>
        </div>
      </section>
    </body></html>
    """

    events = scrape_lovelive._parse_hasunosora_page(
        html,
        "蓮ノ空女学院",
        "https://www.lovelive-anime.jp/hasunosora/live-event/",
        date(2026, 5, 3),
    )

    assert [event["date"] for event in events] == ["2026-05-03"]
    assert events[0]["venue"] == "Ariake Arena"


def test_bangdream_countdown_uses_same_captured_today_as_filter(monkeypatch):
    captured_today = date(2026, 5, 15)
    monkeypatch.setattr(scrape_bangdream, "jst_today", lambda: captured_today)

    def fake_countdown_days(event_date, *, today=None):
        assert today == captured_today
        return (event_date - today).days

    monkeypatch.setattr(scrape_bangdream, "countdown_days", fake_countdown_days)
    monkeypatch.setattr(
        scrape_bangdream,
        "http_get",
        lambda *args, **kwargs: _FakeResponse(
            '''
            <article class="p-live-event-list__item">
              <div class="p-live-event-list__item-category"><span>ライブ</span></div>
              <div class="p-live-event-list__item-title">BanG Dream same-day live</div>
              <div class="p-live-event-list__item-date"><p>2026年5月15日</p></div>
              <div class="p-live-event-list__item-place"><p>有明アリーナ</p></div>
              <span class="p-live-event-list__item-artist-item">Poppin'Party</span>
              <a href="/events/1">detail</a>
            </article>
            '''
        ),
    )

    events = scrape_bangdream.scrape()

    assert events[0]["countdown_days"] == 0


def test_bangdream_fetches_detail_page_date_when_list_row_has_no_date(monkeypatch):
    captured_today = date(2026, 5, 15)
    monkeypatch.setattr(scrape_bangdream, "jst_today", lambda: captured_today)
    calls = []

    def fake_http_get(url, **kwargs):
        calls.append((url, kwargs))
        if url == scrape_bangdream.BASE_URL:
            return _FakeResponse(
                '''
                <article class="p-live-event-list__item">
                  <div class="p-live-event-list__item-category"><span>ライブ</span></div>
                  <div class="p-live-event-list__item-title">Detail Date Live</div>
                  <div class="p-live-event-list__item-place"><p>有明アリーナ</p></div>
                  <span class="p-live-event-list__item-artist-item">MyGO!!!!!</span>
                  <a href="/events/detail-date-live/">detail</a>
                </article>
                '''
            )
        assert url == "https://bang-dream.com/events/detail-date-live/"
        return _FakeResponse(
            '''
            <html><body>
              <dl>
                <dt>開催日</dt><dd>2026年5月20日(水)</dd>
              </dl>
            </body></html>
            '''
        )

    monkeypatch.setattr(scrape_bangdream, "http_get", fake_http_get)

    events = scrape_bangdream.scrape()

    assert [url for url, _ in calls] == [
        scrape_bangdream.BASE_URL,
        "https://bang-dream.com/events/detail-date-live/",
    ]
    assert len(events) == 1
    assert events[0]["title"] == "Detail Date Live"
    assert events[0]["date"] == "2026-05-20"
    assert events[0]["venue"] == "Ariake Arena"


def test_bangdream_does_not_fetch_external_detail_page_when_list_row_has_no_date(monkeypatch):
    captured_today = date(2026, 5, 15)
    monkeypatch.setattr(scrape_bangdream, "jst_today", lambda: captured_today)
    calls = []

    def fake_http_get(url, **kwargs):
        calls.append(url)
        if url == scrape_bangdream.BASE_URL:
            return _FakeResponse(
                '''
                <article class="p-live-event-list__item">
                  <div class="p-live-event-list__item-category"><span>ライブ</span></div>
                  <div class="p-live-event-list__item-title">External Detail Live</div>
                  <div class="p-live-event-list__item-place"><p>有明アリーナ</p></div>
                  <span class="p-live-event-list__item-artist-item">MyGO!!!!!</span>
                  <a href="https://example.invalid/events/external/">detail</a>
                </article>
                '''
            )
        raise AssertionError(f"external detail URL must not be fetched: {url}")

    monkeypatch.setattr(scrape_bangdream, "http_get", fake_http_get)

    events = scrape_bangdream.scrape()

    assert calls == [scrape_bangdream.BASE_URL]
    assert events == []
