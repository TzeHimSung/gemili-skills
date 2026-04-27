#!/usr/bin/env python3
"""Cron delivery policy guardrails.

This module codifies the Hermes cron delivery rules that used to live only in
SKILL.md / memory:

- New jobs should normally use ``deliver='origin'`` when created from the
  correct Telegram DM.
- ``deliver='origin'`` is only safe if the persisted job origin is Telegram and
  the Telegram chat_id is numeric.
- Migrated jobs whose origin still points to Weixin/QQ should use an explicit
  numeric Telegram target such as ``telegram:7943831495``.
- Bare ``telegram`` is unsafe in this environment because the Home channel ID
  can be the username-like string ``thsung``, which the Telegram adapter tries
  to parse as an integer chat id.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PREFERRED_NEW_JOB_DELIVER = "origin"
TELEGRAM_TARGET_RE = re.compile(r"^telegram:(?P<chat_id>-?\d+)(?::(?P<thread_id>\d+))?$")


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


def is_active_recurring_job(job: dict[str, Any]) -> bool:
    """Return True for enabled recurring jobs that should actively notify user."""

    if job.get("enabled") is False:
        return False
    repeat = job.get("repeat")
    if isinstance(repeat, dict):
        # Hermes stores forever jobs as {"times": null, "completed": N}.
        return repeat.get("times") is None
    return repeat in (None, "forever")


def evaluate_job(
    job: dict[str, Any],
    *,
    telegram_chat_id: str | None = None,
) -> DeliveryDecision:
    """Evaluate one cron job against the delivery policy.

    ``telegram_chat_id`` is used as a repair target for migrated jobs whose
    persisted origin points to Weixin/QQ. If omitted, the evaluator still flags
    the job but can only recommend ``origin`` for jobs that already have a valid
    Telegram origin.
    """

    job_id = str(job.get("id") or job.get("job_id") or "")
    name = str(job.get("name") or "")
    deliver = job.get("deliver")
    deliver_s = str(deliver) if deliver is not None else None
    origin_platform = _origin_platform(job)
    origin_chat_id = _origin_chat_id(job)

    if deliver_s is None:
        return DeliveryDecision(
            job_id,
            name,
            False,
            None,
            PREFERRED_NEW_JOB_DELIVER,
            "missing deliver target",
        )

    if deliver_s == "origin":
        if origin_platform == "telegram" and _is_numeric_chat_id(origin_chat_id):
            return DeliveryDecision(
                job_id,
                name,
                True,
                deliver_s,
                "origin",
                "origin points to numeric Telegram chat",
            )
        if telegram_chat_id:
            recommended = _explicit_telegram_target(telegram_chat_id)
        else:
            recommended = "origin"
        return DeliveryDecision(
            job_id,
            name,
            False,
            deliver_s,
            recommended,
            f"origin platform is {origin_platform or 'missing'}; origin chat_id is not a numeric Telegram chat",
        )

    if deliver_s == "telegram":
        return DeliveryDecision(
            job_id,
            name,
            False,
            deliver_s,
            PREFERRED_NEW_JOB_DELIVER,
            "bare telegram is unsafe because Home ID may be non-numeric (e.g. thsung)",
        )

    explicit_match = TELEGRAM_TARGET_RE.fullmatch(deliver_s)
    if explicit_match:
        return DeliveryDecision(
            job_id,
            name,
            True,
            deliver_s,
            deliver_s,
            "explicit numeric Telegram target",
        )

    if deliver_s.startswith("telegram:"):
        recommended = _explicit_telegram_target(telegram_chat_id) if telegram_chat_id else PREFERRED_NEW_JOB_DELIVER
        return DeliveryDecision(
            job_id,
            name,
            False,
            deliver_s,
            recommended,
            "telegram target is not numeric; names such as telegram:TzeHim Sung time out",
        )

    if deliver_s.startswith("weixin"):
        recommended = _explicit_telegram_target(telegram_chat_id) if telegram_chat_id else PREFERRED_NEW_JOB_DELIVER
        return DeliveryDecision(
            job_id,
            name,
            False,
            deliver_s,
            recommended,
            "weixin proactive delivery is blocked by asyncio context bug",
        )

    if deliver_s.startswith("qqbot"):
        recommended = _explicit_telegram_target(telegram_chat_id) if telegram_chat_id else PREFERRED_NEW_JOB_DELIVER
        return DeliveryDecision(
            job_id,
            name,
            False,
            deliver_s,
            recommended,
            "qqbot proactive delivery fails with 11263 ErrorCheckGuildAuth",
        )

    return DeliveryDecision(
        job_id,
        name,
        False,
        deliver_s,
        PREFERRED_NEW_JOB_DELIVER,
        f"unsupported deliver target: {deliver_s}",
    )


def audit_jobs(
    jobs: Iterable[dict[str, Any]],
    *,
    telegram_chat_id: str | None = None,
) -> list[DeliveryIssue]:
    """Return delivery-policy violations for enabled recurring jobs."""

    issues: list[DeliveryIssue] = []
    for job in jobs:
        if not is_active_recurring_job(job):
            continue
        decision = evaluate_job(job, telegram_chat_id=telegram_chat_id)
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
    repeat: str = "forever",
    deliver: str = PREFERRED_NEW_JOB_DELIVER,
    skills: list[str] | None = None,
) -> dict[str, Any]:
    """Build safe kwargs for Hermes ``cronjob(action='create', ...)`` calls."""

    return {
        "action": "create",
        "name": name,
        "skill": skill,
        "skills": skills or [skill],
        "prompt": prompt,
        "schedule": schedule,
        "repeat": repeat,
        "deliver": deliver,
    }


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
    parser.add_argument("--telegram-chat-id", help="Numeric Telegram chat_id used to repair migrated jobs")
    args = parser.parse_args(argv)

    jobs = load_jobs_file(args.jobs_file)
    issues = audit_jobs(jobs, telegram_chat_id=args.telegram_chat_id)
    _print_audit(issues)
    return 1 if issues else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
