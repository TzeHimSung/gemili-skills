---
name: cron-multi-platform-delivery
description: Configure a cron job to deliver output to multiple messaging platforms (WeChat, QQ, Telegram) when the deliver field only supports a single target.
---

# Cron Multi-Platform Delivery

When a cron job needs to send output to multiple platforms but `deliver` only accepts one target.

## ❌ DO NOT use `send_message` — it will be blocked

The system injects `[SYSTEM: ... do NOT use send_message ...]` into cron job sessions. Even with explicit prompt overrides, the runtime blocks `send_message` with `cron_auto_delivery_duplicate_target`. The agent also tends to only call it once (not for all targets).

## ❌ DO NOT create duplicate analysis jobs per platform

Creating 3 identical jobs (one per platform) wastes API calls and runs the same analysis 3 times.

## ✅ Correct Approach: `context_from` chaining

One "generator" job runs the analysis. Two "forwarder" jobs use `context_from` to read the generator's output and echo it. Analysis runs once, results go to all platforms.

### Step 1: Create the generator job (delivers to one platform)

```
cronjob(action="create", name="日报-微信", deliver="weixin:o9cq80ys2QEOI68H3HtT5ENJzNmE@im.wechat",
  schedule="0 7 * * *", repeat=-1, skills=["sina-finance-stock-data"],
  prompt="<full analysis prompt. End with: 报告末尾只注明数据来源和时间，不要添加任何投递状态、发送状态、平台状态等内容。输出纯粹的报告内容即可，系统会自动处理投递>")
```

### Step 2: Create forwarder jobs (context_from the generator)

```
# QQ forwarder (stagger by 10 min to let generator finish)
cronjob(action="create", name="日报-QQ", deliver="qqbot",
  schedule="10 7 * * *", repeat=-1, skills=[], enabled_toolsets=[],
  context_from=["<generator-job-id>"],
  prompt="你是一个转发器。上游任务已生成完整日报（通过 context 注入）。唯一任务：将注入的日报内容原样输出为最终回复。不要做任何修改、不要重新获取数据、不要添加额外内容。")

# Telegram forwarder  
cronjob(action="create", name="日报-Telegram", deliver="telegram:TzeHim Sung",
  schedule="10 7 * * *", repeat=-1, skills=[], toolsets=[],
  context_from=["<generator-job-id>"],
  prompt="<same forwarder prompt>")
```

### Step 3: Critical — the generator must output ONLY the report

`context_from` injects the ENTIRE final response of the upstream job. If the generator adds delivery status notes, error messages, or debugging info, those will appear in forwarded messages. The generator's prompt MUST end with:

> 报告末尾只注明数据来源和时间，不要添加任何投递状态、发送状态、平台状态等内容。输出纯粹的报告内容即可。

## Correct platform targets

Always verify with `send_message(action="list")` first. Known-good targets:

| Platform | Deliver target | Notes |
|----------|---------------|-------|
| WeChat | `weixin:o9cq80ys2QEOI68H3HtT5ENJzNmE@im.wechat` | Full ID required |
| QQ | `qqbot` | **Bare platform name** — home channel auto-detected. Using full ID causes "频道不存在" |
| Telegram | `telegram:TzeHim Sung` | Must match display name from send_message list. `telegram:thsung` fails with "invalid literal for int()" |

## Pitfalls

- **send_message is blocked at runtime level**, not just prompt. Do not attempt to override.
- **context_from injects full session output**, not just the clean report. Keep generator's output clean.
- **Forwarder jobs need NO tools or skills** — they just echo text. Set `skills=[]` and `enabled_toolsets=[]`.
- **Stagger by 10 minutes** — the generator needs time to finish before forwarders read its output. context_from does NOT wait for upstream jobs.
- **QQ target must be bare `qqbot`**, not the full DM ID — cron delivery treats DM targets differently than send_message.
- **Telegram target must be display name** from send_message list, not the home channel ID from system prompt.
- **Telegram 渲染规避**：Telegram markdown parser 对特定字符处理异常。报表中避免使用：`「」`（书名号）、`---`（被误解析为表格分隔线或 hr）、`｜`（全角竖线 U+FF5C 可能被当成表格列分隔符）、列数不匹配的表格（表头 N 列但数据行 N+1 列会整表炸掉）。用 `「」` 替换为 `[]` 或无括号、`---` 用空行代替、`｜` 用 `·` 代替。
- **Complex browser/data tasks may silently fail**: Jobs requiring 10+ browser navigations or web fetches can die mid-execution with only a todo list in the session. Session state shows "unknown", agent log has only a startup line. Mitigate by: (a) using `delegate_task` to parallelize per-franchise research, (b) keeping the generator prompt concise with clear numbered steps, (c) testing manually before relying on the schedule.
