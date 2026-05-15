import sys
from pathlib import Path
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import scrape_bangdream  # noqa: E402
import scrape_lovelive  # noqa: E402


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
    monkeypatch.setattr(scrape_lovelive, "jst_today", lambda: scrape_lovelive.date(2026, 5, 15))
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
