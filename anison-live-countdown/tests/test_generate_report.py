import json
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from generate_report import generate_markdown


def _write_events(data_dir: Path, filename: str, events: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / filename).write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")


def _event(title: str, event_date: str, franchise: str = "BanG Dream!") -> dict:
    return {
        "franchise": franchise,
        "title": title,
        "date": event_date,
        "weekday": "火",
        "venue": "Test Venue",
        "artists": ["Test Artist"],
        "category": "ライブ",
    }


def test_generate_markdown_excludes_past_events_instead_of_sending_ended_lives(tmp_path):
    _write_events(
        tmp_path,
        "bandori.json",
        [
            _event("昨天已经结束的 live", "2026-04-27"),
            _event("今天仍需提醒的 live", "2026-04-28"),
            _event("明天未来 live", "2026-04-29"),
        ],
    )

    report = generate_markdown(tmp_path, platform="telegram", today=date(2026, 4, 28))

    assert "昨天已经结束的 live" not in report
    assert "已结束" not in report
    assert "✅" not in report
    assert "今天仍需提醒的 live" in report
    assert "明天未来 live" in report


def test_generate_markdown_links_event_titles_to_original_source(tmp_path):
    event = _event("带来源链接的 live", "2026-04-29")
    event["detail_link"] = "https://example.test/live/1"
    _write_events(tmp_path, "bandori.json", [event])

    report = generate_markdown(tmp_path, platform="telegram", today=date(2026, 4, 28))

    assert "[带来源链接的 live](https://example.test/live/1)" in report


def test_generate_markdown_rejects_unsafe_event_links(tmp_path):
    event = _event("危险链接 live", "2026-04-29")
    event["detail_link"] = "javascript:alert(1)"
    _write_events(tmp_path, "bandori.json", [event])

    report = generate_markdown(tmp_path, platform="telegram", today=date(2026, 4, 28))

    assert "[危险链接 live](javascript:alert(1))" not in report
    assert "危险链接 live" in report


def test_generate_markdown_escapes_link_text_and_url(tmp_path):
    event = _event("标题 [括号] | 换行\nlive", "2026-04-29")
    event["detail_link"] = "https://example.test/live/(special)?q=a b"
    _write_events(tmp_path, "bandori.json", [event])

    report = generate_markdown(tmp_path, platform="telegram", today=date(2026, 4, 28))

    assert "[标题 \\[括号\\] ／ 换行 live](https://example.test/live/%28special%29?q=a%20b)" in report


def test_generate_markdown_rejects_malformed_or_markdown_breaking_urls(tmp_path):
    events = []
    malformed = _event("坏 host live", "2026-04-29")
    malformed["detail_link"] = "https://[bad"
    events.append(malformed)
    markdown_breaking = _event("括号 host live", "2026-04-30")
    markdown_breaking["detail_link"] = "https://ex)ample.test/path"
    events.append(markdown_breaking)
    _write_events(tmp_path, "bandori.json", events)

    report = generate_markdown(tmp_path, platform="telegram", today=date(2026, 4, 28))

    assert "[坏 host live]" not in report
    assert "[括号 host live]" not in report
    assert "坏 host live" in report
    assert "括号 host live" in report


def test_generate_markdown_returns_empty_message_when_all_events_are_past(tmp_path):
    _write_events(
        tmp_path,
        "bandori.json",
        [
            _event("昨天已经结束的 live", "2026-04-27"),
            _event("上周已经结束的 live", "2026-04-21"),
        ],
    )

    report = generate_markdown(tmp_path, platform="telegram", today=date(2026, 4, 28))

    assert "昨天已经结束的 live" not in report
    assert "上周已经结束的 live" not in report
    assert "暂无未来 live 活动数据" in report
