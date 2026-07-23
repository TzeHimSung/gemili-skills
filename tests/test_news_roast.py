from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
from datetime import datetime, timezone
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


def test_5ch_scraper_fails_closed_when_hot_thread_list_is_empty(monkeypatch, tmp_path):
    scraper = _load_module("fivech_scraper_empty_under_test", FIVECH_SCRIPTS / "scraper.py")
    monkeypatch.setattr(scraper, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(scraper, "OUTPUT", str(tmp_path / "raw_data.json"))
    monkeypatch.setattr(scraper, "get_hot_threads", lambda n: [])

    assert scraper.main() == 1
    assert not (tmp_path / "raw_data.json").exists()


def test_5ch_filter_score_fails_closed_when_raw_data_is_missing(monkeypatch, tmp_path):
    filter_score = _load_module("fivech_filter_missing_under_test", FIVECH_SCRIPTS / "filter_score.py")
    monkeypatch.setattr(filter_score, "BASE_DIR", str(tmp_path))

    assert filter_score.main() == 1


def test_5ch_filter_score_fails_closed_when_all_threads_are_filtered(monkeypatch, tmp_path):
    filter_score = _load_module("fivech_filter_empty_under_test", FIVECH_SCRIPTS / "filter_score.py")
    report_dir = tmp_path / "2099-01-01"
    report_dir.mkdir()
    (report_dir / "raw_data.json").write_text(
        '{"threads":[{"board":"VIP","title":"短い","comments":[],"comment_count":0}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(filter_score, "BASE_DIR", str(tmp_path))

    assert filter_score.main() == 1
    assert not (report_dir / "scored.json").exists()


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


def test_yahoo_safe_report_refuses_to_render_item_without_original_url():
    safe = _load_module("yahoo_safe_missing_aurl_render_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")
    items = [
        {
            "pid": "9001",
            "title": "国内ニュース",
            "cc": 100,
            "purl": "https://news.yahoo.co.jp/pickup/9001",
        }
    ]

    try:
        safe.render_report(items, top=1)
    except ValueError as exc:
        assert "original article URL" in str(exc)
    else:
        raise AssertionError("safe report should reject published items without original article URL")


def test_yahoo_safe_report_refuses_none_or_malformed_original_url():
    safe = _load_module("yahoo_safe_bad_aurl_render_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")

    for bad_aurl in [None, "", "not a url", "https://example.com/not-yahoo-article"]:
        items = [
            {
                "pid": "9001",
                "title": "国内ニュース",
                "cc": 100,
                "purl": "https://news.yahoo.co.jp/pickup/9001",
                "aurl": bad_aurl,
            }
        ]
        try:
            safe.render_report(items, top=1)
        except ValueError as exc:
            assert "original article URL" in str(exc)
        else:
            raise AssertionError(f"safe report should reject malformed original article URL: {bad_aurl!r}")


def test_yahoo_safe_report_filters_missing_original_urls_and_keeps_expanding(monkeypatch, tmp_path):
    safe = _load_module("yahoo_safe_missing_aurl_expand_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")
    fetched_pages = []

    def fake_fetch_page(page, tmp_dir):
        fetched_pages.append(page)
        return tmp_path / f"p{page}.html", f"page {page}"

    def fake_extract_articles(page_html, page, seen):
        if page == 1:
            items = {
                "missing": {
                    "pid": "missing",
                    "title": "原文なしニュース",
                    "cc": 1000,
                    "aurl": "",
                    "page": page,
                    "purl": "https://news.yahoo.co.jp/pickup/missing",
                },
                "valid1": {
                    "pid": "valid1",
                    "title": "原文ありニュース1",
                    "cc": 900,
                    "aurl": "https://news.yahoo.co.jp/articles/valid1",
                    "page": page,
                    "purl": "https://news.yahoo.co.jp/pickup/valid1",
                },
            }
        else:
            items = {
                "valid2": {
                    "pid": "valid2",
                    "title": "原文ありニュース2",
                    "cc": 800,
                    "aurl": "https://news.yahoo.co.jp/articles/valid2",
                    "page": page,
                    "purl": "https://news.yahoo.co.jp/pickup/valid2",
                }
            }
        seen.update(items)
        return items

    monkeypatch.setattr(safe.base, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(safe.base, "_extract_articles", fake_extract_articles)

    items = safe.ensure_min_articles(initial_pages=1, top=2, tmp_dir=tmp_path, max_pages=2)

    assert fetched_pages == [1, 2]
    assert [item["pid"] for item in items[:2]] == ["valid1", "valid2"]
    assert all(item.get("aurl") for item in items[:2])


def test_yahoo_safe_report_date_helpers_use_jst_not_local_timezone():
    safe = _load_module("yahoo_safe_jst_helpers_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")
    utc_dt = datetime(2026, 5, 18, 15, 30, tzinfo=timezone.utc)

    assert safe.jst_date_key(utc_dt) == "2026-05-19"
    assert safe.jst_now_label(utc_dt) == "2026-05-19 00:30"


def test_yahoo_full_legacy_script_is_import_safe_and_debug_only():
    yahoo_full = _load_module("yahoo_full_legacy_under_test", YAHOO_SCRIPTS / "yahoo_full.py")

    assert yahoo_full.DEBUG_ONLY is True
    assert callable(yahoo_full.main)


def test_yahoo_safe_report_generates_item_specific_commentary():
    safe = _load_module("yahoo_safe_variety_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")
    titles = [
        "栃木で住宅強盗事件 女性が死亡",
        "女性殴られ死亡 強盗殺人疑い逮捕",
        "枝野氏 武器輸出解禁は国益損なう",
        "消えたナフサ由来商品 困惑する客",
        "児童の机逆向きに 授業参加させず",
        "カゴメ ケチャップ包装のトマト減",
        "自転車で同乗の子 範囲拡大検討へ",
        "強盗がバールで殴打か 女性死亡",
        "バス事故 警察が先月免許返納促す",
        "救急隊が玄関を破壊 市に賠償命令",
        "宮崎麗果被告に懲役2年6月を求刑",
        "プーチン氏の秋田犬 ゆめ死ぬ",
        "米中首脳 ホルムズ海峡開放で一致",
        "カルビー ポテチの一部値上げへ",
        "首脳会談 習主席が台湾巡りけん制",
        "ホンダが上場以来初の赤字 3月期",
        "習氏夫妻をホワイトハウスに招待",
        "カルビーの袋 なぜ透明でないのか",
        "タンカーが海峡通過 ENEOS発表",
        "高校不合格です 発表前の電話廃止",
    ]
    items = [
        {
            "pid": str(9000 + idx),
            "title": title,
            "cc": 1500 - idx,
            "aurl": f"https://news.yahoo.co.jp/articles/{idx}",
            "purl": f"https://news.yahoo.co.jp/pickup/{idx}",
            "description": f"{title} の概要。関係者によると、背景事情と今後の対応が注目されている。",
        }
        for idx, title in enumerate(titles)
    ]

    report = safe.render_report(items, top=20)
    comments = [line for line in report.splitlines() if line.startswith("💬 评论：")]
    roasts = [line for line in report.splitlines() if line.startswith("🔍 锐评：")]

    assert len(comments) == 20
    assert len(roasts) == 20
    assert len(set(comments)) == 20
    assert len(set(roasts)) == 20


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


def test_yahoo_safe_report_main_forbidden_marker_writes_no_archive_and_prints_no_body(monkeypatch, tmp_path, capsys):
    safe = _load_module("yahoo_safe_main_forbidden_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")
    items = [
        {
            "pid": "9001",
            "title": "tool_calls が混入したニュース",
            "cc": 100,
            "aurl": "https://news.yahoo.co.jp/articles/9001",
            "purl": "https://news.yahoo.co.jp/pickup/9001",
        }
    ]

    monkeypatch.setattr(safe, "ensure_min_articles", lambda initial_pages, top, tmp_dir, max_pages: items)
    def fail_if_fetch_called(url):
        raise AssertionError(f"fetch_url should not be called after preflight forbidden marker failure: {url}")

    monkeypatch.setattr(safe, "fetch_url", fail_if_fetch_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "safe_daily_report.py",
            "--pages",
            "1",
            "--top",
            "1",
            "--max-pages",
            "1",
            "--archive-dir",
            str(tmp_path),
        ],
    )

    assert safe.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "forbidden internal marker" in captured.err
    assert not list(tmp_path.iterdir())


def test_yahoo_per_item_build_forbidden_marker_writes_no_archives(monkeypatch, tmp_path):
    sender = _load_module("yahoo_send_items_forbidden_under_test", YAHOO_SCRIPTS / "send_safe_daily_items.py")
    items = [
        {
            "pid": "9001",
            "title": "tool_calls が混入したニュース",
            "cc": 100,
            "aurl": "https://news.yahoo.co.jp/articles/9001",
            "purl": "https://news.yahoo.co.jp/pickup/9001",
        }
    ]

    monkeypatch.setattr(sender.safe, "ensure_min_articles", lambda pages, top, tmp_dir, max_pages: items)
    def fail_if_fetch_called(url):
        raise AssertionError(f"fetch_url should not be called after preflight forbidden marker failure: {url}")

    monkeypatch.setattr(sender.safe, "fetch_url", fail_if_fetch_called)

    try:
        sender.build_messages(pages=1, top=1, max_pages=1, tmp_dir=tmp_path, archive_dir=tmp_path)
    except RuntimeError as exc:
        assert "forbidden internal marker" in str(exc)
    else:
        raise AssertionError("per-item build should reject forbidden markers before archiving")

    assert not list(tmp_path.iterdir())


def test_yahoo_per_item_main_forbidden_marker_writes_no_archives_and_sends_nothing(monkeypatch, tmp_path, capsys):
    sender = _load_module("yahoo_send_items_main_forbidden_under_test", YAHOO_SCRIPTS / "send_safe_daily_items.py")
    items = [
        {
            "pid": "9001",
            "title": "tool_calls が混入したニュース",
            "cc": 100,
            "aurl": "https://news.yahoo.co.jp/articles/9001",
            "purl": "https://news.yahoo.co.jp/pickup/9001",
        }
    ]
    send_calls = []

    monkeypatch.setattr(sender.safe, "ensure_min_articles", lambda pages, top, tmp_dir, max_pages: items)
    monkeypatch.setattr(sender.safe, "fetch_url", lambda url: "")
    monkeypatch.setattr(sender, "_send_one", lambda target, message: send_calls.append((target, message)))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_safe_daily_items.py",
            "--pages",
            "1",
            "--top",
            "1",
            "--max-pages",
            "1",
            "--archive-dir",
            str(tmp_path),
            "--dry-run",
        ],
    )

    assert sender.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "forbidden internal marker" in captured.err
    assert send_calls == []
    assert not list(tmp_path.iterdir())


def test_yahoo_weixin_digest_contains_twenty_titles_and_three_roasts():
    sender = _load_module("yahoo_send_items_digest_under_test", YAHOO_SCRIPTS / "send_safe_daily_items.py")
    messages = [
        "\n".join(
            [
                "# Yahoo JP 热榜中文锐评日报",
                f"第 {idx}/20 条",
                "",
                f"## #{idx} 新闻标题 {idx} — {100 - idx}💬",
                f"🔍 锐评：第 {idx} 条锐评内容",
            ]
        )
        for idx in range(1, 21)
    ]

    digest = sender.render_weixin_digest(messages, max_chars=1800, roast_count=3)

    assert len(digest) <= 1800
    assert sum(1 for line in digest.splitlines() if line[:1].isdigit() and ". " in line) == 20
    assert digest.count("锐评：") == 3
    assert "新闻标题 20" in digest
    assert "第 1 条锐评内容" in digest
    assert "第 2 条锐评内容" in digest
    assert "第 3 条锐评内容" in digest
    assert "第 4 条锐评内容" not in digest
    assert "http" not in digest


def test_yahoo_main_passes_full_telegram_and_one_weixin_digest(monkeypatch, tmp_path, capsys):
    sender = _load_module("yahoo_send_items_delivery_under_test", YAHOO_SCRIPTS / "send_safe_daily_items.py")
    messages = [f"message {idx}" for idx in range(1, 21)]
    captured = {}

    class Result:
        ok = True
        sent = {"telegram": 20, "weixin": 1}
        errors = {}

    monkeypatch.setattr(sender, "build_messages", lambda *args: messages)
    monkeypatch.setattr(sender, "render_weixin_digest", lambda *args, **kwargs: "compact digest")
    monkeypatch.setattr(sender, "_load_targets", lambda: ["telegram:123", "weixin:abc"])

    def fake_deliver(**kwargs):
        captured.update(kwargs)
        return Result()

    monkeypatch.setattr(sender, "deliver_rate_safe", fake_deliver)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_safe_daily_items.py",
            "--pages",
            "1",
            "--top",
            "20",
            "--archive-dir",
            str(tmp_path),
            "--item-delay",
            "0",
        ],
    )

    assert sender.main() == 0
    assert captured["telegram_messages"] == messages
    assert captured["weixin_message"] == "compact digest"
    assert captured["targets"].telegram == "telegram:123"
    assert captured["targets"].weixin == "weixin:abc"
    assert capsys.readouterr().out == ""


def test_yahoo_per_item_delivery_sends_all_telegram_before_weixin_rate_limit(monkeypatch, tmp_path):
    sender = _load_module("yahoo_send_items_order_under_test", YAHOO_SCRIPTS / "send_safe_daily_items.py")
    messages = [f"message {idx}" for idx in range(1, 21)]
    calls = []

    monkeypatch.setattr(sender, "build_messages", lambda *args: messages)
    monkeypatch.setattr(sender, "render_weixin_digest", lambda *args, **kwargs: "compact digest")
    monkeypatch.setattr(sender, "_load_targets", lambda: ["telegram:123", "weixin:abc"])
    monkeypatch.setattr(sender, "HERMES_HOME", tmp_path)
    monkeypatch.delenv("WEIXIN_RATE_LIMIT_RETRIES", raising=False)

    def fake_send_one(target, message):
        calls.append((target, message))
        if target.startswith("weixin:"):
            raise RuntimeError("iLink sendmessage rate limited after 0 retry(s): ret=-2 errmsg=rate limited")
        return {"success": True}

    monkeypatch.setattr(sender, "_send_one", fake_send_one)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_safe_daily_items.py",
            "--pages",
            "1",
            "--top",
            "20",
            "--archive-dir",
            str(tmp_path),
            "--item-delay",
            "0",
            "--min-weixin-interval",
            "0",
        ],
    )

    assert sender.main() == 1
    assert [call for call in calls if call[0] == "telegram:123"] == [("telegram:123", message) for message in messages]
    assert [call for call in calls if call[0] == "weixin:abc"] == [
        ("weixin:abc", "compact digest")
    ]
    assert sender.os.environ["WEIXIN_RATE_LIMIT_RETRIES"] == "0"


def test_yahoo_per_item_delivery_runs_platforms_concurrently(monkeypatch, tmp_path):
    sender = _load_module("yahoo_send_items_concurrent_under_test", YAHOO_SCRIPTS / "send_safe_daily_items.py")
    messages = [f"message {idx}" for idx in range(1, 21)]
    telegram_started = threading.Event()
    allow_telegram_to_continue = threading.Event()
    weixin_started = threading.Event()
    release_weixin = threading.Event()
    telegram_done = threading.Event()
    result = []

    monkeypatch.setattr(sender, "build_messages", lambda *args: messages)
    monkeypatch.setattr(sender, "render_weixin_digest", lambda *args, **kwargs: "compact digest")
    monkeypatch.setattr(sender, "_load_targets", lambda: ["telegram:123", "weixin:abc"])
    monkeypatch.setattr(sender, "HERMES_HOME", tmp_path)
    monkeypatch.delenv("WEIXIN_RATE_LIMIT_RETRIES", raising=False)

    def fake_send_one(target, message):
        if target == "telegram:123":
            if message == messages[0]:
                telegram_started.set()
                assert allow_telegram_to_continue.wait(timeout=2), "test timed out waiting to release blocked Telegram send"
            if message == messages[-1]:
                telegram_done.set()
            return {"success": True}
        if target == "weixin:abc":
            weixin_started.set()
            assert release_weixin.wait(timeout=2), "test timed out waiting to release blocked Weixin send"
            raise RuntimeError("iLink sendmessage rate limited after 0 retry(s): ret=-2 errmsg=rate limited")
        raise AssertionError(f"unexpected target: {target}")

    monkeypatch.setattr(sender, "_send_one", fake_send_one)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "send_safe_daily_items.py",
            "--pages",
            "1",
            "--top",
            "20",
            "--archive-dir",
            str(tmp_path),
            "--item-delay",
            "0",
            "--min-weixin-interval",
            "0",
        ],
    )

    worker = threading.Thread(target=lambda: result.append(sender.main()))
    worker.start()
    try:
        assert telegram_started.wait(timeout=1)
        assert weixin_started.wait(timeout=1), "Weixin worker should start while Telegram is blocked"
        allow_telegram_to_continue.set()
        assert telegram_done.wait(timeout=1), "Telegram should finish while Weixin is blocked"
        release_weixin.set()
    finally:
        allow_telegram_to_continue.set()
        release_weixin.set()
        worker.join(timeout=2)

    assert result == [1]


def test_yahoo_sports_filter_is_shared_between_manual_and_safe_reports():
    roast = _load_module("yahoo_roast_rules_under_test", YAHOO_SCRIPTS / "yahoo_jp_roast.py")
    safe = _load_module("yahoo_safe_rules_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")

    for title in ["大谷が本塁打", "巨人の投手が炎上", "山本由伸がドジャース戦で好投"]:
        assert roast._is_sports(title) is True
        assert safe.is_sports(title) is True
    assert roast._is_sports("東方神起ライブ発表") is False
    assert safe.is_sports("東方神起ライブ発表") is False


def test_yahoo_safe_dedupe_preserves_all_pickup_urls_when_higher_comment_item_replaces_old_one():
    safe = _load_module("yahoo_safe_dedupe_under_test", YAHOO_SCRIPTS / "safe_daily_report.py")
    items = [
        {"pid": "1", "title": "低コメント", "cc": 1, "aurl": "https://news.yahoo.co.jp/articles/abc?utm=1", "purl": "https://news.yahoo.co.jp/pickup/1"},
        {"pid": "2", "title": "高コメント", "cc": 2, "aurl": "https://news.yahoo.co.jp/articles/abc?utm=2", "purl": "https://news.yahoo.co.jp/pickup/2"},
    ]

    deduped = safe.dedupe_by_article(items)

    assert len(deduped) == 1
    assert deduped[0]["title"] == "高コメント"
    assert deduped[0]["pickup_urls"] == ["https://news.yahoo.co.jp/pickup/1", "https://news.yahoo.co.jp/pickup/2"]


def test_5ch_gen_report_rejects_skeleton_by_default_and_allows_it_explicitly(tmp_path):
    scored = tmp_path / "scored.json"
    scored.write_text(
        '{"candidates":[{"title":"t","board":"VIP","url":"https://example.test","comment_count":10,"_score":5,"comments":[{"text":"コメント","uid":"u"}]}]}',
        encoding="utf-8",
    )
    out = tmp_path / "report.md"

    default = subprocess.run(
        [sys.executable, str(FIVECH_SCRIPTS / "gen_report.py"), "--scored", str(scored), "--output", str(out), "--top", "1"],
        capture_output=True,
        text=True,
        check=False,
    )
    allowed = subprocess.run(
        [
            sys.executable,
            str(FIVECH_SCRIPTS / "gen_report.py"),
            "--scored",
            str(scored),
            "--output",
            str(out),
            "--top",
            "1",
            "--allow-skeleton",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert default.returncode != 0
    assert "--allow-skeleton" in default.stderr
    assert allowed.returncode == 0
    assert "AI 锐评待补" in out.read_text(encoding="utf-8")


def test_5ch_gen_report_rejects_partial_report_by_default(tmp_path):
    scored = tmp_path / "scored.json"
    scored.write_text(
        '{"candidates":[{"title":"t","board":"VIP","url":"https://example.test","comment_count":10,"_score":5,"_cn_title":"中译","_ai_commentary":"锐评","comments":[]}]}',
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(FIVECH_SCRIPTS / "gen_report.py"), "--scored", str(scored), "--top", "2"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--allow-partial" in result.stderr
