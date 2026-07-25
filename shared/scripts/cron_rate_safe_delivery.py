#!/usr/bin/env python3
"""Rate-safe multi-platform delivery for Hermes content cron jobs.

Telegram keeps the complete payload sequence. Weixin receives at most one
bounded digest per job run, serialized across cron processes by a file lock.
"""
from __future__ import annotations

import argparse
import hashlib
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
DEFAULT_MIN_WEIXIN_INTERVAL = 180.0
DEFAULT_MAX_WEIXIN_CONTEXT_AGE = 20 * 60 * 60.0
DEFAULT_MAX_WEIXIN_SENDS_PER_CONTEXT = 5
MAX_SENT_ID_HISTORY = 500


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
    deferred: dict[str, int] = field(
        default_factory=lambda: {"telegram": 0, "weixin": 0}
    )

    @property
    def ok(self) -> bool:
        return not self.errors


def _hermes_home() -> Path:
    return Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()


def _load_runtime_env(*, hermes_home: Path | None = None) -> None:
    """Load adapter credentials for standalone no-agent cron processes."""
    env_path = (hermes_home or _hermes_home()) / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(str(env_path), override=True, encoding="utf-8")
        return
    except Exception:
        pass

    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def load_delivery_targets(
    *,
    hermes_home: Path | None = None,
) -> DeliveryTargets:
    """Load private delivery IDs without exposing them in output."""
    root = hermes_home or _hermes_home()
    _load_runtime_env(hermes_home=root)
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


def _weixin_context_fingerprint(*, hermes_home: Path, target: str) -> str:
    """Fingerprint the target's persisted context without exposing its token.

    The file mtime is included because an inbound message can refresh the
    session even when iLink happens to reuse the same opaque token value.
    """
    chat_id = target.split(":", 1)[1] if ":" in target else target
    account_dir = hermes_home / "weixin" / "accounts"
    material: list[str] = []
    for path in sorted(account_dir.glob("*.context-tokens.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            value = raw.get(chat_id) if isinstance(raw, dict) else None
            if isinstance(value, dict):
                value = value.get("token") or value.get("context_token")
            stat = path.stat()
            material.append(f"{path.name}:{stat.st_mtime_ns}:{value or '<missing>'}")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    if not material:
        material.append("<no-context-file>")
    return hashlib.sha256("\n".join(material).encode("utf-8")).hexdigest()


def _weixin_context_updated_at(*, hermes_home: Path, target: str) -> float | None:
    chat_id = target.split(":", 1)[1] if ":" in target else target
    updated_at: float | None = None
    account_dir = hermes_home / "weixin" / "accounts"
    for path in sorted(account_dir.glob("*.context-tokens.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            value = raw.get(chat_id) if isinstance(raw, dict) else None
            if isinstance(value, dict):
                value = value.get("token") or value.get("context_token")
            if value:
                mtime = path.stat().st_mtime
                updated_at = mtime if updated_at is None else max(updated_at, mtime)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return updated_at


def _weixin_entry_id(job_name: str, message: str, delivery_date: str) -> str:
    material = f"{job_name}\0{delivery_date}\0{message}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _is_deferable_weixin_error(error: Exception | str) -> bool:
    text = str(error).strip().lower()
    return any(
        marker in text
        for marker in (
            "ilink sendmessage rate limited",
            "cooldown active",
            "stale context_token",
            "stale context token",
            "session expired",
        )
    )


def _build_pending_weixin_digest(
    entries: Sequence[dict[str, Any]],
    *,
    max_chars: int,
) -> str:
    items = [
        (
            str(entry.get("job_name") or "content-cron")[:40],
            str(entry.get("message") or "").strip(),
        )
        for entry in entries
        if str(entry.get("message") or "").strip()
    ]
    header = f"📬 微信待投递摘要（{len(items)}项）"
    if not items:
        return header[:max_chars]

    titles = [f"【{name}】\n" for name, _message in items]
    fixed_chars = len(header) + 2 + (2 * max(0, len(items) - 1)) + sum(
        len(title) for title in titles
    )
    body_budget = max_chars - fixed_chars
    if body_budget < len(items):
        # Extremely deep outboxes cannot carry every body in one Weixin
        # request.  Still acknowledge every source instead of silently marking
        # truncated entries as if their text had been included.
        labels = "、".join(name for name, _message in items)
        notice = f"{header}\n\n待投递来源：{labels}\n完整内容已发送至 Telegram/本地归档。"
        return notice[:max_chars]

    base, remainder = divmod(body_budget, len(items))
    sections: list[str] = []
    for index, ((name, message), title) in enumerate(zip(items, titles)):
        budget = base + (1 if index < remainder else 0)
        if len(message) > budget:
            message = message[: max(1, budget - 1)].rstrip() + "…"
        sections.append(title + message)
    return (header + "\n\n" + "\n\n".join(sections))[:max_chars]


def _default_send_one(target: str, message: str) -> dict[str, Any]:
    _load_runtime_env()
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
    """Account-wide lock, context circuit breaker, outbox and idempotency state."""

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
        self.state_path = self.state_dir / "weixin_content_delivery_state.json"
        self.state: dict[str, Any] = {}

    def __enter__(self) -> "_WeixinRateGate":
        import fcntl

        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_dir / ".weixin_content_delivery.lock"
        self._lock_handle = lock_path.open("a+", encoding="utf-8")
        fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX)

        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.state = state if isinstance(state, dict) else {}
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            self.state = {}
        if not isinstance(self.state.get("pending"), list):
            self.state["pending"] = []
        if not isinstance(self.state.get("sent_ids"), list):
            self.state["sent_ids"] = []
        if not isinstance(self.state.get("blocked_context_fingerprints"), list):
            self.state["blocked_context_fingerprints"] = []
        if not isinstance(self.state.get("context_send_counts"), dict):
            self.state["context_send_counts"] = {}
        return self

    def wait_for_slot(self) -> None:
        last_success = float(self.state.get("last_success_at") or 0.0)
        wait = max(0.0, self.min_interval - (self.clock() - last_success))
        if wait:
            self.sleep(wait)

    def _save(self) -> None:
        tmp_path = self.state_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self.state, ensure_ascii=True, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(self.state_path)

    def is_sent(self, entry_id: str) -> bool:
        return entry_id in self.state["sent_ids"]

    def is_context_blocked(self, fingerprint: str) -> bool:
        return fingerprint in self.state["blocked_context_fingerprints"]

    def context_send_count(self, fingerprint: str) -> int:
        try:
            return max(0, int(self.state["context_send_counts"].get(fingerprint, 0)))
        except (TypeError, ValueError):
            return 0

    def queue_pending(self, entry: dict[str, Any]) -> bool:
        entry_id = str(entry["id"])
        if self.is_sent(entry_id):
            return False
        if any(item.get("id") == entry_id for item in self.state["pending"]):
            return False
        self.state["pending"].append(entry)
        self._save()
        return True

    def mark_context_blocked(self, *fingerprints: str) -> None:
        blocked = list(self.state["blocked_context_fingerprints"])
        for fingerprint in fingerprints:
            if fingerprint and fingerprint not in blocked:
                blocked.append(fingerprint)
        self.state["blocked_context_fingerprints"] = blocked[-20:]
        self._save()

    def mark_success(self, entry_ids: Sequence[str], *, context_fingerprint: str) -> None:
        sent = list(self.state["sent_ids"])
        for entry_id in entry_ids:
            if entry_id not in sent:
                sent.append(entry_id)
        sent_set = set(entry_ids)
        self.state["sent_ids"] = sent[-MAX_SENT_ID_HISTORY:]
        self.state["pending"] = [
            item for item in self.state["pending"] if item.get("id") not in sent_set
        ]
        self.state["blocked_context_fingerprints"] = []
        counts = dict(self.state["context_send_counts"])
        counts[context_fingerprint] = self.context_send_count(context_fingerprint) + 1
        self.state["context_send_counts"] = dict(list(counts.items())[-20:])
        self.state["last_success_at"] = self.clock()
        self._save()

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


@dataclass(frozen=True)
class _WeixinOutcome:
    sent: int = 0
    deferred: int = 0


def _send_weixin_digest(
    message: str,
    *,
    target: str,
    send_one: Callable[[str, str], dict[str, Any]],
    state_dir: Path,
    hermes_home: Path,
    job_name: str,
    max_chars: int,
    min_interval: float,
    max_context_age: float,
    max_sends_per_context: int,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> _WeixinOutcome:
    if len(message) > max_chars:
        raise ValueError(
            f"Weixin digest is {len(message)} chars; hard limit is {max_chars}"
        )
    if not message.strip():
        return _WeixinOutcome()

    delivery_date = time.strftime("%Y-%m-%d", time.localtime(clock()))
    entry = {
        "id": _weixin_entry_id(job_name, message, delivery_date),
        "job_name": job_name,
        "report_date": delivery_date,
        "message": message,
        "created_at": clock(),
    }
    with _WeixinRateGate(
        state_dir=state_dir,
        min_interval=min_interval,
        clock=clock,
        sleep=sleep,
    ) as gate:
        entry_id = str(entry["id"])
        if gate.is_sent(entry_id):
            print("skipped already-sent Weixin digest", file=sys.stderr)
            return _WeixinOutcome()

        context_before = _weixin_context_fingerprint(
            hermes_home=hermes_home,
            target=target,
        )
        context_updated_at = _weixin_context_updated_at(
            hermes_home=hermes_home,
            target=target,
        )
        if gate.is_context_blocked(context_before):
            gate.queue_pending(entry)
            print(
                "deferred Weixin digest: context is still blocked; no network request made",
                file=sys.stderr,
            )
            return _WeixinOutcome(deferred=1)
        if (
            context_updated_at is not None
            and max_context_age > 0
            and clock() - context_updated_at > max_context_age
        ):
            gate.queue_pending(entry)
            gate.mark_context_blocked(context_before)
            print(
                "deferred Weixin digest: persisted context is older than the safety window",
                file=sys.stderr,
            )
            return _WeixinOutcome(deferred=1)
        if (
            max_sends_per_context > 0
            and gate.context_send_count(context_before) >= max_sends_per_context
        ):
            gate.queue_pending(entry)
            gate.mark_context_blocked(context_before)
            print(
                "deferred Weixin digest: cron send budget for this context is exhausted",
                file=sys.stderr,
            )
            return _WeixinOutcome(deferred=1)

        pending_before = list(gate.state["pending"])
        if pending_before:
            gate.queue_pending(entry)
            pending_to_send = list(gate.state["pending"])
            payload = _build_pending_weixin_digest(
                pending_to_send,
                max_chars=max_chars,
            )
            entry_ids = [str(item["id"]) for item in pending_to_send]
        else:
            payload = message
            entry_ids = [entry_id]

        # This process is dedicated to cron delivery; ordinary gateway replies
        # run elsewhere and keep their own retry policy.
        os.environ["WEIXIN_RATE_LIMIT_RETRIES"] = "0"
        gate.wait_for_slot()
        try:
            send_one(target, payload)
        except Exception as exc:
            if not _is_deferable_weixin_error(exc):
                raise
            gate.queue_pending(entry)
            context_after = _weixin_context_fingerprint(
                hermes_home=hermes_home,
                target=target,
            )
            gate.mark_context_blocked(context_before, context_after)
            print(
                f"deferred Weixin digest after iLink session rejection: {_redact_error(exc)}",
                file=sys.stderr,
            )
            return _WeixinOutcome(deferred=1)

        gate.mark_success(entry_ids, context_fingerprint=context_before)
    print("sent Weixin digest 1/1", file=sys.stderr)
    return _WeixinOutcome(sent=1)


def deliver_rate_safe(
    *,
    telegram_messages: Sequence[str],
    weixin_message: str,
    targets: DeliveryTargets | None = None,
    send_one: Callable[[str, str], dict[str, Any]] | None = None,
    state_dir: Path | None = None,
    hermes_home: Path | None = None,
    job_name: str = "content-cron",
    max_weixin_chars: int = DEFAULT_MAX_WEIXIN_CHARS,
    min_weixin_interval: float = DEFAULT_MIN_WEIXIN_INTERVAL,
    max_weixin_context_age: float = DEFAULT_MAX_WEIXIN_CONTEXT_AGE,
    max_weixin_sends_per_context: int = DEFAULT_MAX_WEIXIN_SENDS_PER_CONTEXT,
    telegram_retries: int = 2,
    telegram_retry_delay: float = 5.0,
    telegram_message_delay: float = 2.0,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> DeliveryResult:
    """Deliver full Telegram content and one bounded Weixin digest."""
    resolved_targets = targets or load_delivery_targets()
    sender = send_one or _default_send_one
    home = hermes_home or _hermes_home()
    root = state_dir or (home / "cron")
    telegram_payloads = [str(message) for message in telegram_messages if str(message).strip()]
    weixin_payload = str(weixin_message or "").strip()

    workers: dict[str, Callable[[], Any]] = {}
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
                hermes_home=home,
                job_name=str(job_name or "content-cron"),
                max_chars=int(max_weixin_chars),
                min_interval=float(min_weixin_interval),
                max_context_age=max(0.0, float(max_weixin_context_age)),
                max_sends_per_context=max(0, int(max_weixin_sends_per_context)),
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
                outcome = future.result()
                if platform == "weixin" and isinstance(outcome, _WeixinOutcome):
                    result.sent[platform] = outcome.sent
                    result.deferred[platform] = outcome.deferred
                else:
                    result.sent[platform] = int(outcome)
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
    parser.add_argument(
        "--max-weixin-context-age",
        type=float,
        default=DEFAULT_MAX_WEIXIN_CONTEXT_AGE,
    )
    parser.add_argument(
        "--max-weixin-sends-per-context",
        type=int,
        default=DEFAULT_MAX_WEIXIN_SENDS_PER_CONTEXT,
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
        job_name=args.job_name,
        max_weixin_chars=args.max_weixin_chars,
        min_weixin_interval=args.min_weixin_interval,
        max_weixin_context_age=args.max_weixin_context_age,
        max_weixin_sends_per_context=args.max_weixin_sends_per_context,
        telegram_retries=args.telegram_retries,
        telegram_retry_delay=args.telegram_retry_delay,
        telegram_message_delay=args.telegram_message_delay,
    )
    if result.ok:
        print(
            f"{args.job_name}: delivered Telegram={result.sent['telegram']} "
            f"Weixin={result.sent['weixin']} Deferred={result.deferred['weixin']}",
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
