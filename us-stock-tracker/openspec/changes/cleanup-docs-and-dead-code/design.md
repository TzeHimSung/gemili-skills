# Design: Cleanup docs and dead code

## Approach

一次性清理，不改逻辑。分 4 步：

### 1. SKILL.md 更新

直接替换两处过时描述：
- 投递方式：改为 07:00 Telegram 直投
- 休市检测：重写为「判断昨晚（美东时间）是否为交易日」，附加节假日检测说明

### 2. 删除死代码 `_closed_reason()`

`daily_report.py` 第 268-370 行的 `_closed_reason()` 函数已无调用者。`main()` 现在直接使用 `status["reason"]`。删除整段。

连带检查：`_closed_reason` 不再从 common.py / shared lib 被 daily_report.py 引用，确认安全删除。

### 3. 假期表对齐

`_check_market_status()` 内的 `us_holidays` dict 已包含 2026-2027。确认与 shared/stock_tracker_lib 的 `US_HOLIDAYS` 一致后，考虑是否改为从共享库导入以消除重复。

**边界判断**：shared 库的 `US_HOLIDAYS` 是模块级常量，可直接 `from common import US_HOLIDAYS`。但 `_check_market_status` 是 daily_report.py 本地函数，改导入需确认 shared 库假期完整。

如果能导入 shared 的 `US_HOLIDAYS`，可一并删除 `_closed_reason` 中重复的假期表（该函数删除后自然消除）。

### 4. analysis.py 清理

- 删除第 37 行 `_fifty_two_week_text = _fifty_two_week_text`
- 确认 `_display_name` 从 common 导入后本地覆盖是否必要（两者实现相同，移除导入或移除覆盖择一）

## Risk

零风险。纯文档+死代码清理，不涉及运行逻辑变更。
