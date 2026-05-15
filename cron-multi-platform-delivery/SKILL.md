---
name: cron-multi-platform-delivery
description: 将单个 cron job 输出同时推送到 Telegram 和微信；QQ 仍不可用。
---

# Cron 投递（Telegram + 微信双投递）

## 核心结论

当前策略改为：**所有启用中的 recurring 内容任务统一使用显式、逗号分隔的双投递 target：**

```text
telegram:[REDACTED],weixin:[REDACTED]
```

实际 chat_id 由 `cron-multi-platform-delivery/scripts/delivery_policy.py` 常量与 Hermes cron 配置提供；公开文档只写脱敏示例。

Hermes cron scheduler 已支持 `deliver` 字段用逗号分隔多个目标；同一个 job 生成一次报告后会依次投递到所有解析出的目标。不要为同一日报创建 Telegram/微信两套重复 job。

| 平台/target | 状态 | 备注 |
|------|------|------|
| `telegram:[REDACTED]` | ✅ 必选 | 必须使用数字 chat_id；不要用 bare `telegram` |
| `weixin:[REDACTED]` | ✅ 必选 | 使用当前微信 DM 的显式 chat_id |
| `telegram:[REDACTED],weixin:[REDACTED]` | ✅ 标准 | 所有启用 recurring 内容任务必须精确使用 |
| `origin` | ❌ 内容任务禁用 | 只能指向创建任务时的单一来源，无法保证 Telegram+微信双投递 |
| bare `telegram` | ❌ | 当前 Home ID 可能是 `thsung`，会触发 numeric chat_id 解析问题 |
| bare `weixin` | ❌ | 依赖 Home channel；显式 chat_id 更稳定 |
| `telegram:TzeHim Sung` | ❌ | 会超时，不要用 |
| QQ / `qqbot` | ❌ | QQ bot WebSocket 断线 → `ErrorCheckGuildAuth`/11263，暂不启用 |

## 最终架构：单任务，逗号分隔双投递

```text
┌──────────────────────────┐
│ 主任务 (skill=xxx)         │
│ 生成报告一次               │
│ deliver=telegram:[REDACTED],weixin:[REDACTED] │
└──────────────────────────┘
```

**不使用转发器、不创建重复 job。** 所有 content type 各一个 cron job。后台守卫 `Cron投递策略守卫` 每 30 分钟静默审计一次，发现任何启用中的 recurring 内容任务偏离标准双投递 target，就自动改回。

## 创建示例

```python
cronjob(
  action='create',
  name='xxx日报',
  skills=['xxx-tracker'],
  prompt='加载并执行 xxx-tracker skill。生成完整报告作为最终回复。',
  schedule='0 9 * * *',
  # 不要传 repeat='forever'：cronjob.repeat 参数是整数；recurring schedule 省略 repeat 即默认 forever。
  deliver='telegram:[REDACTED],weixin:[REDACTED]',
)
```

## 已部署实例（全部 Telegram + 微信双投递）

| 任务 | skill | 时间 |
|------|-------|------|
| 美股收盘日报 | us-stock-tracker | 07:00 |
| 偶像Live倒计时 | anison-live-countdown | 09:00 |
| 中港股午市快报 | cnhk-stock-tracker | 12:00 |
| 中港股收盘日报 | cnhk-stock-tracker | 16:10 |
| Yahoo JP 锐评日报 | yahoo-jp-roast | 22:00 |

> 当前部署策略：所有启用中的 recurring 内容任务必须 `deliver='telegram:[REDACTED],weixin:[REDACTED]'`。`Cron投递策略守卫` 每 30 分钟检查并自动纠偏；守卫自身 `deliver='local'`，避免刷屏。

## 代码固化：投递策略审计

投递规则已固化为 Python 模块，真实投递 ID 不写入 Git。守卫脚本从以下来源读取真实 target：

1. 环境变量：`HERMES_DELIVERY_TELEGRAM_CHAT_ID`、`HERMES_DELIVERY_WEIXIN_CHAT_ID`；
2. 或本机私密文件：`~/.hermes/secrets/cron_delivery_targets.json`；
3. 或 CLI 显式传入 `--telegram-chat-id` / `--weixin-chat-id`。

私密文件格式：

```json
{
  "telegram_chat_id": "<numeric_chat_id>",
  "weixin_chat_id": "<explicit_weixin_chat_id>"
}
```

公开仓库与测试只能使用脱敏/假 ID，`scripts/skills_audit.py` 会阻止 `telegram:[REAL_NUMERIC_ID]` / `weixin:[REAL_CHAT_ID]` 这类未脱敏 target 入库。

投递规则模块运行方式：

```bash
python3 cron-multi-platform-delivery/scripts/delivery_policy.py ~/.hermes/cron/jobs.json
```

脚本会检查启用中的 recurring cron job：
- 启用中的 recurring 内容任务必须精确使用标准双投递 target；
- `Cron投递策略守卫` 作为例外，必须是仅加载 `cron-multi-platform-delivery` 的守卫任务，并使用 `deliver='local'` 静默运行；
- 明确的系统维护任务（例如仅加载 `update-fedora-packages` 或 `hermes-snapshot` 的任务）作为例外，必须使用 `deliver='local'` 静默运行；
- 混合内容 skill 的任务不能借 `update-fedora-packages` / `hermes-snapshot` 逃过内容投递策略；
- 禁止内容任务使用 `origin`、bare `telegram`、bare `weixin`、`telegram:TzeHim Sung`、`qqbot`；
- `build_create_kwargs()` 为新建 cron job 提供默认强制参数。

配套测试：

```bash
python3 -m pytest cron-multi-platform-delivery/tests/test_delivery_policy.py -q
```

## 手动重试与验证流程

当用户说“重试这个定时任务”且上下文指向刚失败/刚运行的 recurring job 时，按以下顺序处理，不要只调用 `cronjob(action='run')` 后就结束：

1. `cronjob(action='list')` 找到目标 job，优先选择最近 `last_run_at`、名称/上下文匹配、或 `last_delivery_error`/输出异常的任务；不要猜 job_id。
2. 确认内容任务的 `deliver` 是标准双投递 target；若不是，先 `cronjob(action='update', job_id=..., deliver='telegram:[REDACTED],weixin:[REDACTED]')`。
3. 调用 `cronjob(action='run', job_id=...)` 触发重跑。
4. 等待至少一个 scheduler tick（约 60 秒）后再次 `cronjob(action='list')` 验证：
   - `last_run_at` 是否已更新；
   - `last_status` 是否为 `ok`；
   - `last_delivery_error` 是否为 `null`。
5. 若 `next_run_at` 被设置到过去、但 `last_run_at` 长时间未更新，检查是否存在过期 tick lock：
   ```bash
   date '+%F %T %z'
   stat -c '%y %s' ~/.hermes/cron/.tick.lock
   ps -ef | grep -E 'cron|hermes_cli|目标job_id' | grep -v grep
   ```
   若 `.tick.lock` 明显陈旧且没有正在运行的 cron/job 进程，可删除：
   ```bash
   rm -f ~/.hermes/cron/.tick.lock
   ```
6. 验证实际输出文件，不只看状态：确认 `## Response` 内容不是 `API call failed...`、`[SILENT]` 或空输出。对 Yahoo JP 锐评等长报告，还要快速确认条数（例如搜索 `^## #20`）。

## 反模式

| ❌ 不要 | ✅ 用 |
|---------|------|
| 创建 Telegram/微信两套重复日报 job | 单 job 逗号分隔双投递 |
| 创建 QQ/微信转发器 | 单任务直投 `telegram:...,weixin:...` |
| 使用 bare `telegram` | `telegram:[REDACTED]` |
| 使用 bare `weixin` | `weixin:[REDACTED]` |
| 使用 `origin` 投递内容任务 | 标准双投递 target |
| 未检查任务投递 target | 运行 `delivery_policy.py`，或依赖守卫自动纠偏 |
| 创建 recurring job 时不要传 `repeat='forever'` | 省略 `repeat`；cronjob 的 `repeat` 入参是整数，recurring schedule 默认 forever |
| 为 QQ 做 retry chain | 11263 是 WebSocket 问题，retry 无效 |
| 看到 11263 就改 target 格式 | 翻官方文档查真实错误含义 |
