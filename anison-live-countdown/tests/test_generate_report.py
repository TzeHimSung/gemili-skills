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
