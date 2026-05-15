from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "chatgpt-review.yml"
SCRIPT = ROOT / ".github" / "scripts" / "chatgpt_pr_review.py"


def _load_review_script():
    spec = importlib.util.spec_from_file_location("chatgpt_pr_review_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["chatgpt_pr_review_under_test"] = module
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8") if not isinstance(body, str) else body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def test_chatgpt_review_workflow_uses_local_fail_closed_script():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "cirolini/genai-code-review" not in text
    assert "continue-on-error" not in text
    assert "pull_request_target:" in text
    assert "github.event.pull_request.base.sha" in text
    assert "python3 .github/scripts/chatgpt_pr_review.py" in text
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in text


def test_chatgpt_review_sanitizes_provider_error_details():
    review = _load_review_script()

    detail = (
        'Incorrect API key provided: sk-live_ABC123xyz. '
        'Observed masked provider echo: sk-70227***********************3ac8. '
        'Authorization: Bearer ghp_secret123'
    )

    assert review.sanitize_error_detail(detail) == (
        'Incorrect API key provided: [OPENAI_KEY_REDACTED] '
        'Observed masked provider echo: [OPENAI_KEY_REDACTED] '
        'Authorization: Bearer [REDACTED]'
    )


def test_chatgpt_review_script_posts_comment(monkeypatch):
    review = _load_review_script()
    posted_comments = []
    calls = []

    def fake_urlopen(req, timeout=60):
        calls.append((req.get_method(), req.full_url, req.data))
        if req.full_url.endswith("/pulls/7") and req.get_method() == "GET":
            accept = req.headers.get("Accept", "")
            if "diff" in accept:
                return _FakeResponse("diff --git a/file.py b/file.py\n+print('ok')\n")
            return _FakeResponse({
                "number": 7,
                "title": "demo",
                "user": {"login": "alice"},
                "base": {"ref": "main"},
                "head": {"ref": "fix/demo"},
            })
        if req.full_url == review.OPENAI_API and req.get_method() == "POST":
            payload = json.loads(req.data.decode("utf-8"))
            assert payload["model"] == "gpt-test"
            assert "diff --git" in payload["messages"][1]["content"]
            return _FakeResponse({"choices": [{"message": {"content": "未发现阻塞问题。"}}]})
        if req.full_url.endswith("/issues/7/comments?per_page=100") and req.get_method() == "GET":
            return _FakeResponse([])
        if req.full_url.endswith("/issues/7/comments") and req.get_method() == "POST":
            posted_comments.append(json.loads(req.data.decode("utf-8"))["body"])
            return _FakeResponse({"id": 123})
        raise AssertionError(f"unexpected request: {req.get_method()} {req.full_url}")

    monkeypatch.setenv("GITHUB_REPOSITORY", "TzeHimSung/gemili-skills")
    monkeypatch.setenv("PR_NUMBER", "7")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setattr(review.urllib.request, "urlopen", fake_urlopen)

    assert review.main() == 0

    assert [method for method, _url, _data in calls] == ["GET", "GET", "POST", "GET", "POST"]
    assert len(posted_comments) == 1
    assert "<!-- gemili-skills-chatgpt-review -->" in posted_comments[0]
    assert "未发现阻塞问题。" in posted_comments[0]
