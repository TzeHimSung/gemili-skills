# Tasks: Cleanup docs and dead code

## Task 1: 更新 SKILL.md 投递方式行

**Objective:** 将投递描述更新为当前实际状态

**Files:**
- Modify: `SKILL.md`

**Steps:**

1. 定位 "定时推送 — 每日早 7:00 微信 / 7:10 QQ + Telegram"
2. 替换为 "定时推送 — 每日 07:00 Telegram"
3. 同步更新 `gemili-skills/README.md` 中的时间表（如仍不一致）

---

## Task 2: 重写 SKILL.md 休市检测描述

**Objective:** 文档与 `_check_market_status()` 代码实现一致

**Files:**
- Modify: `SKILL.md`

**Steps:**

1. 定位 "## 市场休市检测" 段落
2. 删除旧的函数表格（`_is_us_dst` / `_market_hours_str` / `_check_market_status`）
3. 替换为新描述：

```markdown
## 市场休市检测

判断「昨晚（美东时间）是否为交易日」而非「最新数据日期」：

| 条件 | 判定 | 
|------|------|
| 昨晚 = 周六/日 | **休市** — 周末，输出简化消息 |
| 昨晚 = 美股节假日 | **休市** — 覆盖 2026-2027 假期 |
| 昨晚 = 周一~周五 非假期 | **开盘** — 正常生成日报 |

北京时间早上 7:00，昨晚 = 昨天美东日期。周一 7:00 → 昨晚美东周日 → 休市。
```

---

## Task 3: 删除 daily_report.py 死代码 `_closed_reason()`

**Objective:** 移除已无调用的函数，减少维护负担

**Files:**
- Modify: `scripts/daily_report.py`

**Steps:**

1. 确认 `_closed_reason` 无调用方：`search_files("_closed_reason", path="scripts/daily_report.py")`
2. 删除 `_closed_reason()` 函数定义（约 268 行起的大段代码，含假期表）
3. 确认脚本仍可运行：`python3 scripts/daily_report.py --tech-only -q`

---

## Task 4: 清理 analysis.py 无效代码

**Objective:** 移除空操作赋值和冗余 import

**Files:**
- Modify: `scripts/analysis.py`

**Steps:**

1. 删除第 37 行：`_fifty_two_week_text = _fifty_two_week_text  # 直接代理`
2. 检查 `_display_name`：移除从 common 的导入（`from common import ... display_name` 部分），保留本地定义
3. 确认运行无影响：`python3 scripts/daily_report.py --tech-only -q`

---

## Task 5: 同步 git 仓库 + 更新 README

**Objective:** 推送所有修改，保持 gemili-skills 同步

**Steps:**

1. `rsync` us-stock-tracker → gemili-skills
2. 如 README.md 中时间表仍不一致，同步更新
3. `git commit -m "chore: cleanup us-stock-tracker - sync docs, remove dead code"`
4. `git push`
