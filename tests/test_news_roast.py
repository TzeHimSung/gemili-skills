from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
FIVECH_SCRIPTS = ROOT / "5ch-roast" / "scripts"
YAHOO_SCRIPTS = ROOT / "yahoo-jp-roast" / "scripts"


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_5ch_fetch_falls_back_when_shift_jis_decode_produces_replacement_chars(monkeypatch):
    scraper = _load_module("fivech_scraper_under_test", FIVECH_SCRIPTS / "scraper.py")
    raw = "<html><body>こんにちは、世界</body></html>".encode("utf-8")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=raw, returncode=0)

    monkeypatch.setattr(scraper.subprocess, "run", fake_run)

    text = scraper.fetch("https://example.test/thread", encoding="shift-jis", retries=0)

    assert "こんにちは、世界" in text
    assert "�" not in text


def _fake_yahoo_html(total: int = 25) -> str:
    parts = []
    for i in range(total):
        pid = 9000 + i
        title = f"国内ニュース{i:02d}"
        parts.append(
            f'{{"id":{pid},"title":"{title}","commentCount":{1000 - i},'
            f'"articleUrl":"https:\\/\\/news.yahoo.co.jp\\/articles\\/{pid:x}"}}'
        )
    return "\n".join(parts)


def test_yahoo_roast_enforces_at_least_twenty_non_sports_items_when_top_is_too_small(monkeypatch, tmp_path):
    roast = _load_module("yahoo_roast_under_test", YAHOO_SCRIPTS / "yahoo_jp_roast.py")

    def fake_fetch_page(page, tmp_dir):
        return tmp_path / f"p{page}.html", _fake_yahoo_html(25)

    monkeypatch.setattr(roast, "_fetch_page", fake_fetch_page)

    report = roast.build_report(pages=1, top=3, include_sports=False, tmp_dir=tmp_path)

    assert report.count("💬]") == 20


def test_yahoo_roast_without_top_limit_keeps_all_non_sports_items(monkeypatch, tmp_path):
    roast = _load_module("yahoo_roast_default_top_under_test", YAHOO_SCRIPTS / "yahoo_jp_roast.py")

    def fake_fetch_page(page, tmp_dir):
        return tmp_path / f"p{page}.html", _fake_yahoo_html(25)

    monkeypatch.setattr(roast, "_fetch_page", fake_fetch_page)

    report = roast.build_report(pages=1, top=None, include_sports=False, tmp_dir=tmp_path)

    assert report.count("💬]") == 25


def test_yahoo_roast_report_header_does_not_start_with_redundant_metadata_summary(monkeypatch, tmp_path):
    roast = _load_module("yahoo_roast_header_under_test", YAHOO_SCRIPTS / "yahoo_jp_roast.py")

    def fake_fetch_page(page, tmp_dir):
        return tmp_path / f"p{page}.html", _fake_yahoo_html(21)

    monkeypatch.setattr(roast, "_fetch_page", fake_fetch_page)

    report = roast.build_report(pages=1, top=20, include_sports=False, tmp_dir=tmp_path)
    first_lines = "\n".join(report.splitlines()[:2])

    assert "筛体育" not in first_lines
    assert "篇→" not in first_lines
    assert "Top10" not in first_lines
    assert "Top20" not in first_lines


def test_yahoo_safe_report_auto_expands_until_twenty_items(monkeypatch, tmp_path):
    safe = _load_module("yahoo_safe_daily_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")
    fetched_pages = []

    def fake_fetch_page(page, tmp_dir):
        fetched_pages.append(page)
        return tmp_path / f"p{page}.html", f"page {page}"

    def fake_extract_articles(page_html, page, seen):
        count = 10 if page == 1 else 15
        items = {}
        for i in range(count):
            pid = f"{page}{i:02d}"
            seen.add(pid)
            items[pid] = {
                "pid": pid,
                "title": f"国内ニュース{pid}",
                "cc": 1000 - int(pid),
                "aurl": f"https://news.yahoo.co.jp/articles/{pid}",
                "page": page,
                "purl": f"https://news.yahoo.co.jp/pickup/{pid}",
            }
        return items

    monkeypatch.setattr(safe.base, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(safe.base, "_extract_articles", fake_extract_articles)

    items = safe.ensure_min_articles(initial_pages=1, top=20, tmp_dir=tmp_path, max_pages=3)

    assert fetched_pages == [1, 2]
    assert len(items) >= 20


def test_yahoo_safe_report_refuses_to_render_underfilled_report():
    safe = _load_module("yahoo_safe_render_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")

    try:
        safe.render_report([], top=20)
    except ValueError as exc:
        assert "requires at least 20" in str(exc)
    else:
        raise AssertionError("underfilled safe report should fail before delivery")


def test_yahoo_safe_report_main_returns_nonzero_without_printing_body_when_underfilled(monkeypatch, tmp_path, capsys):
    safe = _load_module("yahoo_safe_main_underfilled_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")

    monkeypatch.setattr(safe, "ensure_min_articles", lambda initial_pages, top, tmp_dir, max_pages: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "safe_daily_report.py",
            "--pages",
            "1",
            "--top",
            "20",
            "--max-pages",
            "1",
            "--archive-dir",
            str(tmp_path),
        ],
    )

    assert safe.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "safe report aborted" in captured.err
    assert not list(tmp_path.iterdir())
