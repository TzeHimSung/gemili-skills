---
name: update-fedora-packages
description: 在 Fedora / WSL 环境中以非交互方式刷新仓库并更新系统软件包；适合后台 cron 静默执行。
---

# Update Fedora Packages

用于用户要求“更新软件包 / 更新 Fedora / WSL Fedora 系统更新 / dnf upgrade”时。

## 目标

在当前 Fedora 系统中安全、非交互地执行软件包更新，并验证是否还有待更新包。该 skill 默认面向 WSL 中的 Fedora 环境，但命令同样适用于普通 Fedora。

## 固定脚本

不要从 prose 重新拼装 `dnf` / `dnf5` 命令；agent 与 cron 都应直接调用仓库内固定脚本：

```bash
update-fedora-packages/scripts/update_fedora_packages.sh
```

该脚本负责：检测 Fedora release、优先选择 `dnf5`（否则退回 `dnf`）、使用 `sudo -n` 非交互执行当前 release 内的软件包更新，并在最后执行非致命验证检查。

需要预检或测试 cron 权限时使用 dry-run，只做验证检查、不执行升级：

```bash
update-fedora-packages/scripts/update_fedora_packages.sh --dry-run
```

验证退出码解释：
- `0`：无待更新包；
- `100`：仍有待更新包；
- 其他：仓库、网络、权限或包管理器错误。

## 执行流程

1. 在仓库根目录或 skill 安装目录中运行固定脚本；不要手写替代命令。
2. 若 sudo 需要密码，脚本会因 `sudo -n` 快速失败，避免 cron / gateway 后台任务卡死。
3. 最终回复应简洁记录：
   - 系统版本；
   - 使用的包管理器；
   - 更新命令是否成功；
   - 验证结果；
   - 若失败，给出失败原因原文摘要。

## 后台/cron 规则

- 定时任务应使用 `deliver='local'` 静默保存输出，不向 Telegram / 微信发送消息。
- 定时任务应限制工具集为 `terminal` 即可。
- 若 sudo 需要密码或权限不足，任务应快速失败并在本地输出说明，不要尝试交互输入密码。
- 不要执行发行版大版本升级（例如 `system-upgrade`），只做当前 Fedora release 内的软件包更新。

## 推荐 cron prompt

```text
加载并执行 update-fedora-packages skill：直接运行 update-fedora-packages/scripts/update_fedora_packages.sh，不要从文档重写 dnf/dnf5 命令。最终回复只写简洁执行状态，供本地 cron 日志保存；不要发送任何额外通知。
```
