---
name: cnhk-stock-tracker
description: 中港股行情追踪 — 双数据源（新浪实时 + Yahoo v8 收盘），覆盖 A 股芯片半导体 + 港股科技/LLM 概念。含大盘/板块/异动/52周位置分析 + 叙事生成。
---

# 中港股行情追踪

## 快速使用

```bash
# 实时快照（新浪财经，盘中用）
python3 scripts/snapshot.py
python3 scripts/snapshot.py --a-only
python3 scripts/snapshot.py --hk-only

# 收盘日报（Yahoo v8，盘后用）
python3 scripts/daily_report.py
python3 scripts/daily_report.py --a-only
python3 scripts/daily_report.py --hk-only

# JSON 输出
python3 scripts/daily_report.py --json
```

## 文件结构

```
scripts/
  common.py         # HTTP客户端、双源ticker配置、数据结构、板块分组
  analysis.py       # 分析引擎 + 叙事生成（52周位置、原因简述、综述、关键动态、总结）
  snapshot.py       # 新浪财经实时快照（盘中）
  daily_report.py   # Yahoo v8 收盘日报（盘后），分析师风格输出
```

## 覆盖标的

### A 股芯片半导体（14 只）
中芯国际 / 海光信息 / 寒武纪 / 北方华创 / 韦尔股份 / 澜起科技 / 中微公司 / 长电科技 / 卓胜微 / 兆易创新 / 沪硅产业 / 华虹公司 / 拓荆科技 / 紫光国微

### 港股科技 / LLM 概念（16 只）
腾讯控股 / 小米集团 / 阿里巴巴 / 美团 / 京东集团 / 网易 / 快手 / 百度集团 / 商汤-W / 中芯国际 / 哔哩哔哩 / 金蝶国际 / 华虹半导体 / 金山云 / 微盟集团 / 平安好医生

### 指数（5 个）
上证指数 / 深证成指 / 创业板指 / 科创50 / 恒生指数

## 双数据源

| 数据源 | 端点 | 用途 | 特点 |
|--------|------|------|------|
| 新浪财经 | `hq.sinajs.cn/list=` | 实时快照 | sh/sz/hk/int_ 前缀，需要 Referer |
| Yahoo v8 | `query1.finance.yahoo.com/v8/finance/chart/` | 收盘日报 + 趋势分析 | `.SS`/`.SZ`/`.HK` 后缀，**必须 curl subprocess**，range=1mo 获取约20个交易日日线用于趋势分析 |

## 交易时间

- **A 股**：9:30–11:30 / 13:00–15:00（北京时间）
- **港股**：9:30–12:00 / 13:00–16:00（北京时间）

## 环境约束

同 `us-stock-tracker`：
- `proxies={"http": None, "https": None}` 必须
- 新浪需要 `Referer: https://finance.sina.com.cn/`
- Yahoo v8 必须 `subprocess.run(["curl", "-s", ...])` 而非 Python requests

## 日报输出结构

与 `us-stock-tracker` 完全对齐的分析师风格：

1. **🏛 大盘概览** — 指数涨跌表 + A/港分组叙事
2. **🔍 核心科技股** — 12 只重点股，含 52周位置
3. **表现综述** — A 股芯片 + 港股科技双市场叙事
4. **🔥 异动** — 涨/跌前五 + 原因简述（含 A 股涨跌停检测）
5. **📈 走势深度分析** — 精选 2-3 只最强上涨 + 2-3 只最弱下跌个股，做多维度深度拆解
6. **🧠 关键动态** — A 股芯片异动 / 港股科技 / LLM 概念 / 跨市场联动
7. **📈 一句话总结**

## 与 us-stock-tracker 的区别

| | us-stock-tracker | cnhk-stock-tracker |
|---|---|---|
| 市场 | 美股 | A 股 + 港股 |
| 标的 | 36 只科技股 | 14 A 股 + 16 港股 |
| 时区 | EDT/EST 夏令时 | 北京时间（无 DST） |
| 特色 | 费城半导体 SOX | 涨跌停检测 / LLM 概念 |
| 板块 | 半导体/软件云/消费/中概 | A股芯片 / 港股科技 |

## 📈 走势深度分析 方法论

`_detect_trend()` 对每只有 1 个月历史数据的个股进行多日趋势检测：

| 维度 | 算法 | 输出 |
|------|------|------|
| 累积涨跌 | 区间首日收盘 → 最新收盘 | cumulative_return（%） |
| 连续方向 | 从最近一日向前数连续同向天数（>0.05% 为有效） | streak（正=连阳，负=连阴） |
| 涨跌比 | 上涨天数 / 总交易日 | up_ratio |
| 量价确认 | 近5日均量 / 全区间均量 | vol_ratio（>1.3 放量，<0.8 缩量） |

**趋势分类**：累积 ≥15% → 强势拉升；≥5% → 稳步上行；<5% → 温和走强；反之对称负向分类。

`_deep_reason()` 综合五个维度生成归因：
1. **趋势形态** — 连阳/连阴天数判断多空力量
2. **量价关系** — 放量上涨（资金介入）vs 缩量上涨（动能衰减）vs 放量下跌（资金出逃）
3. **52周位置** — 逼近高点/低点的阻力与支撑判断
4. **板块联动** — 个股 vs 板块均值，判断 α（独立行情）或 β（系统性）属性
5. **涨跌停检测** — A 股涨跌停的极端情绪标注
