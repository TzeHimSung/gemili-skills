#!/usr/bin/env python3
"""Cron delivery policy guardrails.

This module codifies the Hermes cron delivery rules for the user's recurring
content jobs:

- User-facing recurring cron jobs must use one comma-separated, explicit
  multi-target deliver string: ``telegram:7943831495,weixin:<chat_id>``.
- ``origin`` is not allowed for content jobs because it can only resolve to one
  platform and may drift depending on where the job was created.
- Bare ``telegram`` / ``weixin`` are not allowed; explicit chat IDs make the
  target stable and avoid Telegram Home names such as ``thsung`` being parsed as
  numeric chat IDs.
- The silent local guard job named ``Cron投递策略守卫`` is the only exception; it
  audits jobs every 30 minutes and corrects any drift back to the enforced
  Telegram + Weixin target.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_TELEGRAM_CHAT_ID = "7943831495"
DEFAULT_WEIXIN_CHAT_ID = "o9cq80ys2QEOI68H3HtT5ENJzNmE@im.wechat"
ENFORCED_DELIVER_TARGETS = (
    f"telegram:{DEFAULT_TELEGRAM_CHAT_ID}",
    f"weixin:{DEFAULT_WEIXIN_CHAT_ID}",
)
ENFORCED_DELIVER_TARGET = ",".join(ENFORCED_DELIVER_TARGETS)
PREFERRED_NEW_JOB_DELIVER = ENFORCED_DELIVER_TARGET
TELEGRAM_TARGET_RE = re.compile(r"^telegram:(?P<chat_id>-?\d+)(?::(?P<thread_id>\d+))?$")
WEIXIN_TARGET_RE = re.compile(r"^weixin:(?P<chat_id>[^,\s]+)$")


@dataclass(frozen=True)
class DeliveryDecision:
    job_id: str
    name: str
    ok: bool
    current_deliver: str | None
    recommended_deliver: str
    reason: str


@dataclass(frozen=True)
class DeliveryIssue:
    job_id: str
    name: str
    current_deliver: str | None
    recommended_deliver: str
    reason: str


def _origin_platform(job: dict[str, Any]) -> str | None:
    origin = job.get("origin") or {}
    if isinstance(origin, dict):
        return origin.get("platform")
    return None


def _origin_chat_id(job: dict[str, Any]) -> str | None:
    origin = job.get("origin") or {}
    if isinstance(origin, dict):
        chat_id = origin.get("chat_id")
        return str(chat_id) if chat_id is not None else None
    return None


def _is_numeric_chat_id(chat_id: str | None) -> bool:
    return bool(chat_id and re.fullmatch(r"-?\d+", chat_id))


def _explicit_telegram_target(chat_id: str | None) -> str:
    if not _is_numeric_chat_id(chat_id):
        raise ValueError(f"telegram_chat_id must be numeric, got {chat_id!r}")
    return f"telegram:{chat_id}"


def _explicit_weixin_target(chat_id: str | None) -> str:
    if not chat_id or "," in chat_id or any(ch.isspace() for ch in chat_id):
        raise ValueError(f"weixin_chat_id must be a non-empty explicit chat id without commas/spaces, got {chat_id!r}")
    return f"weixin:{chat_id}"


def _split_deliver_targets(deliver: str | None) -> list[str]:
    if deliver is None:
        return []
    return [part.strip() for part in str(deliver).split(",") if part.strip()]


def _validate_required_deliver(required_deliver: str) -> None:
    parts = _split_deliver_targets(required_deliver)
    if not parts:
        raise ValueError("required_deliver must contain at least one explicit target")
    invalid = [part for part in parts if not (TELEGRAM_TARGET_RE.fullmatch(part) or WEIXIN_TARGET_RE.fullmatch(part))]
    if invalid:
        raise ValueError(
            "required_deliver must contain only explicit numeric Telegram targets and explicit Weixin targets; "
            f"invalid={invalid!r}"
        )


def is_delivery_guard_job(job: dict[str, Any]) -> bool:
    """Return True for the silent local job that enforces this policy."""

    return str(job.get("name") or "") == "Cron投递策略守卫"


def is_active_recurring_job(job: dict[str, Any]) -> bool:
    """Return True for enabled recurring jobs that should actively notify user."""

    if job.get("enabled") is False:
        return False
    repeat = job.get("repeat")
    if isinstance(repeat, dict):
        # Hermes stores forever jobs as {"times": null, "completed": N}.
        return repeat.get("times") is None
    return repeat in (None, "forever")


def _target_issue(target: str, *, origin_platform: str | None, origin_chat_id: str | None) -> str | None:
    """Return None if one deliver target is allowed, otherwise a human reason."""

    if target == "origin":
        return (
            "origin can resolve to only one platform and may drift; "
            f"origin platform={origin_platform or 'missing'} chat_id={origin_chat_id or 'missing'}"
        )
    if target == "telegram":
        return "bare telegram is unsafe because Home ID may be non-numeric (e.g. thsung)"
    if target == "weixin":
        return "bare weixin depends on Home channel; use explicit weixin:<chat_id>"
    if target == "local":
        return "active content jobs must notify Telegram + Weixin, not local-only"
    if TELEGRAM_TARGET_RE.fullmatch(target):
        return None
    if WEIXIN_TARGET_RE.fullmatch(target):
        return None
    if target.startswith("telegram:"):
        return "telegram target is not numeric; names such as telegram:TzeHim Sung time out"
    if target.startswith("weixin:"):
        return "weixin target is malformed; use weixin:<chat_id> without commas/spaces"
    if target.startswith("qqbot"):
        return "qqbot proactive delivery fails with 11263 ErrorCheckGuildAuth"
    return f"unsupported deliver target: {target}"


def evaluate_job(
    job: dict[str, Any],
    *,
    telegram_chat_id: str | None = None,
    weixin_chat_id: str | None = None,
    required_deliver: str | None = None,
) -> DeliveryDecision:
    """Evaluate one cron job against the delivery policy.

    ``required_deliver`` enables strict guard mode. When present, every active
    recurring content job must use that exact comma-separated deliver string.
    """

    job_id = str(job.get("id") or job.get("job_id") or "")
    name = str(job.get("name") or "")
    deliver = job.get("deliver")
    deliver_s = str(deliver) if deliver is not None else None
    origin_platform = _origin_platform(job)
    origin_chat_id = _origin_chat_id(job)

    if required_deliver:
        _validate_required_deliver(required_deliver)
    recommended = required_deliver or ",".join(
        (
            _explicit_telegram_target(telegram_chat_id or DEFAULT_TELEGRAM_CHAT_ID),
            _explicit_weixin_target(weixin_chat_id or DEFAULT_WEIXIN_CHAT_ID),
        )
    )

    if deliver_s is None:
        return DeliveryDecision(
            job_id,
            name,
            False,
            None,
            recommended,
            "missing deliver target",
        )

    if required_deliver and deliver_s != required_deliver:
        return DeliveryDecision(
            job_id,
            name,
            False,
            deliver_s,
            required_deliver,
            f"required deliver target is {required_deliver}; got {deliver_s}",
        )

    parts = _split_deliver_targets(deliver_s)
    if not parts:
        return DeliveryDecision(job_id, name, False, deliver_s, recommended, "empty deliver target")

    invalid_reasons = [
        reason
        for part in parts
        if (reason := _target_issue(part, origin_platform=origin_platform, origin_chat_id=origin_chat_id))
    ]
    if invalid_reasons:
        return DeliveryDecision(
            job_id,
            name,
            False,
            deliver_s,
            recommended,
            "; ".join(invalid_reasons),
        )

    seen = set()
    duplicate_parts = []
    for part in parts:
        key = part.lower()
        if key in seen:
            duplicate_parts.append(part)
        seen.add(key)
    if duplicate_parts:
        return DeliveryDecision(
            job_id,
            name,
            False,
            deliver_s,
            recommended,
            f"duplicate deliver targets: {duplicate_parts!r}",
        )

    return DeliveryDecision(
        job_id,
        name,
        True,
        deliver_s,
        deliver_s,
        "explicit delivery target(s)",
    )


def audit_jobs(
    jobs: Iterable[dict[str, Any]],
    *,
    telegram_chat_id: str | None = None,
    weixin_chat_id: str | None = None,
    required_deliver: str | None = None,
) -> list[DeliveryIssue]:
    """Return delivery-policy violations for enabled recurring jobs."""

    issues: list[DeliveryIssue] = []
    for job in jobs:
        if is_delivery_guard_job(job):
            continue
        if not is_active_recurring_job(job):
            continue
        decision = evaluate_job(
            job,
            telegram_chat_id=telegram_chat_id,
            weixin_chat_id=weixin_chat_id,
            required_deliver=required_deliver,
        )
        if not decision.ok:
            issues.append(
                DeliveryIssue(
                    job_id=decision.job_id,
                    name=decision.name,
                    current_deliver=decision.current_deliver,
                    recommended_deliver=decision.recommended_deliver,
                    reason=decision.reason,
                )
            )
    return issues


def load_jobs_file(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):
        return data["jobs"]
    if isinstance(data, list):
        return data
    raise ValueError("jobs file must be a JSON object with a jobs list, or a jobs list")


def build_create_kwargs(
    *,
    name: str,
    skill: str,
    prompt: str,
    schedule: str,
    repeat: int | None = None,
    deliver: str = PREFERRED_NEW_JOB_DELIVER,
    skills: list[str] | None = None,
) -> dict[str, Any]:
    """Build safe kwargs for Hermes ``cronjob(action='create', ...)`` calls.

    Recurring schedules are forever by default in the cronjob tool, so this
    helper omits ``repeat`` unless the caller explicitly requests a finite
    repeat count.
    """

    kwargs: dict[str, Any] = {
        "action": "create",
        "name": name,
        "skill": skill,
        "skills": skills or [skill],
        "prompt": prompt,
        "schedule": schedule,
        "deliver": deliver,
    }
    if repeat is not None:
        kwargs["repeat"] = repeat
    return kwargs


def _print_audit(issues: list[DeliveryIssue]) -> None:
    if not issues:
        print("✅ delivery policy audit passed")
        return
    print(f"❌ delivery policy audit found {len(issues)} issue(s)")
    for issue in issues:
        print(
            f"- {issue.job_id} {issue.name}: deliver={issue.current_deliver!r} -> "
            f"{issue.recommended_deliver!r} ({issue.reason})"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Hermes cron delivery targets")
    parser.add_argument("jobs_file", help="Path to ~/.hermes/cron/jobs.json or exported cronjob list JSON")
    parser.add_argument("--telegram-chat-id", default=DEFAULT_TELEGRAM_CHAT_ID, help="Numeric Telegram chat_id used in the required multi-target deliver string")
    parser.add_argument("--weixin-chat-id", default=DEFAULT_WEIXIN_CHAT_ID, help="Explicit Weixin chat_id used in the required multi-target deliver string")
    parser.add_argument(
        "--required-deliver",
        default=None,
        help=(
            "Strict mode: every active recurring job must use this exact comma-separated deliver string. "
            "Defaults to telegram:<telegram-chat-id>,weixin:<weixin-chat-id>."
        ),
    )
    args = parser.parse_args(argv)

    required_deliver = args.required_deliver or ",".join(
        (_explicit_telegram_target(args.telegram_chat_id), _explicit_weixin_target(args.weixin_chat_id))
    )
    jobs = load_jobs_file(args.jobs_file)
    issues = audit_jobs(
        jobs,
        telegram_chat_id=args.telegram_chat_id,
        weixin_chat_id=args.weixin_chat_id,
        required_deliver=required_deliver,
    )
    _print_audit(issues)
    return 1 if issues else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
