---
name: update-fedora-packages
description: 在 Fedora / WSL 环境中以非交互方式刷新仓库并更新系统软件包；适合后台 cron 静默执行。
---

# Update Fedora Packages

用于用户要求“更新软件包 / 更新 Fedora / WSL Fedora 系统更新 / dnf upgrade”时。

## 目标

在当前 Fedora 系统中安全、非交互地执行软件包更新，并验证是否还有待更新包。该 skill 默认面向 WSL 中的 Fedora 环境，但命令同样适用于普通 Fedora。

## 执行流程

1. 先确认系统与包管理器：

```bash
cat /etc/fedora-release 2>/dev/null || cat /etc/os-release
command -v dnf5 || command -v dnf
whoami
```

2. 选择包管理器：
   - 优先使用 `dnf5`；
   - 若没有 `dnf5`，退回 `dnf`。

3. 以非交互、不可卡住的方式更新：

```bash
sudo -n dnf5 upgrade --refresh -y
```

或：

```bash
sudo -n dnf upgrade --refresh -y
```

注意：必须使用 `sudo -n`，避免 cron / gateway 后台任务等待密码而卡死。

4. 更新后验证：

```bash
sudo -n dnf5 check-upgrade --refresh; rc=$?; echo "dnf_check_upgrade_exit_code=$rc"; exit 0
```

或：

```bash
sudo -n dnf check-update --refresh; rc=$?; echo "dnf_check_update_exit_code=$rc"; exit 0
```

解释：
- `0`：无待更新包；
- `100`：仍有待更新包；
- 其他：仓库、网络、权限或包管理器错误。

5. 最终回复应简洁记录：
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
加载并执行 update-fedora-packages skill：确认 Fedora 系统与 dnf/dnf5，使用 sudo -n 非交互执行软件包更新，随后检查是否仍有待更新包。最终回复只写简洁执行状态，供本地 cron 日志保存；不要发送任何额外通知。
```
