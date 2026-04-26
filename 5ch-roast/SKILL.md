---
name: 5ch-roast
description: 抓取 5ch.io 实时热帖（ikioig 全板勢い）并生成中文锐评报告。覆盖前30条热帖及其评论区，输出结构化报告到 D:\hermes\5ch-reports\ 按日期归档。
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

抓取 5ch.io 实时热帖排行（ikioig），逐条提取评论区内容，生成带锐评的结构化中文报告。

## 工作流

### 第一步：抓取

```bash
cd ~/.hermes/skills/5ch-roast/scripts && python3 scraper.py
```

脚本会：
1. 从 `https://headline.5ch.io/ikioig/` 获取前30条热帖
2. 逐条进入帖子页，抓取评论（自动过滤占位乱码帖，识别有效日语评论）
3. 输出原始数据到 `/tmp/5ch_hot_threads.json`

注意：5ch 使用 Shift-JIS 编码，帖子前约39楼通常为灌水占位乱码。

### 第二步：生成锐评报告

数据抓取完成后，由 AI 逐条阅读帖子和评论区内容，生成中文锐评报告。

锐评风格要求：
- **毒舌但不刻薄**：对日本网络文化保持幽默洞察
- **抓住本质**：提炼每条帖子的核心矛盾和社会隐喻
- **文化翻译**：将日式网络梗转化为中文读者能理解的表达
- **数据加持**：引用评论数、串号历史等量化信息增强说服力
- **板块识读**：标注板块特征（嫌儲=政治吐槽、VIP=混沌、なんG=棒球民等）

### 第三步：保存

报告保存路径：
```
D:\hermes\5ch-reports\YYYY-MM-DD\
├── report.md        ← 锐评报告
├── raw_data.json    ← 原始数据
└── scraper.py       ← 脚本备份
```

## 数据源说明

| 端点 | 用途 |
|---|---|
| `https://headline.5ch.io/ikioig/` | 热帖排行（全板勢い） |
| `https://XXXX.5ch.io/test/read.cgi/BOARD/THREAD_ID/` | 帖子详情+评论 |

## 5ch 板块速查

| 板块 | 特征 |
|---|---|
| 嫌儲 (greta/poverty) | 政治吐槽大本营，万物转高市/安倍 |
| 速＋ (asahi/newsplus) | 新闻速报+，相对正经 |
| VIP (mi/news4vip) | 混沌杂谈，讨论方向随机 |
| なんG (nova/livegalileo) | 棒球民聚集地 |
| 芸＋ (hayabusa9/mnewsplus) | 艺能新闻 |
| ゲハ (krsw/ghard) | 游戏硬件战争 |
| netidol (egg/netidol) | VTuber/网络偶像 |

## 已知陷阱

- 5ch 编码为 Shift-JIS，curl 后必须 `iconv -f SHIFT-JIS -t UTF-8`
- 帖子前约39楼是灌水占位乱码（重复的「チョン」「パヨ」等），需过滤
- ikioig 按发帖速度排序，0评论帖子也可能上榜
- 部分子域名（如 greta、krsw）可能需要不同的请求头
