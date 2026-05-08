from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "skills_audit.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("skills_audit_under_test", AUDIT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["skills_audit_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_audit_detects_python_syntax_errors(tmp_path):
    audit = _load_audit()
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n", encoding="utf-8")

    errors = audit.check_python_syntax([bad], tmp_path)

    assert errors
    assert "bad.py" in errors[0]


def test_audit_rejects_legacy_telegram_only_delivery_docs(tmp_path):
    audit = _load_audit()
    doc = tmp_path / "README.md"
    doc.write_text("内容任务强制 `deliver='telegram:123'`，微信/QQ deliver 暂不可用。", encoding="utf-8")

    errors = audit.check_markdown_drift([doc], tmp_path)

    assert any("legacy Telegram-only" in error for error in errors)


def test_audit_rejects_obsolete_yahoo_comment_count_claim(tmp_path):
    audit = _load_audit()
    doc = tmp_path / "yahoo-jp-news-scraper" / "SKILL.md"
    doc.parent.mkdir()
    doc.write_text("Comment count in curl: Always 0 — JS-rendered", encoding="utf-8")

    errors = audit.check_markdown_drift([doc], tmp_path)

    assert any("obsolete Yahoo commentCount" in error for error in errors)
