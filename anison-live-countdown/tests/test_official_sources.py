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
