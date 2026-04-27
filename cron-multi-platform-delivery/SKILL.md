---
name: cron-multi-platform-delivery
description: 将单个 cron job 输出推送到 Telegram。QQ/微信均不可用，精简为单点 Telegram 投递。
---

# Cron 投递（Telegram Only）

## 核心结论

经过系统性排查，**只有 Telegram 的 deliver 管道稳定可用**：

| 平台 | deliver | send_message | 根因 |
|------|---------|-------------|------|
| Telegram | ✅ | ✅ | — |
| QQ | ❌ 11263 | ❌ 11263 | QQ bot WebSocket 断线 → `ErrorCheckGuildAuth` 系统错误；非 target 格式或权限问题 |
| 微信 | ❌ asyncio | ❌ asyncio | `Timeout context manager should be used inside a task` — 平台层 bug，无法在 agent 端修复 |

关键发现：微信上用户发消息→bot 回复**可以**正常工作（在消息 handler 的 asyncio 上下文中），但 `send_message` 和 `deliver` 的主动发送脱离了 asyncio 上下文，必然失败。

## 最终架构：单任务直达 Telegram

```
┌──────────────────────────┐
│ 主任务 (skill=xxx)         │
│ 生成报告                  │
│ deliver=telegram:TzeHim   │
└──────────────────────────┘
```

**不再使用转发器**，所有 content type 各一个 cron job，直接 deliver 到 Telegram。

## 创建示例

```python
cronjob(
  action='create',
  name='xxx日报',
  skill='xxx-tracker',
  skills=['xxx-tracker'],
  prompt='加载并执行 xxx-tracker skill。生成完整报告作为最终回复。',
  schedule='0 9 * * *',
  repeat='forever',
  deliver='telegram:TzeHim Sung',
)
```

## 已部署实例（全部直达 Telegram）

| 任务 | skill | 时间 |
|------|-------|------|
| 美股收盘日报 | us-stock-tracker | 08:45 |
| 偶像Live倒计时 | anison-live-countdown | 09:00 |
| 中港股收盘日报 | cnhk-stock-tracker | 16:10 |
| 5ch 每日锐评 | 5ch-roast | 22:36 |

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
| 创建 QQ/微信转发器 | 全部走 Telegram deliver |
| 为 QQ/微信做 retry chain | 11263 是 WebSocket 问题，retry 无效 |
| `send_message` 到 QQ/微信 | 和 deliver 一样炸 |
| 看到 11263 就改 target 格式 | 翻官方文档查真实错误含义 |
