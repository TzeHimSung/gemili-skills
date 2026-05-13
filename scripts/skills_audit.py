#!/usr/bin/env python3
"""Repository-wide safety gate for gemili-skills.

Checks intentionally stay offline and deterministic:
- every Python file parses with ast;
- skill docs do not drift back to legacy Telegram-only cron delivery wording;
- Markdown docs do not expose explicit Telegram/Weixin target IDs;
- Yahoo JP docs do not claim top-picks commentCount is impossible via curl;
- Yahoo JP safe report code keeps the no-agent output contract intact.
"""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "data"}
LEGACY_DELIVERY_MARKERS = [
    "微信/QQ deliver 暂不可用",
    "QQ/微信 deliver 管道不可用",
    "deliver='telegram:",
    'deliver="telegram:',
    "deliver=`telegram:",
]
YAHOO_OBSOLETE_MARKERS = [
    "Comment count in curl: Always 0",
    "Comment counts (e.g., `コメント245件`) are **JS-rendered** — not in curl output",
    "Only trust browser-observed counts",
]

SENSITIVE_DELIVERY_PATTERNS = [
    re.compile(r"telegram:-?\d{6,}(?::\d+)?"),
    re.compile(r"weixin:[^,`'\"\s]+@im\.wechat"),
]
YAHOO_FORBIDDEN_OUTPUT_MARKERS = [
    "delegate_task",
    "default_api",
    "```python",
    "```json",
    "tool_calls",
    "browser_snapshot",
]



def _skip(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def iter_files(root: Path, suffix: str) -> list[Path]:
    return sorted(path for path in root.rglob(f"*{suffix}") if not _skip(path))


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def check_python_syntax(paths: list[Path], root: Path) -> list[str]:
    errors: list[str] = []
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"python syntax: {rel(path, root)}:{exc.lineno}:{exc.offset}: {exc.msg}")
        except UnicodeDecodeError as exc:
            errors.append(f"python decode: {rel(path, root)}: {exc}")
    return errors


def _is_delivery_policy_doc(path: Path) -> bool:
    return "cron-multi-platform-delivery" in path.parts


def check_markdown_drift(paths: list[Path], root: Path) -> list[str]:
    errors: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if not _is_delivery_policy_doc(path):
            has_legacy_phrase = any(marker in text for marker in LEGACY_DELIVERY_MARKERS[:2])
            has_single_telegram_deliver = (
                any(marker in text for marker in LEGACY_DELIVERY_MARKERS[2:])
                and "weixin:" not in text
            )
            if has_legacy_phrase or has_single_telegram_deliver:
                errors.append(f"legacy Telegram-only delivery doc: {rel(path, root)}")
        if any(pattern.search(text) for pattern in SENSITIVE_DELIVERY_PATTERNS):
            errors.append(f"unredacted explicit delivery target in markdown: {rel(path, root)}")
        if "yahoo-jp-news-scraper" in path.parts and any(marker in text for marker in YAHOO_OBSOLETE_MARKERS):
            errors.append(f"obsolete Yahoo commentCount doc: {rel(path, root)}")
    return errors


def check_yahoo_safe_report_contract(root: Path) -> list[str]:
    errors: list[str] = []
    path = root / "yahoo-jp-roast" / "scripts" / "safe_daily_report.py"
    if not path.exists():
        return ["missing Yahoo safe daily report script"]
    text = path.read_text(encoding="utf-8")
    if "--top" not in text or "default=20" not in text:
        errors.append("Yahoo safe report must default to --top 20")
    if "ensure_min_articles" not in text:
        errors.append("Yahoo safe report must auto-expand pages or fail when fewer than top items are available")
    for marker in YAHOO_FORBIDDEN_OUTPUT_MARKERS:
        if marker not in text:
            errors.append(f"Yahoo safe report forbidden marker missing: {marker}")
    if "-roast-safe.md" not in text:
        errors.append("Yahoo safe report archive suffix drifted from -roast-safe.md")
    return errors


def run(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    errors.extend(check_python_syntax(iter_files(root, ".py"), root))
    errors.extend(check_markdown_drift(iter_files(root, ".md"), root))
    errors.extend(check_yahoo_safe_report_contract(root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline gemili-skills safety audit")
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    args = parser.parse_args()

    errors = run(Path(args.root))
    if errors:
        print("❌ skills audit failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("✅ skills audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
