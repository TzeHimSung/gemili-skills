---
name: cron-multi-platform-delivery
description: 将单个 cron job 输出推送到 Telegram。QQ/微信均不可用，精简为单点 Telegram 投递。
---

# Cron 投递（Telegram Only）

## 核心结论

经过系统性排查，**主动投递强制统一为显式数字 Telegram target：`telegram:7943831495`**。不再允许 bare `telegram`、`telegram:TzeHim Sung`，也不再允许内容任务使用 `origin`。`origin` 只作为历史排查参考；所有启用中的 recurring 内容任务必须被守卫纠正为 `telegram:7943831495`。

| 平台/target | deliver | send_message | 根因 / 备注 |
|------|---------|-------------|------|
| `origin` | ⚠️ 禁止用于内容任务 | — | 只保留作历史排查参考；守卫会把内容任务纠正为 `telegram:7943831495` |
| bare `telegram` | ❌ | ⚠️ 不稳定 | 当前 Home ID 为 `thsung`，会触发 `invalid literal for int() with base 10: 'thsung'` |
| `telegram:TzeHim Sung` | ❌ | ❌ | 会超时，不要用 |
| QQ | ❌ 11263 | ❌ 11263 | QQ bot WebSocket 断线 → `ErrorCheckGuildAuth` 系统错误；非 target 格式或权限问题 |
| 微信 | ❌ asyncio | ❌ asyncio | `Timeout context manager should be used inside a task` — 平台层 bug，无法在 agent 端修复 |

关键发现：微信上用户发消息→bot 回复**可以**正常工作（在消息 handler 的 asyncio 上下文中），但 `send_message` 和 `deliver` 的主动发送脱离了 asyncio 上下文，必然失败。

## 最终架构：单任务直达 Telegram

```
┌──────────────────────────┐
│ 主任务 (skill=xxx)         │
│ 生成报告                  │
│ deliver=telegram:7943831495 │
└──────────────────────────┘
```

**不再使用转发器**，所有 content type 各一个 cron job。内容任务必须显式 `deliver='telegram:7943831495'`。后台守卫 `Cron投递策略守卫` 每 30 分钟静默审计一次，发现任何启用中的 recurring 内容任务偏离该 target，就自动改回。

## 创建示例

```python
cronjob(
  action='create',
  name='xxx日报',
  skill='xxx-tracker',
  skills=['xxx-tracker'],
  prompt='加载并执行 xxx-tracker skill。生成完整报告作为最终回复。',
  schedule='0 9 * * *',
  # 不要传 repeat='forever'：cronjob.repeat 参数是整数；recurring schedule 省略 repeat 即默认 forever。
  deliver='telegram:7943831495',  # 强制统一；不要用 origin / bare telegram / telegram:姓名
)
```

## 已部署实例（全部直达 Telegram）

| 任务 | skill | 时间 |
|------|-------|------|
| 美股收盘日报 | us-stock-tracker | 07:00 |
| 偶像Live倒计时 | anison-live-countdown | 08:35 |
| 中港股午市快报 | cnhk-stock-tracker | 12:10 |
| 中港股收盘日报 | cnhk-stock-tracker | 16:10 |
| Yahoo JP 锐评日报 | yahoo-jp-roast | 22:00 |

> 当前部署策略：所有启用中的 recurring 内容任务必须 `deliver='telegram:7943831495'`。`Cron投递策略守卫` 每 30 分钟检查并自动纠偏；守卫自身 `deliver='local'`，避免刷屏。

## 代码固化：投递策略审计

投递规则已固化为 Python 模块：

```bash
python3 cron-multi-platform-delivery/scripts/delivery_policy.py ~/.hermes/cron/jobs.json
```

脚本会检查启用中的 recurring cron job：
- 启用中的 recurring 内容任务必须精确使用 `deliver='telegram:7943831495'`；
- `Cron投递策略守卫` 作为唯一例外，使用 `deliver='local'` 静默运行，避免审计通过消息刷屏；
- 禁止 bare `telegram`、`telegram:TzeHim Sung`、`origin`、`weixin`、`qqbot`；
- `build_create_kwargs()` 为新建 cron job 提供默认强制参数（`deliver='telegram:7943831495'`）。

配套测试：

```bash
python3 -m pytest cron-multi-platform-delivery/tests/test_delivery_policy.py -q
```

## QQ 11263 诊断（保留参考）

如果将来 QQ WebSocket 恢复想重新启用，以下是排查步骤：

1. 11263 = `ErrorCheckGuildAuth`（系统错误），非权限/配置问题
2. 参考文档：[事件订阅与通知 - WebSocket 方式](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html#websocket%E6%96%B9%E5%BC%8F) | [OpenAPI 错误码](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/error-trace/openapi.html)
3. 检查 WebSocket 生命周期：Hello(Op10) → Identify(Op2) → READY → Heartbeat(Op1) ↔ HeartbeatACK(Op11)
4. `qqbot` 和 `qqbot:A9F4A6FEFD341E5BE3A95008B6C89177` 等效，都依赖 WebSocket
5. 不要为 11263 改 target 格式——翻官方文档定位到真实含义之前，曾被这个误导浪费了大量时间

## 反模式

| ❌ 不要 | ✅ 用 |
|---------|------|
| 创建 QQ/微信转发器 | 单任务直投 `telegram:7943831495`，并由守卫每 30 分钟强制纠偏 |
| 使用 bare `telegram` | `telegram:7943831495` |
| 使用 `origin` 投递内容任务 | `telegram:7943831495`（`origin` 可能持久化为微信/QQ） |
| 未检查任务投递 target | 运行 `delivery_policy.py`，或依赖 `Cron投递策略守卫` 自动纠偏 |
| 创建 recurring job 时传 `repeat='forever'` | 省略 `repeat`；cronjob 的 `repeat` 入参是整数，recurring schedule 默认 forever |
| 为 QQ/微信做 retry chain | 11263 是 WebSocket 问题，retry 无效 |
| `send_message` 到 QQ/微信 | 和 deliver 一样炸 |
| 看到 11263 就改 target 格式 | 翻官方文档查真实错误含义 |
