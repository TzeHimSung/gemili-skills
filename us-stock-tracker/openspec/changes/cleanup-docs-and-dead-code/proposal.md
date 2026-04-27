# Cleanup: SKILL.md 同步 + 死代码清理 + 假期表去重

## Why

OpenSpec review 发现 5 个问题：SKILL.md 投递方式、休市检测描述与代码不符；daily_report.py 含 60+ 行死代码 `_closed_reason()`；假期表在 3 处重复定义且不一致；analysis.py 含无效赋值。

## What Changes

1. **SKILL.md** — 更新投递方式为 07:00 Telegram，重写休市检测描述为「判断昨晚美东是否为交易日」
2. **daily_report.py** — 删除死代码 `_closed_reason()` 函数（~50行），移除未使用的 `timedelta` import（如无其他使用）
3. **假期表统一** — 确保 `_check_market_status()` 中假期表与 shared/stock_tracker_lib 的 `US_HOLIDAYS` 保持一致
4. **analysis.py** — 移除无效赋值 `_fifty_two_week_text = _fifty_two_week_text`，移除冗余 import 后覆盖的 `_display_name`
5. **Cron job** — 重命名 "偶像企划Live倒计时 - 微信" → 移除 "- 微信" 后缀

## Impact

- 纯维护性改动，不影响运行逻辑
- 删除死代码后 daily_report.py 减少 ~50 行
- SKILL.md 与代码实现一致，避免未来混淆
