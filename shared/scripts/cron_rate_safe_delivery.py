#!/usr/bin/env python3
"""Rate-safe multi-platform delivery for Hermes content cron jobs.

Telegram keeps the complete payload sequence. Weixin receives at most one
bounded digest per job run, serialized across cron processes by a file lock.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

DEFAULT_MAX_WEIXIN_CHARS = 1800
DEFAULT_MIN_WEIXIN_INTERVAL = 30.0


@dataclass(frozen=True)
class DeliveryTargets:
    telegram: str | None
    weixin: str | None


@dataclass
class DeliveryResult:
    sent: dict[str, int] = field(
        default_factory=lambda: {"telegram": 0, "weixin": 0}
    )
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _hermes_home() -> Path:
    return Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()


def load_delivery_targets(
    *,
    hermes_home: Path | None = None,
) -> DeliveryTargets:
    """Load private delivery IDs without exposing them in output."""
    root = hermes_home or _hermes_home()
    data: dict[str, Any] = {}
    secrets_path = root / "secrets" / "cron_delivery_targets.json"
    if secrets_path.exists():
        data = json.loads(secrets_path.read_text(encoding="utf-8"))

    telegram_id = str(
        os.getenv("HERMES_DELIVERY_TELEGRAM_CHAT_ID")
        or data.get("telegram_chat_id")
        or ""
    ).strip()
    weixin_id = str(
        os.getenv("HERMES_DELIVERY_WEIXIN_CHAT_ID")
        or data.get("weixin_chat_id")
        or ""
    ).strip()

    telegram = f"telegram:{telegram_id}" if telegram_id else None
    weixin = f"weixin:{weixin_id}" if weixin_id else None
    return DeliveryTargets(telegram=telegram, weixin=weixin)


def compact_weixin_text(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_WEIXIN_CHARS,
) -> str:
    """Compact Markdown deterministically without creating a second message."""
    content = text.strip()
    if len(content) <= max_chars:
        return content

    footer = "\n\n（内容已压缩，完整内容已发送至 Telegram）"
    if max_chars <= len(footer) + 1:
        raise ValueError("max_chars is too small for the compact-message footer")

    budget = max_chars - len(footer)
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    selected: list[str] = []
    used = 0
    for block in blocks:
        separator = 2 if selected else 0
        if used + separator + len(block) <= budget:
            selected.append(block)
            used += separator + len(block)
            continue
        if not selected:
            selected.append(block[: max(1, budget - 1)].rstrip() + "…")
        break

    body = "\n\n".join(selected).rstrip()
    return (body + footer)[:max_chars]


def _redact_error(error: Exception | str) -> str:
    text = str(error)
    text = re.sub(r"telegram:[^,\s]+", "telegram:[REDACTED]", text)
    text = re.sub(r"weixin:[^,\s]+", "weixin:[REDACTED]", text)
    return text


def _default_send_one(target: str, message: str) -> dict[str, Any]:
    agent_dir = _hermes_home() / "hermes-agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    from tools.send_message_tool import _handle_send  # type: ignore

    raw = _handle_send({"target": target, "message": message})
    result = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(result, dict):
        raise RuntimeError("send_message returned a non-object result")
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    if not result.get("success"):
        raise RuntimeError("send_message did not report success")
    return result


def _is_transient_telegram_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in ("timed out", "timeout", "networkerror"))


class _WeixinRateGate:
    """Cross-process lock plus persisted successful-send timestamp."""

    def __init__(
        self,
        *,
        state_dir: Path,
        min_interval: float,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self.state_dir = state_dir
        self.min_interval = max(0.0, float(min_interval))
        self.clock = clock
        self.sleep = sleep
        self._lock_handle = None

    def __enter__(self) -> "_WeixinRateGate":
        import fcntl

        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_dir / ".weixin_content_delivery.lock"
        self._lock_handle = lock_path.open("a+", encoding="utf-8")
        fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX)

        last_success = 0.0
        state_path = self.state_dir / "weixin_content_delivery_state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            last_success = float(state.get("last_success_at") or 0.0)
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            last_success = 0.0

        wait = max(0.0, self.min_interval - (self.clock() - last_success))
        if wait:
            self.sleep(wait)
        return self

    def mark_success(self) -> None:
        state_path = self.state_dir / "weixin_content_delivery_state.json"
        tmp_path = state_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(
                {"last_success_at": self.clock()},
                ensure_ascii=True,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(state_path)

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self._lock_handle is None:
            return
        import fcntl

        fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
        self._lock_handle.close()
        self._lock_handle = None


def _send_telegram_sequence(
    messages: Sequence[str],
    *,
    target: str,
    send_one: Callable[[str, str], dict[str, Any]],
    retries: int,
    retry_delay: float,
    message_delay: float,
    sleep: Callable[[float], None],
) -> int:
    sent = 0
    for index, message in enumerate(messages, 1):
        attempts = 0
        while True:
            try:
                send_one(target, message)
                sent += 1
                print(
                    f"sent Telegram message {index}/{len(messages)}",
                    file=sys.stderr,
                )
                break
            except Exception as exc:
                if attempts >= retries or not _is_transient_telegram_error(exc):
                    raise
                attempts += 1
                wait = max(0.0, retry_delay * attempts)
                print(
                    f"Telegram transient failure; retry {attempts}/{retries} in {wait:.1f}s",
                    file=sys.stderr,
                )
                if wait:
                    sleep(wait)
        if message_delay > 0 and index < len(messages):
            sleep(message_delay)
    return sent


def _send_weixin_digest(
    message: str,
    *,
    target: str,
    send_one: Callable[[str, str], dict[str, Any]],
    state_dir: Path,
    max_chars: int,
    min_interval: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> int:
    if len(message) > max_chars:
        raise ValueError(
            f"Weixin digest is {len(message)} chars; hard limit is {max_chars}"
        )
    if not message.strip():
        return 0

    with _WeixinRateGate(
        state_dir=state_dir,
        min_interval=min_interval,
        clock=clock,
        sleep=sleep,
    ) as gate:
        # This process is dedicated to cron delivery; ordinary gateway replies
        # run elsewhere and keep their own retry policy.
        os.environ["WEIXIN_RATE_LIMIT_RETRIES"] = "0"
        send_one(target, message)
        gate.mark_success()
    print("sent Weixin digest 1/1", file=sys.stderr)
    return 1


def deliver_rate_safe(
    *,
    telegram_messages: Sequence[str],
    weixin_message: str,
    targets: DeliveryTargets | None = None,
    send_one: Callable[[str, str], dict[str, Any]] | None = None,
    state_dir: Path | None = None,
    max_weixin_chars: int = DEFAULT_MAX_WEIXIN_CHARS,
    min_weixin_interval: float = DEFAULT_MIN_WEIXIN_INTERVAL,
    telegram_retries: int = 2,
    telegram_retry_delay: float = 5.0,
    telegram_message_delay: float = 2.0,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> DeliveryResult:
    """Deliver full Telegram content and one bounded Weixin digest."""
    resolved_targets = targets or load_delivery_targets()
    sender = send_one or _default_send_one
    root = state_dir or (_hermes_home() / "cron")
    telegram_payloads = [str(message) for message in telegram_messages if str(message).strip()]
    weixin_payload = str(weixin_message or "").strip()

    workers: dict[str, Callable[[], int]] = {}
    if telegram_payloads:
        if not resolved_targets.telegram:
            workers["telegram"] = lambda: (_ for _ in ()).throw(
                RuntimeError("Telegram delivery target is not configured")
            )
        else:
            workers["telegram"] = lambda: _send_telegram_sequence(
                telegram_payloads,
                target=resolved_targets.telegram or "",
                send_one=sender,
                retries=max(0, int(telegram_retries)),
                retry_delay=max(0.0, float(telegram_retry_delay)),
                message_delay=max(0.0, float(telegram_message_delay)),
                sleep=sleep,
            )
    if weixin_payload:
        if not resolved_targets.weixin:
            workers["weixin"] = lambda: (_ for _ in ()).throw(
                RuntimeError("Weixin delivery target is not configured")
            )
        else:
            workers["weixin"] = lambda: _send_weixin_digest(
                weixin_payload,
                target=resolved_targets.weixin or "",
                send_one=sender,
                state_dir=root,
                max_chars=int(max_weixin_chars),
                min_interval=float(min_weixin_interval),
                clock=clock,
                sleep=sleep,
            )

    result = DeliveryResult()
    if not workers:
        return result

    with ThreadPoolExecutor(max_workers=len(workers), thread_name_prefix="cron-delivery") as executor:
        future_to_platform = {
            executor.submit(worker): platform for platform, worker in workers.items()
        }
        for future in as_completed(future_to_platform):
            platform = future_to_platform[future]
            try:
                result.sent[platform] = int(future.result())
            except Exception as exc:
                result.errors[platform] = _redact_error(exc)
                print(f"{platform} delivery failed: {_redact_error(exc)}", file=sys.stderr)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deliver full Telegram content plus one rate-safe Weixin digest"
    )
    parser.add_argument("--telegram-file", action="append", default=[])
    parser.add_argument("--weixin-file", required=True)
    parser.add_argument("--compact-weixin", action="store_true")
    parser.add_argument("--max-weixin-chars", type=int, default=DEFAULT_MAX_WEIXIN_CHARS)
    parser.add_argument(
        "--min-weixin-interval",
        type=float,
        default=DEFAULT_MIN_WEIXIN_INTERVAL,
    )
    parser.add_argument("--telegram-retries", type=int, default=2)
    parser.add_argument("--telegram-retry-delay", type=float, default=5.0)
    parser.add_argument("--telegram-message-delay", type=float, default=2.0)
    parser.add_argument("--job-name", default="content-cron")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    telegram_messages = [
        Path(path).read_text(encoding="utf-8").strip()
        for path in args.telegram_file
    ]
    weixin_message = Path(args.weixin_file).read_text(encoding="utf-8").strip()
    if args.compact_weixin:
        weixin_message = compact_weixin_text(
            weixin_message,
            max_chars=args.max_weixin_chars,
        )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "job": args.job_name,
                    "telegram_messages": len([m for m in telegram_messages if m]),
                    "weixin_messages": 1 if weixin_message else 0,
                    "weixin_chars": len(weixin_message),
                    "max_weixin_chars": args.max_weixin_chars,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if len(weixin_message) <= args.max_weixin_chars else 1

    result = deliver_rate_safe(
        telegram_messages=telegram_messages,
        weixin_message=weixin_message,
        max_weixin_chars=args.max_weixin_chars,
        min_weixin_interval=args.min_weixin_interval,
        telegram_retries=args.telegram_retries,
        telegram_retry_delay=args.telegram_retry_delay,
        telegram_message_delay=args.telegram_message_delay,
    )
    if result.ok:
        print(
            f"{args.job_name}: delivered Telegram={result.sent['telegram']} Weixin={result.sent['weixin']}",
            file=sys.stderr,
        )
        return 0
    print(
        f"{args.job_name}: partial delivery failure on {','.join(sorted(result.errors))}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
