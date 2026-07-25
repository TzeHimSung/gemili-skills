from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cron_rate_safe_delivery import (  # noqa: E402
    DeliveryResult,
    DeliveryTargets,
    _load_runtime_env,
    compact_weixin_text,
    deliver_rate_safe,
    load_delivery_targets,
)


class FakeClock:
    def __init__(self, value: float) -> None:
        self.value = value
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def _targets() -> DeliveryTargets:
    return DeliveryTargets(
        telegram="telegram:[REDACTED]",
        weixin="weixin:[REDACTED]",
    )


def _write_context_token(hermes_home: Path, token: str) -> None:
    path = hermes_home / "weixin" / "accounts" / "bot.context-tokens.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"[REDACTED]": token}), encoding="utf-8")


def test_runtime_env_loads_adapter_credentials_for_standalone_cron(
    tmp_path,
    monkeypatch,
):
    env_key = "HERMES_CRON_DELIVERY_TEST_CREDENTIAL"
    (tmp_path / ".env").write_text(
        f"{env_key}=loaded-from-private-env\n",
        encoding="utf-8",
    )
    monkeypatch.delenv(env_key, raising=False)

    _load_runtime_env(hermes_home=tmp_path)

    assert os.environ[env_key] == "loaded-from-private-env"


def test_delivery_targets_can_come_from_private_dotenv(tmp_path, monkeypatch):
    keys = (
        "HERMES_DELIVERY_TELEGRAM_CHAT_ID",
        "HERMES_DELIVERY_WEIXIN_CHAT_ID",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(f"{key}=[REDACTED]" for key in keys) + "\n",
        encoding="utf-8",
    )

    targets = load_delivery_targets(hermes_home=tmp_path)

    assert targets.telegram == "telegram:[REDACTED]"
    assert targets.weixin == "weixin:[REDACTED]"


def test_rate_safe_delivery_sends_exactly_one_weixin_message(tmp_path, capsys):
    calls: list[tuple[str, str]] = []

    result = deliver_rate_safe(
        telegram_messages=["telegram one", "telegram two"],
        weixin_message="one compact Weixin digest",
        targets=_targets(),
        send_one=lambda target, message: calls.append((target, message)) or {"success": True},
        state_dir=tmp_path,
        min_weixin_interval=0,
    )

    assert result.ok is True
    assert result.sent == {"telegram": 2, "weixin": 1}
    assert [message for target, message in calls if target.startswith("weixin:")] == [
        "one compact Weixin digest"
    ]
    assert capsys.readouterr().out == ""


def test_rate_safe_delivery_rejects_oversized_weixin_but_finishes_telegram(tmp_path):
    calls: list[tuple[str, str]] = []

    result = deliver_rate_safe(
        telegram_messages=["full telegram report"],
        weixin_message="x" * 1801,
        targets=_targets(),
        send_one=lambda target, message: calls.append((target, message)) or {"success": True},
        state_dir=tmp_path,
        min_weixin_interval=0,
    )

    assert result.ok is False
    assert result.sent == {"telegram": 1, "weixin": 0}
    assert [target for target, _ in calls] == ["telegram:[REDACTED]"]
    assert "1800" in result.errors["weixin"]


def test_rate_safe_delivery_defers_weixin_rate_limit_without_failing_job(tmp_path):
    calls: list[str] = []
    _write_context_token(tmp_path, "context-v1")

    def send_one(target: str, _message: str):
        calls.append(target)
        if target.startswith("weixin:"):
            raise RuntimeError("iLink sendmessage rate limited")
        return {"success": True}

    result = deliver_rate_safe(
        telegram_messages=["one", "two"],
        weixin_message="digest",
        targets=_targets(),
        send_one=send_one,
        state_dir=tmp_path / "cron",
        hermes_home=tmp_path,
        job_name="test-report",
        min_weixin_interval=0,
    )

    assert result.ok is True
    assert result.sent["telegram"] == 2
    assert result.sent["weixin"] == 0
    assert result.deferred["weixin"] == 1
    assert calls.count("weixin:[REDACTED]") == 1
    assert "weixin" not in result.errors

    state = json.loads(
        (tmp_path / "cron" / "weixin_content_delivery_state.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(state["pending"]) == 1
    assert state["pending"][0]["job_name"] == "test-report"


def test_same_blocked_context_skips_network_and_deduplicates_pending(tmp_path):
    calls: list[str] = []
    _write_context_token(tmp_path, "context-v1")

    def send_one(target: str, _message: str):
        calls.append(target)
        raise RuntimeError("iLink sendmessage rate limited")

    kwargs = {
        "telegram_messages": [],
        "weixin_message": "digest",
        "targets": _targets(),
        "send_one": send_one,
        "state_dir": tmp_path / "cron",
        "hermes_home": tmp_path,
        "job_name": "test-report",
        "min_weixin_interval": 0,
    }

    first = deliver_rate_safe(**kwargs)
    second = deliver_rate_safe(**kwargs)

    assert first.deferred["weixin"] == 1
    assert second.deferred["weixin"] == 1
    assert calls == ["weixin:[REDACTED]"]
    state = json.loads(
        (tmp_path / "cron" / "weixin_content_delivery_state.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(state["pending"]) == 1


def test_new_context_flushes_pending_as_one_combined_digest(tmp_path):
    calls: list[tuple[str, str]] = []
    _write_context_token(tmp_path, "context-v1")

    def first_send(target: str, message: str):
        calls.append((target, message))
        raise RuntimeError("iLink sendmessage rate limited")

    common = {
        "telegram_messages": [],
        "targets": _targets(),
        "state_dir": tmp_path / "cron",
        "hermes_home": tmp_path,
        "min_weixin_interval": 0,
    }
    deferred = deliver_rate_safe(
        **common,
        weixin_message="older digest",
        send_one=first_send,
        job_name="older-report",
    )
    assert deferred.deferred["weixin"] == 1

    _write_context_token(tmp_path, "context-v2")
    calls.clear()

    delivered = deliver_rate_safe(
        **common,
        weixin_message="new digest",
        send_one=lambda target, message: calls.append((target, message))
        or {"success": True},
        job_name="new-report",
    )

    assert delivered.ok is True
    assert delivered.sent["weixin"] == 1
    assert delivered.deferred["weixin"] == 0
    assert len(calls) == 1
    assert "older digest" in calls[0][1]
    assert "new digest" in calls[0][1]
    assert len(calls[0][1]) <= 1800
    state = json.loads(
        (tmp_path / "cron" / "weixin_content_delivery_state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["pending"] == []


def test_old_context_is_deferred_without_network_request(tmp_path):
    _write_context_token(tmp_path, "context-v1")
    token_path = tmp_path / "weixin" / "accounts" / "bot.context-tokens.json"
    os.utime(token_path, (100.0, 100.0))
    calls: list[str] = []

    result = deliver_rate_safe(
        telegram_messages=[],
        weixin_message="digest",
        targets=_targets(),
        send_one=lambda target, _message: calls.append(target) or {"success": True},
        state_dir=tmp_path / "cron",
        hermes_home=tmp_path,
        job_name="old-context-report",
        min_weixin_interval=0,
        max_weixin_context_age=20 * 60 * 60,
        clock=lambda: 100.0 + 20 * 60 * 60 + 1,
    )

    assert result.ok is True
    assert result.deferred["weixin"] == 1
    assert calls == []


def test_cron_send_budget_caps_requests_per_context(tmp_path):
    _write_context_token(tmp_path, "context-v1")
    calls: list[str] = []
    results: list[DeliveryResult] = []

    for index in range(6):
        results.append(deliver_rate_safe(
            telegram_messages=[],
            weixin_message=f"digest-{index}",
            targets=_targets(),
            send_one=lambda target, _message: calls.append(target) or {"success": True},
            state_dir=tmp_path / "cron",
            hermes_home=tmp_path,
            job_name=f"report-{index}",
            min_weixin_interval=0,
            max_weixin_sends_per_context=5,
        ))

    assert len(calls) == 5
    assert results[-1].deferred["weixin"] == 1


def test_idempotency_key_includes_local_delivery_date(tmp_path):
    calls: list[str] = []
    clock = FakeClock(100)
    kwargs = {
        "telegram_messages": [],
        "weixin_message": "same digest",
        "targets": _targets(),
        "send_one": lambda target, _message: calls.append(target) or {"success": True},
        "state_dir": tmp_path / "state",
        "hermes_home": tmp_path,
        "job_name": "daily",
        "min_weixin_interval": 0,
        "clock": clock.now,
        "sleep": clock.sleep,
    }

    assert deliver_rate_safe(**kwargs).sent["weixin"] == 1
    assert deliver_rate_safe(**kwargs).sent["weixin"] == 0
    clock.value += 24 * 60 * 60
    assert deliver_rate_safe(**kwargs).sent["weixin"] == 1
    assert calls == ["weixin:[REDACTED]", "weixin:[REDACTED]"]


def test_weixin_gate_waits_between_successful_cron_deliveries(tmp_path):
    clock = FakeClock(100.0)
    kwargs = {
        "telegram_messages": [],
        "weixin_message": "digest",
        "targets": _targets(),
        "send_one": lambda _target, _message: {"success": True},
        "state_dir": tmp_path,
        "min_weixin_interval": 30,
        "clock": clock.now,
        "sleep": clock.sleep,
    }

    assert deliver_rate_safe(**kwargs).ok is True
    clock.value += 5
    kwargs["weixin_message"] = "digest-2"
    assert deliver_rate_safe(**kwargs).ok is True

    assert clock.sleeps == [25.0]


@pytest.mark.skipif(os.name == "nt", reason="Hermes cron runs on a POSIX NAS")
def test_weixin_gate_serializes_independent_processes(tmp_path):
    script = f"""
import sys
import time
sys.path.insert(0, {str(SCRIPTS)!r})
from cron_rate_safe_delivery import _WeixinRateGate
with _WeixinRateGate(
    state_dir=__import__('pathlib').Path(sys.argv[1]),
    min_interval=0,
    clock=time.time,
    sleep=time.sleep,
):
    print('locked', flush=True)
    time.sleep(float(sys.argv[2]))
"""
    first = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path), "0.3"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert first.stdout is not None
    assert first.stdout.readline().strip() == "locked"

    second = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path), "0"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.1)
        assert second.poll() is None
        assert first.wait(timeout=2) == 0
        assert second.communicate(timeout=2)[0].strip() == "locked"
        assert second.returncode == 0
    finally:
        first.kill()
        second.kill()


def test_compact_weixin_text_is_deterministic_and_bounded():
    source = "\n\n".join(f"section {idx} " + ("x" * 350) for idx in range(10))

    compact = compact_weixin_text(source, max_chars=1800)

    assert len(compact) <= 1800
    assert compact.startswith("section 0")
    assert "完整内容已发送至 Telegram" in compact
