---
name: cron-multi-platform-delivery
description: 将单个 cron job 输出推送到 Telegram。QQ/微信均不可用，精简为单点 Telegram 投递。
---

# Cron 投递（Telegram Only）

## 核心结论

经过系统性排查，**主动投递应回当前 Telegram DM（`deliver='origin'`）**：

| 平台/target | deliver | send_message | 根因 / 备注 |
|------|---------|-------------|------|
| `origin` | ✅ | — | 推荐：回当前 Telegram DM，保留会话上下文 |
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
│ deliver=origin 或 telegram:<numeric_chat_id> │
└──────────────────────────┘
```

**不再使用转发器**，所有 content type 各一个 cron job，直接 `deliver='origin'` 回当前 Telegram DM。

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
  deliver='origin',  # 回当前 Telegram DM；不要用 bare telegram / telegram:xxx
)
```

## 已部署实例（全部直达 Telegram）

| 任务 | skill | 时间 |
|------|-------|------|
| 美股收盘日报 | us-stock-tracker | 07:00 |
| 偶像Live倒计时 | anison-live-countdown | 09:00 |
| 中港股午市快报 | cnhk-stock-tracker | 12:10 |
| 中港股收盘日报 | cnhk-stock-tracker | 16:10 |
| Yahoo JP 锐评日报 | yahoo-jp-roast | 22:00 |

> 当前部署策略：新建任务优先 `deliver='origin'`；若历史任务的 `origin` 不是数字 Telegram chat，则用 `telegram:<numeric_chat_id>` 显式投递。不要改回 bare `telegram`。

## 代码固化：投递策略审计

投递规则已固化为 Python 模块：

```bash
python3 cron-multi-platform-delivery/scripts/delivery_policy.py ~/.hermes/cron/jobs.json --telegram-chat-id 7943831495
```

脚本会检查启用中的 recurring cron job：
- `deliver='origin'` 必须对应 `origin.platform == 'telegram'` 且 `origin.chat_id` 为数字；
- 迁移历史任务若 `origin` 仍是微信/QQ，建议改为 `telegram:<numeric_chat_id>`；
- 禁止 bare `telegram`、`telegram:TzeHim Sung`、`weixin`、`qqbot`；
- `build_create_kwargs()` 为新建 cron job 提供默认安全参数（`deliver='origin'`）。

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
| 创建 QQ/微信转发器 | 全部走 `deliver='origin'` 回 Telegram DM |
| 使用 bare `telegram` | `origin`（bare `telegram` 当前会把 Home ID `thsung` 当 int 解析而失败） |
| 为 QQ/微信做 retry chain | 11263 是 WebSocket 问题，retry 无效 |
| `send_message` 到 QQ/微信 | 和 deliver 一样炸 |
| 看到 11263 就改 target 格式 | 翻官方文档查真实错误含义 |
