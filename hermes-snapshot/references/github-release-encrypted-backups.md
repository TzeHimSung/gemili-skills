# GitHub Release Encrypted Hermes Backups

## Why this reference exists

A full `hermes backup` can exceed GitHub's ordinary 100MB blob limit and can contain sensitive Hermes state. Do not solve this by committing the zip, rewriting the repo around Git LFS, or leaving recovery instructions only in chat.

The durable pattern is:

```text
hermes backup zip
  -> verify with unzip -t
  -> encrypt with GPG symmetric AES256
  -> verify by decrypting to a temp zip and running unzip -t again
  -> upload .zip.gpg as a GitHub Release asset
  -> commit only a small manifest.json and documentation
```

## Learned failure mode

If a plaintext backup zip is committed to normal Git history, GitHub rejects pushes once the blob is over 100MB, for example with `GH001: Large files detected`. The safe remediation is to remove the large backup commit before pushing, add `hermes_snapshot/*.zip` and `hermes_snapshot/*.zip.gpg` to `.gitignore`, and use Release assets instead.

## Authentication gate

The upload step requires one of:

- authenticated `gh`; or
- `HERMES_SNAPSHOT_GITHUB_TOKEN`; or
- `GITHUB_TOKEN`; or
- `GH_TOKEN`; or
- a private token file at `~/.hermes/secrets/github_token.txt` (override with `HERMES_SNAPSHOT_GITHUB_TOKEN_FILE`).

This is setup state, not a skill failure. If missing, report that encryption and local verification completed but Release upload is blocked until the user provides a token with repository Contents read/write permission. Do not commit or print the token file contents.

## Security contract

- Never commit plaintext `.zip` backups.
- Never commit `.zip.gpg` binaries to normal Git history; they belong in GitHub Release assets.
- Never commit or print the passphrase.
- Never commit or print the GitHub token. Prefer `~/.hermes/secrets/github_token.txt` with mode `600` for durable local API access.
- Generate/store the passphrase under `~/.hermes/secrets/hermes_snapshot_passphrase.txt` with mode `600` if the user has not provided one.
- The user must store that passphrase outside the repo, e.g. in a password manager.

## Restore drill summary

On another machine:

1. Download the `.zip.gpg` Release asset.
2. Obtain the passphrase from the user's external secret store.
3. Decrypt:

```bash
gpg --batch --yes --pinentry-mode loopback \
  --passphrase-file /path/to/hermes_snapshot_passphrase.txt \
  --output hermes-backup.zip \
  --decrypt hermes-backup-YYYYMMDD-HHMMSS.zip.gpg
```

4. Verify:

```bash
unzip -t hermes-backup.zip
```

5. Restore:

```bash
hermes import hermes-backup.zip
```

6. Restart Hermes/gateway/TUI as appropriate for the target machine.
