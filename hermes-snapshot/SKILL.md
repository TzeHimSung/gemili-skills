---
name: hermes-snapshot
description: Use when the user asks “备份自己”, “全量备份”, or requests a full Hermes self-backup. Creates a full Hermes backup, encrypts it, uploads it to GitHub Releases, and records a small manifest in the skills repository.
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, backup, snapshot, skills, git, github-release]
    related_skills: [hermes-agent, github-repo-management]
---

# Hermes Snapshot

## Overview

Use this skill to create a full backup of the current Hermes installation and synchronize a recoverable encrypted copy to GitHub without putting the large backup zip into normal Git history.

Trigger phrases:

- `备份自己`
- `全量备份`
- `Hermes 备份`
- `Hermes snapshot`

Default repository path for this user is `/home/jhseng/gemili-skills`. The local backup directory inside that repository is `hermes_snapshot/`.

A normal run creates a full `hermes backup` zip archive. Do not use `hermes backup --quick` unless the user explicitly asks for a quick backup.

## Storage Design

Additional session-specific rationale and the GitHub 100MB failure/recovery pattern are captured in `references/github-release-encrypted-backups.md`. API upload implementation pitfalls are captured in `references/github-release-upload-pitfalls.md`.

Do **not** commit backup zip files to ordinary Git history:

- GitHub rejects ordinary Git blobs larger than 100MB.
- Hermes backups may include secrets, tokens, cron data, sessions, and private config.
- Large binary backups make every clone slow and permanently bloat history.

The durable flow is:

```text
hermes backup -> local hermes-backup-*.zip
             -> gpg symmetric AES256 encrypted .zip.gpg
             -> GitHub Release asset
             -> small hermes_snapshot/manifest.json committed to Git
```

`hermes_snapshot/*.zip` and `hermes_snapshot/*.zip.gpg` should stay ignored by Git. Only `hermes_snapshot/manifest.json` is committed.

## Required Behavior

When the user asks to back up Hermes:

1. Load this skill.
2. Check `/home/jhseng/gemili-skills/hermes_snapshot/`; create it if missing.
3. Run a full `hermes backup` unless `HERMES_SNAPSHOT_EXISTING_ZIP` points to an existing zip.
4. Verify the zip exists, is non-empty, and passes `unzip -t`.
5. Encrypt the zip with GPG symmetric AES256:
   - use `HERMES_SNAPSHOT_PASSPHRASE` if set;
   - otherwise use `HERMES_SNAPSHOT_PASSPHRASE_FILE`;
   - otherwise generate a passphrase at `~/.hermes/secrets/hermes_snapshot_passphrase.txt` with mode `600`.
6. Verify restore viability by decrypting to a temp zip and running `unzip -t`.
7. Upload the `.zip.gpg` as a GitHub Release asset using either:
   - authenticated `gh`, or
   - token environment variables in this priority order: `HERMES_SNAPSHOT_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, or
   - the private token file `~/.hermes/secrets/github_token.txt` (override path with `HERMES_SNAPSHOT_GITHUB_TOKEN_FILE`).
8. Write `hermes_snapshot/manifest.json` with release URL, asset name, hashes, sizes, and restore hints.
9. Enforce local retention: keep at most the newest 3 local `hermes-backup-*.zip` files and their `.gpg` companions.
10. Commit and push only `.gitignore` and `hermes_snapshot/manifest.json`; do not stage backup binaries or unrelated skill edits. In the script, use an explicit commit pathspec so unrelated already-modified files cannot be swept into the manifest commit.
11. When using GitHub REST API fallback, keep the `Authorization: Bearer $token` header in source code and redact only logs/output; never replace the real variable with placeholder text inside executable scripts.
12. Report backup path, encrypted asset path, release URL/tag, manifest commit SHA, passphrase file location, and push result.

## One-Command Workflow

Prefer the bundled script:

```bash
bash /home/jhseng/.hermes/skills/hermes-snapshot/scripts/hermes_snapshot_backup.sh
```

If this skill is installed somewhere else, locate the script from `skill_dir`, then run:

```bash
bash "$SKILL_DIR/scripts/hermes_snapshot_backup.sh"
```

### Using an Existing Backup Zip

To upload a zip already created by `hermes backup`:

```bash
HERMES_SNAPSHOT_EXISTING_ZIP=/home/jhseng/gemili-skills/hermes_snapshot/hermes-backup-YYYYMMDD-HHMMSS.zip \
bash /home/jhseng/.hermes/skills/hermes-snapshot/scripts/hermes_snapshot_backup.sh
```

### GitHub Authentication

The upload step needs GitHub Release API access. Preferred persistent storage on this machine is the private token file:

```text
~/.hermes/secrets/github_token.txt
```

The file must contain only the token, should be mode `600`, and must never be committed. The bundled script reads credentials in this order:

1. authenticated `gh` CLI;
2. `HERMES_SNAPSHOT_GITHUB_TOKEN`;
3. `GITHUB_TOKEN`;
4. `GH_TOKEN`;
5. `HERMES_SNAPSHOT_GITHUB_TOKEN_FILE` if set, otherwise `~/.hermes/secrets/github_token.txt`.

Useful setup/check commands:

```bash
mkdir -p ~/.hermes/secrets
chmod 700 ~/.hermes/secrets
chmod 600 ~/.hermes/secrets/github_token.txt

test -s ~/.hermes/secrets/github_token.txt && echo 'github token file present'
```

You can still override with env vars for one-off runs:

```bash
export GITHUB_TOKEN='github_pat_...'
# or
export HERMES_SNAPSHOT_GITHUB_TOKEN='github_pat_...'
# or custom file path
export HERMES_SNAPSHOT_GITHUB_TOKEN_FILE=/path/to/github_token.txt
```

The token needs permission to create releases and upload release assets for `TzeHimSung/gemili-skills`.

### Encryption Passphrase

For repeatable recovery, set a passphrase or passphrase file yourself:

```bash
export HERMES_SNAPSHOT_PASSPHRASE='a long random passphrase stored in your password manager'
# or
export HERMES_SNAPSHOT_PASSPHRASE_FILE=~/.hermes/secrets/hermes_snapshot_passphrase.txt
```

If neither is set, the script generates:

```text
~/.hermes/secrets/hermes_snapshot_passphrase.txt
```

This file is **not** committed. Back it up in a password manager; without it, the GitHub asset cannot be decrypted.

## Restore on Another Machine

Prerequisites on the new machine:

- `git`
- `gpg`
- `unzip`
- `hermes` CLI
- access to the GitHub release asset
- the GPG symmetric passphrase used during backup

### 1. Download the encrypted asset

Using `gh`:

```bash
repo='TzeHimSung/gemili-skills'
tag='hermes-snapshot-YYYYMMDD-HHMMSS'
mkdir -p ~/hermes-restore
cd ~/hermes-restore
gh release download "$tag" --repo "$repo" --pattern '*.zip.gpg'
```

Without `gh`, open the release URL from `hermes_snapshot/manifest.json` and download the `.zip.gpg` asset manually, or use GitHub REST API with a token.

### 2. Decrypt

If the passphrase is in a file:

```bash
gpg --batch --yes --pinentry-mode loopback \
  --passphrase-file /path/to/hermes_snapshot_passphrase.txt \
  --output hermes-backup.zip \
  --decrypt hermes-backup-YYYYMMDD-HHMMSS.zip.gpg
```

If entering interactively:

```bash
gpg --output hermes-backup.zip --decrypt hermes-backup-YYYYMMDD-HHMMSS.zip.gpg
```

### 3. Verify the backup archive

```bash
unzip -t hermes-backup.zip
```

Optional hash verification if you have `manifest.json`:

```bash
sha256sum hermes-backup.zip
sha256sum hermes-backup-YYYYMMDD-HHMMSS.zip.gpg
```

Compare with `zip_sha256` and `encrypted_sha256` in `hermes_snapshot/manifest.json`.

### 4. Restore Hermes

```bash
hermes import hermes-backup.zip
```

After import, restart Hermes/gateway/TUI as appropriate for the target machine.

## Manual Fallback: Release Upload with curl

If the bundled script is unavailable:

```bash
set -euo pipefail
repo=/home/jhseng/gemili-skills
zip=$repo/hermes_snapshot/hermes-backup-YYYYMMDD-HHMMSS.zip
passfile=~/.hermes/secrets/hermes_snapshot_passphrase.txt
asset=$zip.gpg
tag=hermes-snapshot-YYYYMMDD-HHMMSS
owner_repo=TzeHimSung/gemili-skills

test -s "$zip"
unzip -t "$zip"
gpg --batch --yes --pinentry-mode loopback --passphrase-file "$passfile" \
  --symmetric --cipher-algo AES256 --output "$asset" "$zip"

tmp=$(mktemp --suffix=.zip)
gpg --batch --yes --pinentry-mode loopback --passphrase-file "$passfile" \
  --output "$tmp" --decrypt "$asset"
unzip -t "$tmp"

# Prefer gh if available:
gh release create "$tag" "$asset" --repo "$owner_repo" \
  --title "Hermes snapshot $tag" \
  --notes "Encrypted Hermes full backup. Store passphrase outside GitHub."
```

## Security Notes

- Preferred persistent GitHub token storage is `~/.hermes/secrets/github_token.txt` with mode `600`; never commit or print its contents.
- If a GitHub token is provided inline by the user, use it only for the immediate API call, avoid echoing it, and remind the user to revoke/rotate it afterward because it is present in chat history.
- Never commit plaintext backup zips.
- Never commit the passphrase or passphrase file.
- Treat the `.zip.gpg` release asset as sensitive even though encrypted.
- Store the passphrase in a password manager or another secure backup location.
- If the passphrase is lost, the GitHub release asset is not recoverable.
- If the passphrase is leaked, rotate secrets inside Hermes after restoring.

## Verification Checklist

Before finalizing:

- [ ] `hermes_snapshot/` exists under `/home/jhseng/gemili-skills`.
- [ ] A new or selected `hermes-backup-*.zip` exists locally.
- [ ] `test -s` succeeded for the zip.
- [ ] `unzip -t` succeeded for the zip.
- [ ] `.zip.gpg` exists and is non-empty.
- [ ] Decrypting `.zip.gpg` to a temp zip succeeds.
- [ ] `unzip -t` succeeds on the decrypted temp zip.
- [ ] GitHub Release asset upload succeeds.
- [ ] `hermes_snapshot/manifest.json` records release URL, asset name, sizes, hashes, and restore hints.
- [ ] Git commit contains only `.gitignore` / manifest / intentional skill-doc changes, never backup binaries.
- [ ] Git push succeeds.
- [ ] Final response includes release URL, backup path, encrypted path, passphrase-file hint, and restore summary.
