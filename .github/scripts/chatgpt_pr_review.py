#!/usr/bin/env python3
"""Post a ChatGPT review comment for a GitHub pull request.

This script intentionally uses only the Python standard library so the workflow
has no third-party action or pip-install dependency. It fails closed: if GitHub
or OpenAI calls fail, the workflow fails instead of producing a fake-green check.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

GITHUB_API = "https://api.github.com"
OPENAI_API = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_DIFF_CHARS = 60000


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is empty")
    return value


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: Any | None = None,
    timeout: int = 60,
) -> Any:
    data = None
    merged = {"Accept": "application/vnd.github+json", "User-Agent": "gemili-skills-chatgpt-review"}
    if headers:
        merged.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        merged.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=merged, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc


def request_text(url: str, *, headers: dict[str, str], timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc


def github_headers(token: str, accept: str = "application/vnd.github+json") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gemili-skills-chatgpt-review",
    }


def build_prompt(pr: dict[str, Any], diff: str, diff_truncated: bool) -> list[dict[str, str]]:
    custom_prompt = os.environ.get("CUSTOM_PROMPT", "").strip() or (
        "你是 TzeHimSung/gemili-skills 仓库的代码审查员。请用中文审查这个 PR diff。"
    )
    truncation_note = (
        "\n\n注意：diff 因长度限制已截断，请在结论中明确说明审查范围受限。"
        if diff_truncated
        else ""
    )
    user = f"""请审查以下 Pull Request。只基于 diff 给出结论，不要臆造未看到的文件内容。{truncation_note}

PR: #{pr.get('number')} {pr.get('title', '')}
Author: {(pr.get('user') or {}).get('login', '')}
Base: {(pr.get('base') or {}).get('ref', '')}
Head: {(pr.get('head') or {}).get('ref', '')}

输出要求：
- 先给一个总体结论。
- 再按“必须修复 / 建议改进 / 可接受”分组列出发现。
- 没有问题时明确说明未发现阻塞问题，不要编造风险。
- 如果发现硬编码 secret、真实投递 ID、明显逻辑错误或 CI 假绿，请放入“必须修复”。

PR diff:
```diff
{diff}
```
"""
    return [
        {"role": "system", "content": custom_prompt},
        {"role": "user", "content": user},
    ]


def call_openai(api_key: str, messages: list[dict[str, str]]) -> str:
    model = os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(os.environ.get("OPENAI_TEMPERATURE", "0.2")),
        "max_tokens": int(os.environ.get("OPENAI_MAX_TOKENS", "2048")),
    }
    response = request_json(
        OPENAI_API,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body=payload,
        timeout=120,
    )
    try:
        content = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response shape: {json.dumps(response)[:1000]}") from exc
    if not content:
        raise RuntimeError("OpenAI returned an empty review")
    return content


def post_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    marker = "<!-- gemili-skills-chatgpt-review -->"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    comment = f"{marker}\n## ChatGPT PR Review\n\n{body}\n\n---\nGenerated at {timestamp}."
    comments = request_json(
        f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments?per_page=100",
        headers=github_headers(token),
        timeout=60,
    )
    existing = next(
        (
            item
            for item in comments
            if isinstance(item, dict)
            and marker in str(item.get("body", ""))
            and ((item.get("user") or {}).get("type") == "Bot")
        ),
        None,
    )
    if existing and existing.get("id"):
        request_json(
            f"{GITHUB_API}/repos/{repo}/issues/comments/{existing['id']}",
            method="PATCH",
            headers=github_headers(token),
            body={"body": comment},
            timeout=60,
        )
        return
    request_json(
        f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
        method="POST",
        headers=github_headers(token),
        body={"body": comment},
        timeout=60,
    )


def main() -> int:
    repo = require_env("GITHUB_REPOSITORY")
    pr_number = require_env("PR_NUMBER")
    if not re.fullmatch(r"[1-9][0-9]*", pr_number):
        raise RuntimeError(f"PR_NUMBER must be a positive integer, got {pr_number!r}")
    github_token = require_env("GITHUB_TOKEN")
    openai_key = require_env("OPENAI_API_KEY")

    pr = request_json(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers=github_headers(github_token),
        timeout=60,
    )
    diff = request_text(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers=github_headers(github_token, "application/vnd.github.v3.diff"),
        timeout=60,
    )
    if not diff.strip():
        raise RuntimeError(f"PR #{pr_number} diff is empty; refusing to post an empty review")

    max_chars = int(os.environ.get("MAX_DIFF_CHARS", str(DEFAULT_MAX_DIFF_CHARS)))
    diff_truncated = len(diff) > max_chars
    if diff_truncated:
        diff = diff[:max_chars] + "\n\n[DIFF TRUNCATED BY chatgpt_pr_review.py]\n"

    review = call_openai(openai_key, build_prompt(pr, diff, diff_truncated))
    post_comment(repo, pr_number, github_token, review)
    print(f"Posted ChatGPT review comment for {repo}#{pr_number} using {os.environ.get('OPENAI_MODEL', DEFAULT_MODEL)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # fail closed with clear logs
        print(f"::error::{exc}", file=sys.stderr)
        raise SystemExit(1)
