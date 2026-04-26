---
name: 5ch-roast
description: 抓取 5ch.io 实时热帖（ikioig 全板勢い）前100条，筛选20条最逆天帖子生成中日双语锐评报告，输出到 D:\hermes\5ch-reports\YYYY-MM-DD\。
trigger:
  - 5ch热帖
  - 5ch锐评
  - 锐评老日
  - 日本论坛热帖
  - 看看5ch
  - ikioig
  - 5ch.io
---

# 5ch Roast — 锐评老日

抓取 5ch.io 实时热帖排行（ikioig）前100条，海选出20条最逆天/最值得吐槽的帖子，逐条带中日双语标题 + ≥100字中文锐评，按离谱程度从高到低排列，输出结构化报告。

## 工作流

### 第一步：抓取 100 条

```bash
cd ~/.hermes/skills/5ch-roast/scripts && python3 scraper.py
```

⚠️ **务必使用 `timeout=300`**（5分钟）。scraper 需要逐条请求约90个帖子详情页，默认120s不够。

输出：`D:\hermes\5ch-reports\YYYY-MM-DD\raw_data.json`

### 第二步：自动过滤 + 预打分

```bash
cd ~/.hermes/skills/5ch-roast/scripts && python3 filter_score.py
```

脚本会：
- **自动过滤**：电视实况打卡串、偶像例行更新、体育无事件实况、游戏板例行串、低信息量帖
- **预打分**：根据板块权重（嫌儲+4/VIP+3）+ meme标签（高市速報+5/悲報+3）+ 逆天关键词 + 评论数 + 标题特征
- 输出 `scored.json`（≤50条候选，按逆天潜力分降序）+ `filter_report.txt`（被过滤原因）

### 第三步：AI 精选 20 条 + 写入锐评

从 `scored.json` 的 candidates 中选 top 20 条（按 `_score` 排即可），对每条写入：

```python
# AI agent 操作：
# 1. 读 scored.json
# 2. 对前 20 条添加 _cn_title（中文标题）和 _ai_commentary（中文锐评）
# 3. 写回 scored.json
```

**为每条帖子添加字段**：
- `_cn_title`: 中文翻译标题
- `_ai_commentary`: ≥100 字中文锐评（毒舌/幽默/文化洞察风格）

**逆天程度**评判维度：

1. **标题炸裂度**：标题本身是否荒诞/反常识/情绪化（如「高市速報」「悲報」「朗報」等meme标签加分）
2. **评论精彩度**：评论区是否有神回复、经典日式阴阳怪气、meme复读
3. **社会隐喻**：背后反映的日本社会问题有多深刻
4. **文化反差**：对中文读者来说有多"看不懂但大受震撼"
5. **板块纯度**：嫌儲的阴阳怪气 > 普通新闻转帖；VIP的混沌发言 > 电视实况串的例行打卡
6. **评论数权重**：高评论数说明引发了真实讨论，但不是绝对标准（0评论的极品标题党也可能入选）

**排除规则**：
- 纯电视实况打卡串（如「いちおつ」连打无实质内容的）
- 纯番組表搬运/数据更新的例行串
- 偶像fan串的例行更新（除非有炎上事件）

### 第四步：生成锐评报告

```bash
cd ~/.hermes/skills/5ch-roast/scripts && python3 gen_report.py
```

`gen_report.py` 读取 `scored.json`，取前 20 条，自动生成结构化 Markdown 报告。如果 AI 已写入 `_cn_title` 和 `_ai_commentary`，则报告包含完整锐评内容；否则生成骨架供 AI 后续编辑。

**输出**：`D:\hermes\5ch-reports\YYYY-MM-DD\report.md`

### 第五步：输出报告

**报告结构**（由 gen_report.py 自动生成）：
```
# 🔥 5ch 锐评老日 — 日期
## 📊 统计速览（含板块分布、评论统计）
## 🏆 逆天排行榜（20条，含 AI 锐评 + 评论区精选）
```
```
D:\hermes\5ch-reports\YYYY-MM-DD\
├── raw_data.json       ← scraper 输出
├── scored.json         ← filter 输出
├── filter_report.txt   ← 过滤原因明细
├── report.md           ← 最终锐评报告
└── scraper.py          ← 脚本备份
```

**重要：生成报告后，必须把 report.md 的完整内容直接发送到对话中**，不要只给文件路径让用户手动打开。报告末尾附上文件路径即可。

## 数据源

| 端点 | 用途 |
|---|---|
| `https://headline.5ch.io/ikioig/` | 热帖排行 |
| `https://XXXX.5ch.io/test/read.cgi/BOARD/THREAD_ID/` | 帖子详情 |

## 5ch 板块速查

| 板块 | 特征 |
|---|---|
| 嫌儲 (greta/poverty) | 政治吐槽大本营，万物转高市/安倍，阴阳怪气浓度最高 |
| 速＋ (asahi/newsplus) | 新闻速报+，相对正经但评论区不正经 |
| VIP (mi/news4vip) | 混沌杂谈，讨论方向完全随机，经常性癖暴露 |
| なんG (nova/livegalileo) | 棒球民+各种奇奇怪怪话题 |
| 芸＋ (hayabusa9/mnewsplus) | 艺能新闻，炎上事件必上 |
| ゲハ (krsw/ghard) | 游戏硬件战争，平台fanboy互咬 |
| netidol (egg/netidol) | VTuber/网络偶像 |

## 已知陷阱

- 5ch Shift-JIS 编码，scraper.py 自动处理
- 前约39楼灌水乱码（「チョン」「パヨ」重复），scraper.py 自动过滤
- ikioig 按发帖速度排序，0评论帖也可能上榜
- ikioig 可能因去重返回少于100条，属正常
- **生成报告时**：避免用 `execute_code` 内嵌大量中文长文本（含「」等引号会触发 SyntaxError），改用 `write_file` 写脚本 → `terminal` 运行
- **索引映射**：`gen_report.py` 用标题子串匹配而非数组索引，防止 filter_score 重排序导致错位
- cron 一次性任务/时间戳任务可能不被拾取，用 `repeat=forever` 循环任务
- **scraper.py 超时风险**：抓取约90条帖子需对每条发HTTP请求获取详情，默认120s超时不够用。务必使用 `timeout=300`（5分钟）。若仍然超时，检查网络或重试
- **scored.json 数据结构**：是 `{"candidates": [...], "scored_time": "...", ...}` 的 dict 结构，不是直接列表。读取候选帖用 `data['candidates']`。filter_score 控制台输出只显示前20条，完整50条候选在 scored.json 中
- **评论提取技巧**：scored.json 中每条帖子的 `comments` 字段包含全部评论，但前39楼多为灌水乱码。筛选有效评论时跳过含「チョン」「パヨ」「チョ」的条目，取 `len(text) > 3` 的有效评论
