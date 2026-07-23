#!/usr/bin/env python3
# pylint: disable=import-error,wrong-import-position,import-outside-toplevel
"""Generate Yahoo JP safe daily report and deliver it to Telegram and Weixin.

Telegram receives each news item separately. Weixin receives small ordered
batches to stay below iLink's proactive-message rate limit. Normal mode is
cron-friendly: messages are delivered via Hermes messaging adapters and stdout
stays empty, so the no_agent cron job itself remains silent on success. Use
--dry-run for validation without sending.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import safe_daily_report as safe  # noqa: E402  # pylint: disable=wrong-import-position

HERMES_HOME = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
HERMES_AGENT_DIR = HERMES_HOME / "hermes-agent"
SECRETS_PATH = HERMES_HOME / "secrets" / "cron_delivery_targets.json"
DEFAULT_ARCHIVE_DIR = HERMES_HOME / "yahoo-reports"


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


def _is_rate_limit_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return "rate limited" in text or "ret=-2" in text or "errcode=-2" in text


def _is_transient_telegram_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return "timed out" in text or "timeout" in text or "networkerror" in text


def _target_item_delay(target: str, default_delay: float, weixin_delay: float | None) -> float:
    scheme = target.split(":", 1)[0]
    if scheme == "weixin" and weixin_delay is not None:
        return weixin_delay
    return default_delay


def _messages_for_target(
    target: str,
    messages: list[str],
    *,
    weixin_batch_size: int,
) -> list[str]:
    """Return platform-specific delivery payloads without changing item order."""
    if target.split(":", 1)[0] != "weixin":
        return list(messages)
    if weixin_batch_size < 1:
        raise ValueError("weixin_batch_size must be at least 1")
    separator = "\n\n---\n\n"
    return [
        separator.join(messages[offset : offset + weixin_batch_size])
        for offset in range(0, len(messages), weixin_batch_size)
    ]


def _send_one_with_retries(
    target: str,
    message: str,
    *,
    telegram_retries: int,
    telegram_retry_delay: float,
) -> dict[str, Any]:
    attempts = 0
    while True:
        try:
            return _send_one(target, message)
        except Exception as exc:  # noqa: BLE001 - preserve platform error text
            scheme = target.split(":", 1)[0]
            if (
                scheme == "telegram"
                and attempts < telegram_retries
                and _is_transient_telegram_failure(exc)
            ):
                attempts += 1
                wait = telegram_retry_delay * attempts
                print(
                    f"telegram transient failure for {target}; retry {attempts}/{telegram_retries} in {wait:.1f}s: {exc}",
                    file=sys.stderr,
                )
                if wait > 0:
                    time.sleep(wait)
                continue
            raise


def _archive_messages(messages: list[str], archive_dir: Path) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    date_key = safe.jst_date_key()
    bundle = "\n---\n\n".join(messages).rstrip() + "\n"
    (archive_dir / f"{date_key}-roast-safe-per-item.md").write_text(bundle, encoding="utf-8")
    (archive_dir / f"{date_key}-roast-safe-per-item.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _deliver_target(
    target: str,
    messages: list[str],
    item_delay: float,
    startup_delay: float = 0.0,
    *,
    telegram_retries: int = 0,
    telegram_retry_delay: float = 5.0,
) -> dict[str, Any]:
    """Deliver all messages to one target, isolated from other target workers."""
    if startup_delay > 0:
        time.sleep(startup_delay)

    scheme = target.split(":", 1)[0]
    failures: list[str] = []
    sent = 0
    for idx, message in enumerate(messages, 1):
        try:
            _send_one_with_retries(
                target,
                message,
                telegram_retries=telegram_retries,
                telegram_retry_delay=telegram_retry_delay,
            )
            sent += 1
            print(f"sent message {idx}/{len(messages)} to {scheme}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - aggregate all platform failures
            failures.append(f"message {idx} -> {target}: {exc}")
            if scheme == "weixin" and _is_rate_limit_failure(exc):
                remaining = len(messages) - idx
                if remaining > 0:
                    failures.append(
                        f"skipped remaining {remaining} message(s) for {target} "
                        "after Weixin/iLink rate limit"
                    )
                break
        if item_delay > 0 and idx < len(messages):
            time.sleep(item_delay)
    return {"target": target, "scheme": scheme, "sent": sent, "failures": failures}


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
    parser.add_argument(
        "--target-delay",
        type=float,
        default=float(os.getenv("HERMES_YAHOO_TARGET_DELAY_SECONDS", "0.5")),
        help="Optional startup stagger in seconds between platform workers",
    )
    parser.add_argument("--item-delay", type=float, default=float(os.getenv("HERMES_YAHOO_ITEM_DELAY_SECONDS", "2.0")))
    parser.add_argument(
        "--weixin-item-delay",
        type=float,
        default=float(os.getenv("HERMES_YAHOO_WEIXIN_ITEM_DELAY_SECONDS", "25.0")),
        help="Delay between Weixin/iLink item sends; higher than Telegram to avoid burst rate limits",
    )
    parser.add_argument(
        "--weixin-batch-size",
        type=int,
        default=int(os.getenv("HERMES_YAHOO_WEIXIN_BATCH_SIZE", "5")),
        help="Number of ordered news items combined into each Weixin message",
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
    if args.weixin_batch_size < 1:
        parser.error("--weixin-batch-size must be at least 1")
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
    except RuntimeError as exc:
        print(f"Yahoo JP per-item delivery aborted: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Yahoo JP per-item delivery aborted: {exc}", file=sys.stderr)
        return 1

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

    # A platform-level outage/rate-limit must not block the other platform.
    # Run one worker per platform: each worker sends its own 20 items in order,
    # but Telegram and Weixin progress independently. If Weixin/iLink rate-limits,
    # only the Weixin worker skips its remaining items; Telegram continues.
    if "WEIXIN_RATE_LIMIT_RETRIES" not in os.environ:
        os.environ["WEIXIN_RATE_LIMIT_RETRIES"] = os.getenv(
            "HERMES_YAHOO_WEIXIN_RATE_LIMIT_RETRIES",
            "0",
        )

    failures: list[str] = []
    sent = 0
    delivery_messages = {
        target: _messages_for_target(
            target,
            messages,
            weixin_batch_size=args.weixin_batch_size,
        )
        for target in targets
    }
    total_attempts = sum(len(payloads) for payloads in delivery_messages.values())
    with ThreadPoolExecutor(max_workers=len(targets), thread_name_prefix="yahoo-delivery") as executor:
        future_to_target = {
            executor.submit(
                _deliver_target,
                target,
                delivery_messages[target],
                _target_item_delay(target, args.item_delay, args.weixin_item_delay),
                idx * args.target_delay,
                telegram_retries=args.telegram_retries,
                telegram_retry_delay=args.telegram_retry_delay,
            ): target
            for idx, target in enumerate(targets)
        }
        for future in as_completed(future_to_target):
            target = future_to_target[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - report worker-level crashes as platform failures
                failures.append(f"target {target} worker crashed: {exc}")
                continue
            sent += int(result["sent"])
            failures.extend(result["failures"])

    if failures:
        print(
            f"Yahoo JP per-item delivery partially failed after {sent}/{total_attempts} successful sends",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Yahoo JP per-item delivery sent {len(messages)} item(s) to {len(targets)} target(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
