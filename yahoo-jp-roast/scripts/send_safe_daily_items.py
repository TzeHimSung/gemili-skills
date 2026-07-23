#!/usr/bin/env python3
# pylint: disable=import-error,wrong-import-position,import-outside-toplevel
"""Generate Yahoo JP safe daily report and deliver it to Telegram and Weixin.

Telegram receives all 20 full items. Weixin receives one bounded digest with
20 titles and three high-heat roasts. Normal mode keeps stdout empty so the
no-agent cron scheduler cannot deliver a duplicate.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import safe_daily_report as safe  # noqa: E402  # pylint: disable=wrong-import-position

HERMES_HOME = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
HERMES_AGENT_DIR = HERMES_HOME / "hermes-agent"
SECRETS_PATH = HERMES_HOME / "secrets" / "cron_delivery_targets.json"
DEFAULT_ARCHIVE_DIR = HERMES_HOME / "yahoo-reports"

for shared_scripts in (
    SCRIPT_DIR.parents[1] / "shared" / "scripts",
    SCRIPT_DIR.parents[2] / "shared" / "scripts",
    HERMES_HOME / "skills" / "shared" / "scripts",
):
    if shared_scripts.exists() and str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))

from cron_rate_safe_delivery import (  # noqa: E402  # pylint: disable=wrong-import-position
    DEFAULT_MAX_WEIXIN_CHARS,
    DEFAULT_MIN_WEIXIN_INTERVAL,
    DeliveryTargets,
    deliver_rate_safe,
)


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
    safe.require_original_article_urls([item], 1)
    pickup_urls = item.get("pickup_urls") or [item["purl"]]
    aurl = safe.original_article_url(item)
    desc = item.get("description", "")
    c_url = _comment_url(aurl)

    lines: list[str] = [
        f"# Yahoo JP 热榜中文锐评日报（{now_label} JST）",
        f"第 {idx}/{total} 条",
        "",
        f"## #{idx} {item['title']} — {item['cc']}💬",
        "原始链接：",
    ]
    for purl in pickup_urls[:3]:
        lines.append(f"- Pickup: {purl}")
    lines.append(f"- 原文: {aurl}")
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
    safe.assert_no_forbidden_markers(messages)


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


def _clip(text: str, max_chars: int) -> str:
    value = " ".join(text.split())
    if len(value) <= max_chars:
        return value
    return value[: max(1, max_chars - 1)].rstrip() + "\u2026"


def _digest_item(message: str, fallback_index: int) -> dict[str, Any]:
    title_line = next(
        (line.strip() for line in message.splitlines() if line.startswith("## #")),
        "",
    )
    title_match = re.match(r"^## #(\d+)\s+(.+)$", title_line)
    if title_match:
        index = int(title_match.group(1))
        title_and_heat = title_match.group(2).strip()
    else:
        index = fallback_index
        title_and_heat = f"\u65b0\u95fb {fallback_index}"

    heat_match = re.search(r"(\d+)\U0001f4ac", title_and_heat)
    heat = int(heat_match.group(1)) if heat_match else 0
    roast_label = "\u9510\u8bc4\uff1a"
    roast = ""
    for line in message.splitlines():
        if roast_label in line:
            roast = line.split(roast_label, 1)[1].strip()
            break
    return {
        "index": index,
        "title_and_heat": title_and_heat,
        "heat": heat,
        "roast": roast or "\u6682\u65e0\u9510\u8bc4",
    }


def render_weixin_digest(
    messages: list[str],
    *,
    max_chars: int = DEFAULT_MAX_WEIXIN_CHARS,
    roast_count: int = 3,
) -> str:
    """Render one URL-free digest while retaining all ranked titles."""
    if max_chars < 1 or max_chars > DEFAULT_MAX_WEIXIN_CHARS:
        raise ValueError(
            f"weixin max_chars must be between 1 and {DEFAULT_MAX_WEIXIN_CHARS}"
        )
    if roast_count < 0:
        raise ValueError("roast_count must not be negative")

    items = [_digest_item(message, index) for index, message in enumerate(messages, 1)]
    lines = ["# Yahoo JP \u70ed\u699c\u6458\u8981", ""]
    for item in items:
        lines.append(
            f"{item['index']}. {_clip(str(item['title_and_heat']), 52)}"
        )

    hottest = sorted(
        items,
        key=lambda item: (-int(item["heat"]), int(item["index"])),
    )[:roast_count]
    lines.extend(["", f"\u70ed\u5ea6 Top {len(hottest)} \u9510\u8bc4"])
    for rank, item in enumerate(hottest, 1):
        lines.append(
            f"- #{rank} \u9510\u8bc4\uff1a{_clip(str(item['roast']), 100)}"
        )
    lines.extend(["", "\u5b8c\u6574 20 \u6761\u5185\u5bb9\u5df2\u53d1\u9001\u81f3 Telegram\u3002"])
    digest = "\n".join(lines).strip()
    if "http://" in digest or "https://" in digest:
        raise ValueError("Weixin Yahoo digest must not contain long links")
    if len(digest) > max_chars:
        raise ValueError(
            f"Weixin Yahoo digest is {len(digest)} chars; hard limit is {max_chars}"
        )
    return digest


def _archive_messages(messages: list[str], archive_dir: Path) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    date_key = safe.jst_date_key()
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
            f"Yahoo JP safe report aborted: only {len(items)} non-sports item(s) with original article URL after {max_pages} page(s); required {top}"
        )

    safe.require_original_article_urls(items, top)
    safe.assert_no_forbidden_item_fields(items, top)
    for item in items[:top]:
        page_html = safe.fetch_url(item["purl"])
        item["description"] = safe.extract_meta_description(page_html)

    # Keep the original aggregate archive for auditing/backward compatibility.
    report = safe.render_report(items, top)
    now_label = safe.jst_now_label()
    messages = [render_item_message(item, idx, top, now_label) for idx, item in enumerate(items[:top], 1)]
    _assert_clean_messages([report, *messages])

    archive_dir.mkdir(parents=True, exist_ok=True)
    aggregate_path = archive_dir / f"{safe.jst_date_key()}-roast-safe.md"
    aggregate_path.write_text(report, encoding="utf-8")
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
    parser.add_argument("--item-delay", type=float, default=float(os.getenv("HERMES_YAHOO_ITEM_DELAY_SECONDS", "2.0")))
    parser.add_argument(
        "--weixin-max-chars",
        type=int,
        default=DEFAULT_MAX_WEIXIN_CHARS,
        help="Hard character limit for the single Weixin digest",
    )
    parser.add_argument(
        "--weixin-roast-count",
        type=int,
        default=3,
        help="Number of highest-heat one-line roasts in the Weixin digest",
    )
    parser.add_argument(
        "--min-weixin-interval",
        type=float,
        default=DEFAULT_MIN_WEIXIN_INTERVAL,
        help="Minimum seconds between successful cron-originated Weixin sends",
    )
    parser.add_argument(
        "--telegram-retries",
        type=int,
        default=int(os.getenv("HERMES_YAHOO_TELEGRAM_RETRIES", "2")),
        help="Retry count for transient Telegram per-item failures such as TimedOut",
    )
    parser.add_argument(
        "--telegram-retry-delay",
        type=float,
        default=float(os.getenv("HERMES_YAHOO_TELEGRAM_RETRY_DELAY_SECONDS", "5.0")),
        help="Base delay before retrying transient Telegram per-item failures",
    )
    args = parser.parse_args()

    if args.pages < 1 or args.top < 1 or args.max_pages < args.pages:
        parser.error("require --pages>=1, --top>=1, and --max-pages>=--pages")
    if args.weixin_max_chars < 1 or args.weixin_max_chars > DEFAULT_MAX_WEIXIN_CHARS:
        parser.error(
            f"--weixin-max-chars must be between 1 and {DEFAULT_MAX_WEIXIN_CHARS}"
        )
    if args.weixin_roast_count < 0:
        parser.error("--weixin-roast-count must not be negative")
    if not args.dry_run and args.top != 20:
        parser.error("live cron delivery must send exactly 20 Yahoo JP news items; use --dry-run for other counts")
    if args.limit and args.limit > 0 and not args.dry_run:
        parser.error("--limit is dry-run/debug only; live cron delivery must send all generated items")

    _load_env()
    tmp_dir = Path(args.tmp_dir).expanduser()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = Path(args.archive_dir).expanduser()
    try:
        messages = build_messages(args.pages, args.top, args.max_pages, tmp_dir, archive_dir)
        weixin_digest = render_weixin_digest(
            messages,
            max_chars=args.weixin_max_chars,
            roast_count=args.weixin_roast_count,
        )
    except RuntimeError as exc:
        print(f"Yahoo JP per-item delivery aborted: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Yahoo JP per-item delivery aborted: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        preview_messages = messages[: args.limit] if args.limit and args.limit > 0 else messages
        print(
            f"DRY_RUN generated={len(messages)} preview={len(preview_messages)} "
            f"telegram_messages={len(messages)} weixin_messages=1 "
            f"weixin_chars={len(weixin_digest)}"
        )
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

    target_map = {
        target.split(":", 1)[0]: target
        for target in targets
    }
    result = deliver_rate_safe(
        telegram_messages=messages,
        weixin_message=weixin_digest,
        targets=DeliveryTargets(
            telegram=target_map.get("telegram"),
            weixin=target_map.get("weixin"),
        ),
        send_one=_send_one,
        state_dir=HERMES_HOME / "cron",
        max_weixin_chars=args.weixin_max_chars,
        min_weixin_interval=args.min_weixin_interval,
        telegram_retries=args.telegram_retries,
        telegram_retry_delay=args.telegram_retry_delay,
        telegram_message_delay=args.item_delay,
    )
    if not result.ok:
        print(
            "Yahoo JP delivery partially failed on "
            f"{','.join(sorted(result.errors))}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Yahoo JP delivery sent Telegram={result.sent['telegram']} Weixin={result.sent['weixin']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
