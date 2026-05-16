#!/usr/bin/env python3
# pylint: disable=import-error,wrong-import-position,import-outside-toplevel
"""Generate Yahoo JP safe daily report and deliver each news item separately.

Normal mode is cron-friendly: messages are delivered via Hermes messaging
adapters and stdout stays empty, so the no_agent cron job itself remains silent
on success. Use --dry-run for validation without sending.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import safe_daily_report as safe  # noqa: E402  # pylint: disable=wrong-import-position

HERMES_HOME = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
HERMES_AGENT_DIR = HERMES_HOME / "hermes-agent"
SECRETS_PATH = HERMES_HOME / "secrets" / "cron_delivery_targets.json"
DEFAULT_ARCHIVE_DIR = HERMES_HOME / "yahoo-reports"

FORBIDDEN_MARKERS = [
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


def _load_env() -> None:
    """Load ~/.hermes/.env for standalone cron script delivery."""
    env_path = HERMES_HOME / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

        load_dotenv(str(env_path), override=True, encoding="utf-8")
        return
    except Exception:
        pass

    # Tiny fallback parser: enough for KEY=VALUE lines used by Hermes .env.
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_targets() -> list[str]:
    explicit = os.getenv("HERMES_YAHOO_PER_ITEM_TARGETS", "").strip()
    if explicit:
        return [part.strip() for part in explicit.split(",") if part.strip()]

    data: dict[str, Any] = {}
    if SECRETS_PATH.exists():
        data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))

    telegram_chat_id = str(
        os.getenv("HERMES_DELIVERY_TELEGRAM_CHAT_ID")
        or data.get("telegram_chat_id")
        or ""
    ).strip()
    weixin_chat_id = str(
        os.getenv("HERMES_DELIVERY_WEIXIN_CHAT_ID")
        or data.get("weixin_chat_id")
        or ""
    ).strip()

    targets: list[str] = []
    if telegram_chat_id:
        targets.append(f"telegram:{telegram_chat_id}")
    if weixin_chat_id:
        targets.append(f"weixin:{weixin_chat_id}")
    return targets


def _comment_url(article_url: str) -> str:
    return safe.comment_url(article_url)


def render_item_message(item: dict[str, Any], idx: int, total: int, now_label: str) -> str:
    """Render exactly one user-facing news item as one standalone message."""
    pickup_urls = item.get("pickup_urls") or [item["purl"]]
    desc = item.get("description", "")
    c_url = _comment_url(item.get("aurl", ""))

    lines: list[str] = [
        f"# Yahoo JP 热榜中文锐评日报（{now_label} JST）",
        f"第 {idx}/{total} 条",
        "",
        f"## #{idx} {item['title']} — {item['cc']}💬",
        "原始链接：",
    ]
    for purl in pickup_urls[:3]:
        lines.append(f"- Pickup: {purl}")
    if item.get("aurl"):
        lines.append(f"- 原文: {item['aurl']}")
    if c_url:
        lines.append(f"- 评论: {c_url}")
    lines.append("")
    if desc:
        lines.append(f"📝 正文：Yahoo 摘要显示：{desc}")
    else:
        lines.append("📝 正文：已取得热榜标题和原始链接；原文摘要抓取为空，详细内容以原文为准。")
    lines.append(f"💬 评论：{safe.zh_comment_angle(item)}")
    lines.append(f"🔍 锐评：{safe.zh_roast(item)}")
    return "\n".join(lines).rstrip() + "\n"


def _assert_clean_messages(messages: list[str]) -> None:
    for idx, message in enumerate(messages, 1):
        bad = [marker for marker in FORBIDDEN_MARKERS if marker in message]
        if bad:
            raise RuntimeError(f"message #{idx} contains forbidden internal marker(s): {bad}")


def _send_one(target: str, message: str) -> dict[str, Any]:
    if str(HERMES_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(HERMES_AGENT_DIR))
    from tools.send_message_tool import _handle_send  # noqa: WPS433  # pylint: disable=import-error,import-outside-toplevel

    raw = _handle_send({"target": target, "message": message})
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"send_message returned non-JSON for {target}: {raw[:300]}")
    if result.get("error"):
        raise RuntimeError(f"send_message failed for {target}: {result['error']}")
    if not result.get("success"):
        raise RuntimeError(f"send_message did not report success for {target}: {result}")
    return result


def _archive_messages(messages: list[str], archive_dir: Path) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    date_key = datetime.now().strftime("%Y-%m-%d")
    bundle = "\n---\n\n".join(messages).rstrip() + "\n"
    (archive_dir / f"{date_key}-roast-safe-per-item.md").write_text(bundle, encoding="utf-8")
    (archive_dir / f"{date_key}-roast-safe-per-item.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_messages(pages: int, top: int, max_pages: int, tmp_dir: Path, archive_dir: Path) -> list[str]:
    items = safe.ensure_min_articles(pages, top, tmp_dir, max_pages)
    if len(items) < top:
        raise RuntimeError(
            f"Yahoo JP safe report aborted: only {len(items)} non-sports items after {max_pages} page(s); required {top}"
        )

    for item in items[:top]:
        page_html = safe.fetch_url(item["purl"])
        item["description"] = safe.extract_meta_description(page_html)

    # Keep the original aggregate archive for auditing/backward compatibility.
    report = safe.render_report(items, top)
    archive_dir.mkdir(parents=True, exist_ok=True)
    aggregate_path = archive_dir / f"{datetime.now().strftime('%Y-%m-%d')}-roast-safe.md"
    aggregate_path.write_text(report, encoding="utf-8")

    now_label = datetime.now().strftime("%Y-%m-%d %H:%M")
    messages = [render_item_message(item, idx, top, now_label) for idx, item in enumerate(items[:top], 1)]
    _assert_clean_messages(messages)
    _archive_messages(messages, archive_dir)
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Yahoo JP safe daily report as one message per news item")
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--tmp-dir", default="/tmp")
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR))
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate messages without sending")
    parser.add_argument("--limit", type=int, default=0, help="Debug/dry-run only: cap number of messages")
    parser.add_argument("--target-delay", type=float, default=float(os.getenv("HERMES_YAHOO_TARGET_DELAY_SECONDS", "0.5")))
    parser.add_argument("--item-delay", type=float, default=float(os.getenv("HERMES_YAHOO_ITEM_DELAY_SECONDS", "2.0")))
    args = parser.parse_args()

    if args.pages < 1 or args.top < 1 or args.max_pages < args.pages:
        parser.error("require --pages>=1, --top>=1, and --max-pages>=--pages")
    if not args.dry_run and args.top != 20:
        parser.error("live cron delivery must send exactly 20 Yahoo JP news items; use --dry-run for other counts")
    if args.limit and args.limit > 0 and not args.dry_run:
        parser.error("--limit is dry-run/debug only; live cron delivery must send all generated items")

    _load_env()
    tmp_dir = Path(args.tmp_dir).expanduser()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = Path(args.archive_dir).expanduser()
    messages = build_messages(args.pages, args.top, args.max_pages, tmp_dir, archive_dir)

    if args.dry_run:
        preview_messages = messages[: args.limit] if args.limit and args.limit > 0 else messages
        print(f"DRY_RUN generated={len(messages)} preview={len(preview_messages)}")
        for idx, message in enumerate(preview_messages, 1):
            print(f"--- message {idx} chars={len(message)} ---")
            print(message[:500].rstrip())
        return 0

    targets = _load_targets()
    invalid = [target for target in targets if target.split(":", 1)[0] not in {"telegram", "weixin"}]
    if invalid:
        raise RuntimeError(
            "Yahoo per-item delivery targets must be telegram:* or weixin:* only; "
            f"invalid target(s): {', '.join(target.split(':', 1)[0] for target in invalid)}"
        )
    schemes = {target.split(":", 1)[0] for target in targets if ":" in target}
    missing = {"telegram", "weixin"} - schemes
    if missing:
        raise RuntimeError(
            "Yahoo per-item delivery requires both Telegram and Weixin targets; "
            f"missing: {', '.join(sorted(missing))}"
        )

    failures: list[str] = []
    sent = 0
    for idx, message in enumerate(messages, 1):
        for target in targets:
            try:
                _send_one(target, message)
                sent += 1
                print(f"sent item {idx}/{len(messages)} to {target.split(':', 1)[0]}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001 - aggregate all platform failures
                failures.append(f"item {idx} -> {target}: {exc}")
            if args.target_delay > 0:
                time.sleep(args.target_delay)
        if idx < len(messages) and args.item_delay > 0:
            time.sleep(args.item_delay)

    if failures:
        print(f"Yahoo JP per-item delivery partially failed after {sent} successful sends", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Yahoo JP per-item delivery sent {len(messages)} item(s) to {len(targets)} target(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
