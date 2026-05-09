---
name: kaikatsu-club-vacancy
description: 输入日本地名/车站/机场名，查询最近三家快活CLUB（快活クラブ）的官网实时空席/房型剩余情况。
version: 1.0.0
metadata:
  hermes:
    tags: [japan, travel, netcafe, vacancy, kaikatsu-club]
---

# 快活CLUB 最近三店空席查询

当用户想查“快活CLUB / 快活クラブ / 快活club / 漫画喫茶 / 网咖 / 包间空位 / 空席状况”时使用本 skill。

## 用户输入

用户需要给一个日本地点名，例如：

- `羽田机场` / `羽田空港`
- `秋叶原站` / `秋葉原駅`
- `新宿駅`
- `大阪難波駅`

如果用户没有给地点，先问：

> 你要查哪个日本地名/车站/机场附近的快活CLUB？例如：羽田机场、秋叶原站。

## 执行方式

在 skill 目录运行：

```bash
python3 scripts/kaikatsu_vacancy.py "秋葉原駅"
```

默认返回最近 3 家店。可选参数：

```bash
python3 scripts/kaikatsu_vacancy.py "羽田空港" --limit 3
python3 scripts/kaikatsu_vacancy.py "秋葉原駅" --refresh-cache
```

## 数据源

脚本使用快活CLUB官网公开页面本身调用的数据源：

1. 店铺列表：`https://www.kaikatsu.jp/data/shop.js`
2. 店铺坐标：各店官方详情页的 Google Maps embed 坐标
3. 空席接口：官网 `vacancy.html?store_code=...` 使用的 AWS API Gateway `empty_seat` 接口
4. 地名定位：OpenStreetMap Nominatim；失败时用国土地理院 `msearch.gsi.go.jp/address-search` 兜底

## 输出要求

把脚本输出的 Markdown 直接发给用户，不要只给文件路径。每家店必须包含：

- 店名与直线距离
- 地址
- 电话
- 官方店铺页链接
- 官方空席页链接
- 官网返回的每一种席种/房型空席状态，例如 `満席`、`残4席`、`残10席以上`

同时保留脚本末尾免责声明：空席随时变动，以现场/官网实时页面为准；距离为直线距离。

## 缓存

首次运行会抓取约 500 家店铺详情页并生成坐标缓存：

```text
~/.cache/hermes/kaikatsu-club-vacancy/stores_with_coordinates.json
```

缓存 TTL 为 7 天。若官网新增/变更店铺，用 `--refresh-cache` 强制刷新。

## 故障处理

- 地名无法定位：让用户换日文地名、加上“駅/空港/市区町村”等后缀。
- 空席 API 返回失败：仍报告店铺和链接，并提示该店空席状态取得失败。
- 最近店铺明显不对：用 `--refresh-cache` 重建坐标缓存。
- 首次运行较慢属正常；之后会走缓存。

## 经验与坑点

- 不要把空席 API key 硬编码进脚本；它是官网 JS 里的公开调用参数，应从 `common/js/shop_vacancy.js` 解析 `prod_api_key`，避免官网变更时失效，也避免静态扫描误报。
- Nominatim 对简体中文地名可能误匹配：`秋叶原站` 曾被定位到长野。必须先做常见中文别名归一化（如 `站→駅`、`机场/機場→空港`、`秋叶原→秋葉原`、`新宿站→新宿駅`）再 geocode，并用测试覆盖文档里的中文示例。
- 空席 API 偶发 SSL EOF / 网络瞬断；HTTP 客户端需要短重试。失败时不要中断整份报告，应保留店铺信息和官方空席页链接并标明该店取得失败。
- 坐标来自店铺详情页 Google Maps embed 的 `!2d<lon>!3d<lat>`；店铺列表 `shop.js` 没有经纬度。

## 验证命令

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest kaikatsu-club-vacancy/tests -q
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile kaikatsu-club-vacancy/scripts/kaikatsu_vacancy.py
python3 kaikatsu-club-vacancy/scripts/kaikatsu_vacancy.py "秋葉原駅" --limit 3
```
