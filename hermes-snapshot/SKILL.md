---
name: hermes-snapshot
description: Use when the user asks “备份自己”, “全量备份”, or requests a full Hermes self-backup. Runs `hermes backup`, stores the exported zip under `hermes_snapshot/` in the skills repository, then commits and pushes the repository.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, backup, snapshot, skills, git]
    related_skills: [hermes-agent]
---

# Hermes Snapshot

## Overview

Use this skill to create a full backup of the current Hermes installation and synchronize that backup into the user's skills repository. The user's trigger phrases are:

- `备份自己`
- `全量备份`
- `Hermes 备份`
- `Hermes snapshot`

Default repository path for this user is `/home/jhseng/gemili-skills`. The backup directory inside that repository must be named exactly `hermes_snapshot`.

A normal run creates a full `hermes backup` zip archive. Do not use `hermes backup --quick` unless the user explicitly asks for a quick backup.

## Required Behavior

When the user asks to back up Hermes:

1. Load this skill.
2. Check whether `/home/jhseng/gemili-skills/hermes_snapshot` exists.
   - If it does not exist, create it.
3. Run a full Hermes backup and write the zip directly into that directory.
4. Verify that the zip exists, is non-empty, and passes `unzip -t`.
5. Commit and push the new zip to the skills repository.
6. Report the backup path, zip size, git commit SHA, and push result directly in the conversation.

## One-Command Workflow

Prefer the bundled script because it handles path creation, zip validation, git commit, and push consistently:

```bash
bash /home/jhseng/.hermes/skills/hermes-snapshot/scripts/hermes_snapshot_backup.sh
```

If this skill is installed somewhere else, locate the script from the loaded skill's `skill_dir`, then run:

```bash
bash "$SKILL_DIR/scripts/hermes_snapshot_backup.sh"
```

## Manual Fallback

If the script is unavailable, run these steps manually:

```bash
set -euo pipefail
repo="/home/jhseng/gemili-skills"
snapshot_dir="$repo/hermes_snapshot"
mkdir -p "$snapshot_dir"

ts="$(date +%Y%m%d-%H%M%S)"
out="$snapshot_dir/hermes-backup-$ts.zip"
hermes backup --output "$out"
test -s "$out"
unzip -t "$out"

cd "$repo"
git add "hermes_snapshot/"
git commit -m "backup: hermes snapshot $ts"
git pull --rebase
git push
```

## Git Sync Rules

- Do not force-push.
- Do not rewrite existing backup archives.
- Only stage `hermes_snapshot/` unless the user explicitly asks to sync other skill edits too.
- If `git pull --rebase` conflicts, stop and report the conflict; do not auto-resolve unrelated repository conflicts.
- If `git push` fails because the remote advanced, run `git pull --rebase` once and retry `git push` once.

## Security Note

`hermes backup` is a full backup of Hermes configuration, skills, sessions, and data. It may include secrets such as `.env`, auth tokens, cron jobs, and private session history. The user explicitly requested repository synchronization, but still mention this in the final report if pushing to a public remote or an unfamiliar remote URL.

## Verification Checklist

Before finalizing:

- [ ] `hermes_snapshot/` exists under `/home/jhseng/gemili-skills`.
- [ ] A new `hermes-backup-*.zip` exists in that directory.
- [ ] `test -s` succeeded for the zip.
- [ ] `unzip -t` succeeded.
- [ ] `git commit` created a commit containing the new zip.
- [ ] `git push` succeeded.
- [ ] Final response includes backup file path, size, commit SHA, and remote push result.
