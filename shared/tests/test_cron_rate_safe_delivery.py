from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cron_rate_safe_delivery import (  # noqa: E402
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


def test_rate_safe_delivery_does_not_retry_weixin_and_isolates_platform_failure(tmp_path):
    calls: list[str] = []

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
        state_dir=tmp_path,
        min_weixin_interval=0,
    )

    assert result.ok is False
    assert result.sent["telegram"] == 2
    assert result.sent["weixin"] == 0
    assert calls.count("weixin:[REDACTED]") == 1
    assert "rate limited" in result.errors["weixin"]


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
