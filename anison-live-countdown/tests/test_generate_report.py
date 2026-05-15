import json
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import common
import generate_report
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


def test_generate_markdown_defaults_to_common_jst_today_not_local_date_today(tmp_path, monkeypatch):
    _write_events(tmp_path, "bandori.json", [_event("JST 今天的 live", "2026-04-28")])

    monkeypatch.setattr(common, "jst_today", lambda: date(2026, 4, 28))

    class LocalDateShouldNotBeUsed:
        @classmethod
        def today(cls):
            raise AssertionError("generate_markdown must use common.jst_today()")

    monkeypatch.setattr(generate_report, "date", LocalDateShouldNotBeUsed)

    report = generate_markdown(tmp_path, platform="general")

    assert "Anison Live 倒计时 — 4月28日" in report
    assert "JST 今天的 live" in report


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


def test_general_markdown_uses_paginated_tables_for_all_franchises(tmp_path):
    base = date(2026, 4, 29)
    bd_events = [
        _event(f"BanG Dream live {idx}", (base + timedelta(days=idx)).isoformat())
        for idx in range(21)
    ]
    ll_events = [
        _event(f"LoveLive live {idx}", (base + timedelta(days=idx)).isoformat(), "LoveLive!")
        for idx in range(21)
    ]
    bd_events[0]["detail_link"] = "https://example.test/live/1"
    _write_events(tmp_path, "bandori.json", bd_events)
    _write_events(tmp_path, "lovelive.json", ll_events)

    report = generate_markdown(tmp_path, platform="general", today=date(2026, 4, 28))

    def data_row_count(section: str) -> int:
        return sum(
            1 for line in section.splitlines()
            if line.startswith("| ") and not line.startswith("| 倒计时 ")
        )

    bd_page1 = report.split("### 🎸 BanG Dream!（第1/2页）", 1)[1].split("### 🎸 BanG Dream!（第2/2页）", 1)[0]
    bd_page2 = report.split("### 🎸 BanG Dream!（第2/2页）", 1)[1].split("*BanG Dream! 未来活动", 1)[0]
    ll_page1 = report.split("### 🎤 LoveLive!（第1/2页）", 1)[1].split("### 🎤 LoveLive!（第2/2页）", 1)[0]
    ll_page2 = report.split("### 🎤 LoveLive!（第2/2页）", 1)[1].split("*LoveLive! 未来活动", 1)[0]

    assert data_row_count(bd_page1) == 20
    assert data_row_count(bd_page2) == 1
    assert data_row_count(ll_page1) == 20
    assert data_row_count(ll_page2) == 1
    assert "| 倒计时 | 日期 | 活动 | 艺人 | 场地 |" in report
    assert "| **🔴 剩1天** | 4月29日 | [BanG Dream live 0](https://example.test/live/1) | Test Artist | Test Venue |" in report


def test_telegram_markdown_keeps_table_layout(tmp_path):
    _write_events(tmp_path, "bandori.json", [_event("表格 live", "2026-04-29")])

    report = generate_markdown(tmp_path, platform="telegram", today=date(2026, 4, 28))

    assert "| 倒计时 | 日期 | 活动 | 艺人 | 场地 |" in report
    assert "| **🔴 剩1天** | 4月29日 | 表格 live | Test Artist | Test Venue |" in report


def test_generate_markdown_ignores_idolmaster_even_when_stale_json_exists(tmp_path):
    _write_events(tmp_path, "bandori.json", [_event("BanG Dream live", "2026-04-29")])
    _write_events(tmp_path, "lovelive.json", [_event("LoveLive live", "2026-04-30", "LoveLive!")])
    _write_events(
        tmp_path,
        "idolmaster.json",
        [_event("不再展示的偶像大师 live", "2026-05-01", "アイドルマスター")],
    )

    report = generate_markdown(tmp_path, platform="general", today=date(2026, 4, 28))

    assert "BanG Dream live" in report
    assert "LoveLive live" in report
    assert "アイドルマスター" not in report
    assert "不再展示的偶像大师 live" not in report


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
