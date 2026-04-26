---
name: cron-multi-platform-delivery
description: 将单个 cron job 输出转发到微信/QQ/Telegram 三平台。主任务 + context_from 转发器模式。
---

# Cron 多平台投递

将一份 cron job 输出同时推送到微信、QQ、Telegram 三个平台。

## 核心发现

- **`send_message` 对微信/QQ 不可用**：微信报 `Timeout context manager should be used inside a task`（asyncio bug），QQ 报 `频道不存在 (11263)`。
- **cronjob `deliver` 管道正常**：三条链路全部验证通过。所有跨平台推送**必须**走 cronjob deliver。
- **可用 targets**（`send_message(action='list')` 获取）：
  - 微信 DM：`weixin:o9cq80ys2QEOI68H3HtT5ENJzNmE@im.wechat`
  - QQ DM：`qqbot:A9F4A6FEFD341E5BE3A95008B6C89177`（不要用 bare `qqbot`，会触发频道不存在）
  - Telegram DM：`telegram:TzeHim Sung`

## 架构：1 主 + N 转发器

```
┌─────────────────────┐
│ 主任务 (微信 deliver)  │  运行 skill，生成报告，deliver → 微信
│ skill=xxx            │
│ deliver=weixin:...   │
└─────────┬───────────┘
          │ context_from
    ┌─────┴─────┬─────────────┐
    ▼           ▼             ▼
┌────────┐ ┌────────┐ ┌──────────┐
│ QQ转发  │ │ TG转发  │ │ (更多平台) │
│ 无skill │ │ 无skill │ │          │
│ deliver │ │ deliver │ │          │
│ =qqbot  │ │ =tg     │ │          │
└────────┘ └────────┘ └──────────┘
```

## 创建步骤

### 1. 主任务

```python
cronjob(
  action='create',
  name='xxx - 微信',
  skill='your-skill',
  skills=['your-skill'],
  prompt='加载并执行 your-skill skill。生成完整报告作为最终回复。',
  schedule='0 9 * * *',
  repeat='forever',
  deliver='weixin:o9cq80ys2QEOI68H3HtT5ENJzNmE@im.wechat',
)
```

### 2. 转发器（QQ + Telegram）

```python
for platform, target in [
  ('QQ', 'qqbot:A9F4A6FEFD341E5BE3A95008B6C89177'),
  ('Telegram', 'telegram:TzeHim Sung'),
]:
  cronjob(
    action='create',
    name=f'xxx - {platform}',
    prompt='你是转发器。上游任务已生成完整报表（通过 context 注入）。将报表内容原样输出为最终回复，不做任何修改。',
    schedule='10 9 * * *',  # 比主任务晚 10 分钟
    repeat='forever',
    deliver=target,
    context_from=['MAIN_JOB_ID'],  # ← 关键：注入主任务输出
    enabled_toolsets=[],  # 转发器不需要任何工具
  )
```

## 测试

```python
cronjob(action='run', job_id='MAIN_JOB_ID')
# 等 2-3 分钟后
cronjob(action='list')
# → last_status='ok'、last_delivery_error=null = 成功
```

**注意**：`run` 有时有延迟，状态不会立即更新。新鲜的一次性任务（`schedule='1m'`）比 `run` 已有任务更可靠。

## 反模式

| ❌ 不要 | ✅ 用 |
|---------|------|
| `send_message(target='weixin')` | `cronjob(deliver='weixin:...')` |
| 转发器带 skill | 转发器 `skills=[]` |
| 转发器用 bare `qqbot` | `qqbot:A9F4A6FEFD341E5BE3A95008B6C89177` |
| 在 prompt 手写内容格式 | 用 `context_from` 注入主任务输出 |

## 已部署实例

| 主任务 | skill | 时间 | QQ转发 | TG转发 |
|--------|-------|------|--------|--------|
| 美股收盘日报 | us-stock-tracker | 7:00 | 7:10 ✅ | 7:10 ✅ |
| 偶像Live倒计时 | anison-live-countdown | 9:00 | 9:10 ✅ | 9:10 ✅ |
