#!/usr/bin/env python3
"""Repository-wide safety gate for gemili-skills.

Checks intentionally stay offline and deterministic:
- every Python file parses with ast;
- skill docs do not drift back to legacy Telegram-only cron delivery wording;
- Markdown docs do not expose explicit Telegram/Weixin target IDs;
- Yahoo JP docs do not claim top-picks commentCount is impossible via curl;
- Yahoo JP safe report code keeps the no-agent output contract intact.
- README / GitHub workflow skill inventories do not silently omit skills;
- recurring cron docs do not drift back to invalid ``repeat='forever'`` wording.
"""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "data", "stock-deep-analysis"}
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
    # Public docs must not expose display-name / home-channel Telegram targets either.
    # Use telegram:[REDACTED] in Markdown; keep wildcard examples such as telegram:* out of scope.
    re.compile(r"telegram:(?!\[REDACTED\])(?:-?\d{6,}|[A-Za-z][^,`'\"\n)]+)"),
    re.compile(r"weixin:[^,`'\"\s]+@im\.wechat"),
]
YAHOO_FORBIDDEN_OUTPUT_MARKERS = [
    "delegate_task",
    "default_api",
    "```python",
    "```json",
    "tool_calls",
    "browser_snapshot",
    "functions.",
    "I will",
    "The first step",
    "下一步我会",
]
REPEAT_FOREVER_MARKERS = ["repeat='forever'", 'repeat="forever"', "repeat=`forever`", "repeat=forever"]
UNREDACTED_DELIVERY_TARGET_RE = re.compile(
    r"telegram:(?!\[REDACTED\]|<display-name>|\*)(?:-?\d{6,}(?::\d+)?|[A-Za-z_\u0080-\uffff][^,`'\"\n)]+)"
    r"|weixin:[^\s,'\"`]+@im\.wechat"
)



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
        for line in text.splitlines():
            if any(marker in line for marker in REPEAT_FOREVER_MARKERS) and not any(
                safe in line for safe in ("不要", "错误", "错误示例", "do not", "invalid")
            ):
                errors.append(f"invalid repeat='forever' cron wording: {rel(path, root)}")
                break
    return errors


def check_delivery_target_leaks(paths: list[Path], root: Path) -> list[str]:
    """Reject concrete Telegram/Weixin delivery IDs in source-controlled text."""

    errors: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if UNREDACTED_DELIVERY_TARGET_RE.search(text):
            errors.append(f"unredacted explicit delivery target in source: {rel(path, root)}")
    return errors


def top_level_skills(root: Path) -> list[str]:
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and not _skip(path) and (path / "SKILL.md").exists()
    )


def check_skill_inventory(root: Path) -> list[str]:
    """Check docs/workflows mention every maintained top-level skill."""

    errors: list[str] = []
    skills = top_level_skills(root)
    readme = root / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        missing = [skill for skill in skills if skill not in text]
        if missing:
            errors.append(f"README missing skill inventory entries: {', '.join(missing)}")
        count_match = re.search(r"当前(?:常规)?维护 \*\*(\d+) 个 skill\*\*", text)
        if not count_match:
            errors.append("README skill count line missing or format drifted")
        elif int(count_match.group(1)) != len(skills):
            errors.append(f"README skill count drift: says {count_match.group(1)}, actual {len(skills)}")

    workflow_paths = [
        root / ".github" / "workflows" / "label.yml",
        root / ".github" / "workflows" / "summary.yml",
        root / ".github" / "workflows" / "pylint.yml",
    ]
    # These are source skills with scripts/tests that should not disappear from automation inventory.
    workflow_required = [skill for skill in skills if skill not in {"shared", "stock-deep-analysis", "yahoo-jp-news-scraper"}]
    for path in workflow_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        missing = [skill for skill in workflow_required if skill not in text]
        if missing:
            errors.append(f"GitHub workflow {rel(path, root)} missing skill entries: {', '.join(missing)}")
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
    leak_paths = iter_files(root, ".md") + iter_files(root, ".py") + iter_files(root, ".yml")
    errors.extend(check_delivery_target_leaks(leak_paths, root))
    errors.extend(check_yahoo_safe_report_contract(root))
    errors.extend(check_skill_inventory(root))
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
