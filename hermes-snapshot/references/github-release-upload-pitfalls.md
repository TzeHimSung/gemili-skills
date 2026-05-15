# GitHub Release Upload Pitfalls for Encrypted Hermes Snapshots

Use this reference when a Hermes snapshot upload has to use GitHub REST API instead of authenticated `gh`.

## Durable lessons

1. Do not redact the Authorization header inside committed scripts.

Bad source code pattern:

```bash
-H "Authorization: Bearer *** \
```

This is both syntactically broken and unusable. Redaction belongs only in logs/output. Source code should pass the variable:

```bash
-H "Authorization: Bearer $token" \
```

Then redact command output before showing it to the user if needed.

2. Keep secrets out of shell history and logs.

If the user provides a token inline, prefer running the upload from a wrapper that injects the token through the process environment and redacts stdout/stderr before printing. For durable local use, read the token from `~/.hermes/secrets/github_token.txt` (or `HERMES_SNAPSHOT_GITHUB_TOKEN_FILE`) and ensure the file is mode `600`. Do not commit tokens, write them into skill files, or echo them back.

3. Commit only the manifest path.

Snapshot runs often happen while the skill repository has unrelated worktree changes from the broader audit. The backup script should commit with an explicit pathspec:

```bash
git add .gitignore hermes_snapshot/manifest.json
git commit -m "backup: record hermes snapshot $ts manifest" -- .gitignore hermes_snapshot/manifest.json
```

This prevents unrelated skill changes from being swept into the manifest commit.

4. Verify Release asset state through the API.

After upload, fetch the release tag and confirm the asset is present with:

- expected asset name
- expected byte size
- `state == "uploaded"`
- stable `browser_download_url`

5. If GitHub returns 422 for release creation, fetch the existing release by tag and upload/replace the asset there.

This makes reruns idempotent for the same snapshot tag.
