import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import delivery_policy


def test_origin_with_numeric_telegram_origin_is_valid():
    job = {
        "id": "ok1",
        "name": "日报",
        "deliver": "origin",
        "origin": {"platform": "telegram", "chat_id": "7943831495"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job)

    assert decision.ok is True
    assert decision.recommended_deliver == "origin"
    assert decision.reason == "origin points to numeric Telegram chat"


def test_origin_with_weixin_origin_is_rejected_and_recommends_numeric_telegram():
    job = {
        "id": "bad1",
        "name": "美股日报",
        "deliver": "origin",
        "origin": {"platform": "weixin", "chat_id": "o9xxx@im.wechat"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job, telegram_chat_id="7943831495")

    assert decision.ok is False
    assert decision.recommended_deliver == "telegram:7943831495"
    assert "origin platform is weixin" in decision.reason


def test_bare_telegram_is_rejected_because_home_id_can_be_non_numeric():
    job = {
        "id": "bad2",
        "name": "Yahoo JP",
        "deliver": "telegram",
        "origin": {"platform": "telegram", "chat_id": "7943831495"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job)

    assert decision.ok is False
    assert decision.recommended_deliver == "telegram:7943831495"
    assert "bare telegram" in decision.reason


def test_explicit_numeric_telegram_target_is_valid_for_migrated_jobs():
    job = {
        "id": "ok2",
        "name": "迁移后的美股日报",
        "deliver": "telegram:7943831495",
        "origin": {"platform": "weixin", "chat_id": "o9xxx@im.wechat"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(job)

    assert decision.ok is True
    assert decision.recommended_deliver == "telegram:7943831495"
    assert decision.reason == "explicit numeric Telegram target"


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
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "7943831495"},
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

    issues = delivery_policy.audit_jobs(jobs, telegram_chat_id="7943831495")

    assert len(issues) == 1
    assert issues[0].job_id == "bad1"
    assert issues[0].recommended_deliver == "telegram:7943831495"


def test_build_create_kwargs_defaults_to_enforced_numeric_telegram_delivery():
    kwargs = delivery_policy.build_create_kwargs(
        name="测试日报",
        skill="example-skill",
        prompt="生成报告",
        schedule="0 7 * * *",
    )

    assert kwargs["action"] == "create"
    assert kwargs["name"] == "测试日报"
    assert kwargs["skills"] == ["example-skill"]
    assert kwargs["repeat"] == "forever"
    assert kwargs["deliver"] == "telegram:7943831495"


def test_strict_required_deliver_rejects_otherwise_valid_origin():
    job = {
        "id": "strict1",
        "name": "未来新建任务",
        "deliver": "origin",
        "origin": {"platform": "telegram", "chat_id": "7943831495"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(
        job,
        telegram_chat_id="7943831495",
        required_deliver="telegram:7943831495",
    )

    assert decision.ok is False
    assert decision.recommended_deliver == "telegram:7943831495"
    assert "required deliver target" in decision.reason


def test_strict_required_deliver_allows_only_exact_target():
    job = {
        "id": "strict2",
        "name": "标准任务",
        "deliver": "telegram:7943831495",
        "origin": {"platform": "telegram", "chat_id": "7943831495"},
        "enabled": True,
        "repeat": {"times": None},
    }

    decision = delivery_policy.evaluate_job(
        job,
        telegram_chat_id="7943831495",
        required_deliver="telegram:7943831495",
    )

    assert decision.ok is True
    assert decision.recommended_deliver == "telegram:7943831495"


def test_strict_audit_ignores_local_delivery_guard_job():
    jobs = [
        {
            "id": "guard",
            "name": "Cron投递策略守卫",
            "deliver": "local",
            "enabled": True,
            "repeat": {"times": None},
        },
        {
            "id": "strict2",
            "name": "标准任务",
            "deliver": "telegram:7943831495",
            "origin": {"platform": "telegram", "chat_id": "7943831495"},
            "enabled": True,
            "repeat": {"times": None},
        },
    ]

    issues = delivery_policy.audit_jobs(
        jobs,
        telegram_chat_id="7943831495",
        required_deliver="telegram:7943831495",
    )

    assert issues == []
