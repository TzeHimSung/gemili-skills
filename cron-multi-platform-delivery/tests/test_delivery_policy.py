import sys
from pathlib import Path

# Tests must not depend on the user's private ~/.hermes/secrets delivery targets.
import os

os.environ["HERMES_DELIVERY_TELEGRAM_CHAT_ID"] = "12345"
os.environ["HERMES_DELIVERY_WEIXIN_CHAT_ID"] = "wx-test-id"

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import delivery_policy

TELEGRAM = "telegram:12345"
WEIXIN = "weixin:wx-test-id"
DUAL = f"{TELEGRAM},{WEIXIN}"


def test_explicit_dual_target_is_valid():
    job = {
        "id": "ok1",
        "name": "日报",
        "deliver": DUAL,
        "origin": {"platform": "weixin", "chat_id": "o9xxx@im.wechat"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job)

    assert decision.ok is True
    assert decision.recommended_deliver == DUAL
    assert decision.reason == "explicit delivery target(s)"


def test_origin_is_rejected_because_it_cannot_dual_deliver():
    job = {
        "id": "bad1",
        "name": "美股日报",
        "deliver": "origin",
        "origin": {"platform": "weixin", "chat_id": "o9xxx@im.wechat"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job)

    assert decision.ok is False
    assert decision.recommended_deliver == DUAL
    assert "origin can resolve to only one platform" in decision.reason


def test_bare_telegram_is_rejected_because_home_id_can_be_non_numeric():
    job = {
        "id": "bad2",
        "name": "Yahoo JP",
        "deliver": "telegram",
        "origin": {"platform": "telegram", "chat_id": "12345"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job)

    assert decision.ok is False
    assert decision.recommended_deliver == DUAL
    assert "bare telegram" in decision.reason


def test_named_telegram_rejection_message_uses_redacted_placeholder():
    named_target = "telegram:" + "Some User Name"
    job = {
        "id": "bad-display-name",
        "name": "Yahoo JP",
        "deliver": named_target,
        "origin": {"platform": "telegram", "chat_id": "12345"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job)

    assert decision.ok is False
    assert named_target not in decision.reason
    assert "telegram:<display-name>" in decision.reason
    assert "TzeHim" not in decision.reason


def test_explicit_single_telegram_target_is_valid_without_strict_mode():
    job = {
        "id": "ok2",
        "name": "迁移后的美股日报",
        "deliver": TELEGRAM,
        "origin": {"platform": "weixin", "chat_id": "o9xxx@im.wechat"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job)

    assert decision.ok is True
    assert decision.recommended_deliver == TELEGRAM


def test_strict_required_deliver_rejects_single_telegram_target():
    job = {
        "id": "strict1",
        "name": "旧 Telegram 单投递任务",
        "deliver": TELEGRAM,
        "origin": {"platform": "telegram", "chat_id": "12345"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job, required_deliver=DUAL)

    assert decision.ok is False
    assert decision.recommended_deliver == DUAL
    assert "required deliver target" in decision.reason


def test_strict_required_deliver_allows_exact_dual_target():
    job = {
        "id": "strict2",
        "name": "标准双投递任务",
        "deliver": DUAL,
        "origin": {"platform": "telegram", "chat_id": "12345"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job, required_deliver=DUAL)

    assert decision.ok is True
    assert decision.recommended_deliver == DUAL


def test_audit_jobs_reports_only_active_delivery_policy_violations():
    jobs = [
        {
            "id": "bad1",
            "name": "美股日报",
            "deliver": "origin",
            "origin": {"platform": "weixin", "chat_id": "o9xxx@im.wechat"},
            "enabled": True,
            "repeat": {"times": None},
        },
        {
            "id": "ok1",
            "name": "中港股日报",
            "deliver": DUAL,
            "origin": {"platform": "telegram", "chat_id": "12345"},
            "enabled": True,
            "repeat": {"times": None},
        },
        {
            "id": "ignored",
            "name": "暂停任务",
            "deliver": "weixin",
            "origin": {"platform": "weixin", "chat_id": "o9xxx@im.wechat"},
            "enabled": False,
            "repeat": {"times": None},
        },
    ]

    issues = delivery_policy.audit_jobs(jobs, required_deliver=DUAL)

    assert len(issues) == 1
    assert issues[0].job_id == "bad1"
    assert issues[0].recommended_deliver == DUAL


def test_audit_jobs_ignores_iso_timestamp_one_shot_schedule_with_repeat_none():
    jobs = [
        {
            "id": "one-shot",
            "name": "一次性提醒",
            "schedule": "2026-05-19T12:00:00+08:00",
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "12345"},
            "enabled": True,
            "repeat": None,
        }
    ]

    issues = delivery_policy.audit_jobs(jobs, required_deliver=DUAL)

    assert issues == []


def test_audit_jobs_treats_cron_every_and_duration_schedules_as_recurring():
    jobs = [
        {
            "id": f"recurring-{index}",
            "name": "循环任务",
            "schedule": schedule,
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "12345"},
            "enabled": True,
            "repeat": None,
        }
        for index, schedule in enumerate(["0 7 * * *", "every 30 minutes", "30m"], start=1)
    ]

    issues = delivery_policy.audit_jobs(jobs, required_deliver=DUAL)

    assert [issue.job_id for issue in issues] == ["recurring-1", "recurring-2", "recurring-3"]


def test_build_create_kwargs_defaults_to_enforced_dual_delivery():
    kwargs = delivery_policy.build_create_kwargs(
        name="测试日报",
        skill="example-skill",
        prompt="生成报告",
        schedule="0 7 * * *",
    )

    assert kwargs["action"] == "create"
    assert kwargs["name"] == "测试日报"
    assert kwargs["skills"] == ["example-skill"]
    assert "repeat" not in kwargs
    assert kwargs["deliver"] == DUAL


def test_strict_audit_allows_only_local_guard_and_exact_local_maintenance_jobs():
    jobs = [
        {
            "id": "guard",
            "name": "Cron投递策略守卫",
            "skill": "cron-multi-platform-delivery",
            "skills": ["cron-multi-platform-delivery"],
            "deliver": "local",
            "enabled": True,
            "repeat": {"times": None},
        },
        {
            "id": "silent-maintenance",
            "name": "Fedora 软件包每日更新",
            "skill": "update-fedora-packages",
            "skills": ["update-fedora-packages"],
            "deliver": "local",
            "enabled": True,
            "repeat": {"times": None},
        },
        {
            "id": "strict2",
            "name": "标准任务",
            "deliver": DUAL,
            "origin": {"platform": "telegram", "chat_id": "12345"},
            "enabled": True,
            "repeat": {"times": None},
        },
    ]

    issues = delivery_policy.audit_jobs(jobs, required_deliver=DUAL)

    assert issues == []


def test_strict_audit_flags_nonlocal_delivery_on_local_only_system_jobs():
    jobs = [
        {
            "id": "guard",
            "name": "Cron投递策略守卫",
            "skill": "cron-multi-platform-delivery",
            "skills": ["cron-multi-platform-delivery"],
            "deliver": DUAL,
            "enabled": True,
            "repeat": {"times": None},
        },
        {
            "id": "maintenance",
            "name": "Fedora 软件包每日更新",
            "skill": "update-fedora-packages",
            "skills": ["update-fedora-packages"],
            "deliver": "origin",
            "enabled": True,
            "repeat": {"times": None},
        },
    ]

    issues = delivery_policy.audit_jobs(jobs, required_deliver=DUAL)

    assert [issue.job_id for issue in issues] == ["guard", "maintenance"]
    assert all(issue.recommended_deliver == "local" for issue in issues)
    assert all("local-only system job" in issue.reason for issue in issues)


def test_strict_audit_does_not_allow_mixed_content_job_to_escape_via_maintenance_skill():
    jobs = [
        {
            "id": "mixed-content",
            "name": "内容任务混入维护 skill",
            "skill": "yahoo-jp-roast",
            "skills": ["yahoo-jp-roast", "update-fedora-packages"],
            "deliver": "local",
            "enabled": True,
            "repeat": {"times": None},
        }
    ]

    issues = delivery_policy.audit_jobs(jobs, required_deliver=DUAL)

    assert len(issues) == 1
    assert issues[0].job_id == "mixed-content"
    assert issues[0].recommended_deliver == DUAL
    assert "required deliver target" in issues[0].reason


def test_strict_audit_does_not_allow_content_job_to_escape_by_using_guard_name():
    jobs = [
        {
            "id": "fake-guard-content",
            "name": "Cron投递策略守卫",
            "skill": "yahoo-jp-roast",
            "skills": ["yahoo-jp-roast", "cron-multi-platform-delivery"],
            "deliver": "local",
            "enabled": True,
            "repeat": {"times": None},
        }
    ]

    issues = delivery_policy.audit_jobs(jobs, required_deliver=DUAL)

    assert len(issues) == 1
    assert issues[0].job_id == "fake-guard-content"
    assert issues[0].recommended_deliver == DUAL
    assert "required deliver target" in issues[0].reason


def test_cli_default_required_deliver_flags_single_telegram(tmp_path):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(
        '{"jobs":[{"id":"old","name":"旧任务","deliver":"telegram:12345","enabled":true,"repeat":{"times":null}}]}',
        encoding="utf-8",
    )

    assert delivery_policy.main([str(jobs_file)]) == 1


def test_cli_live_default_without_env_or_secret_fails_closed_without_dummy_target(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("HERMES_DELIVERY_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("HERMES_DELIVERY_WEIXIN_CHAT_ID", raising=False)
    monkeypatch.setattr(delivery_policy, "SECRETS_PATH", tmp_path / "missing-secrets.json")
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(
        '{"jobs":[{"id":"bad","name":"旧任务","deliver":"origin","enabled":true,"repeat":{"times":null}}]}',
        encoding="utf-8",
    )

    exit_code = delivery_policy.main([str(jobs_file)])
    captured = capsys.readouterr()
    combined_output = captured.out + captured.err

    assert exit_code != 0
    assert "configuration error" in combined_output
    assert "telegram:12345" not in combined_output
    assert "weixin:wx-test-id" not in combined_output


def test_cli_invalid_env_target_error_does_not_echo_secret_value(tmp_path, monkeypatch, capsys):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text('{"jobs": []}', encoding="utf-8")
    invalid_target_value = "not-a-numeric-telegram-chat-id-value"
    monkeypatch.setenv("HERMES_DELIVERY_TELEGRAM_CHAT_ID", invalid_target_value)
    monkeypatch.setenv("HERMES_DELIVERY_WEIXIN_CHAT_ID", "wx-test-id")

    exit_code = delivery_policy.main([str(jobs_file)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "telegram_chat_id must be numeric" in captured.err
    assert invalid_target_value not in captured.err


def test_cli_invalid_required_deliver_error_does_not_echo_named_target(tmp_path, capsys):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text('{"jobs": []}', encoding="utf-8")
    named_target = "telegram:" + "Some User Name"

    exit_code = delivery_policy.main([str(jobs_file), "--required-deliver", named_target])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert named_target not in captured.err
    assert "telegram:[REDACTED]" in captured.err


def test_print_audit_redacts_current_and_recommended_delivery_targets(capsys):
    current_telegram = "telegram:" + "123456789"
    current_named_telegram = "telegram:" + "Some User Name"
    current_unicode_telegram = "telegram:" + "張三"
    current_underscore_telegram = "telegram:" + "_SomeUser"
    current_weixin = "weixin:" + "wx-real" + "@im.wechat"
    recommended_telegram = "telegram:" + "987654321"
    recommended_weixin = "weixin:" + "wx-fixed" + "@im.wechat"
    issue = delivery_policy.DeliveryIssue(
        job_id="bad",
        name="旧任务",
        current_deliver=f"{current_telegram},{current_named_telegram},{current_unicode_telegram},{current_underscore_telegram},{current_weixin}",
        recommended_deliver=f"{recommended_telegram},{recommended_weixin}",
        reason=(
            f"required deliver target is {recommended_telegram},{recommended_weixin}; "
            f"got {current_telegram},{current_named_telegram},{current_unicode_telegram},{current_underscore_telegram},{current_weixin}"
        ),
    )

    delivery_policy._print_audit([issue])
    output = capsys.readouterr().out

    assert "123456789" not in output
    assert "987654321" not in output
    assert "Some User Name" not in output
    assert "張三" not in output
    assert "_SomeUser" not in output
    assert "wx-real" not in output
    assert "wx-fixed" not in output
    assert "telegram:[REDACTED]" in output
    assert "weixin:[REDACTED]" in output


def test_cli_default_required_deliver_accepts_dual_target(tmp_path):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(
        f'{{"jobs":[{{"id":"new","name":"新任务","deliver":"{DUAL}","enabled":true,"repeat":{{"times":null}}}}]}}',
        encoding="utf-8",
    )

    assert delivery_policy.main([str(jobs_file)]) == 0
