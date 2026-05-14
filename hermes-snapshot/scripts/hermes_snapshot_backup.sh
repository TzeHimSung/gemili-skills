#!/usr/bin/env bash
set -Eeuo pipefail

repo="${HERMES_SNAPSHOT_REPO:-/home/jhseng/gemili-skills}"
snapshot_dir="$repo/hermes_snapshot"
ts="$(date +%Y%m%d-%H%M%S)"
out="$snapshot_dir/hermes-backup-$ts.zip"

if ! command -v hermes >/dev/null 2>&1; then
  echo "ERROR: hermes command not found in PATH" >&2
  exit 127
fi

if [ ! -d "$repo" ]; then
  echo "ERROR: skills repository not found: $repo" >&2
  exit 2
fi

if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not a git repository: $repo" >&2
  exit 2
fi

mkdir -p "$snapshot_dir"

echo "Creating full Hermes backup..."
echo "Output: $out"
hermes backup --output "$out"

if [ ! -s "$out" ]; then
  echo "ERROR: backup zip missing or empty: $out" >&2
  exit 3
fi

if command -v unzip >/dev/null 2>&1; then
  unzip -t "$out" >/tmp/hermes_snapshot_unzip_test.log
else
  python3 - "$out" <<'PY'
import sys, zipfile
path = sys.argv[1]
with zipfile.ZipFile(path) as zf:
    bad = zf.testzip()
    if bad:
        raise SystemExit(f"bad zip member: {bad}")
PY
fi

size_bytes="$(wc -c < "$out" | tr -d ' ')"
size_human="$(du -h "$out" | cut -f1)"
remote_url="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"

cd "$repo"

# Retention: keep at most the newest 3 full backup zips in hermes_snapshot/.
# Filenames include YYYYMMDD-HHMMSS, so lexical order matches creation order.
pruned_files=()
mapfile -t all_zips < <(find "hermes_snapshot" -maxdepth 1 -type f -name 'hermes-backup-*.zip' -printf '%f\n' | sort)
if [ "${#all_zips[@]}" -gt 3 ]; then
  prune_count=$((${#all_zips[@]} - 3))
  for zip_name in "${all_zips[@]:0:$prune_count}"; do
    pruned_files+=("hermes_snapshot/$zip_name")
  done
  rm -f -- "${pruned_files[@]}"
fi

git add "hermes_snapshot/"

if git diff --cached --quiet -- "hermes_snapshot/"; then
  echo "ERROR: no snapshot changes staged after creating: $out" >&2
  exit 4
fi

git commit -m "backup: hermes snapshot $ts"
commit_sha="$(git rev-parse --short HEAD)"

# Sync without force-push. If remote advanced, rebase this backup commit on top.
git pull --rebase --autostash
git push

echo ""
echo "Hermes snapshot backup completed."
echo "backup_path=$out"
echo "backup_size=$size_human ($size_bytes bytes)"
if [ "${#pruned_files[@]}" -gt 0 ]; then
  printf 'pruned_files=%s\n' "${pruned_files[*]}"
else
  echo "pruned_files=<none>"
fi
echo "retention=max_3_zip_files"
echo "git_commit=$commit_sha"
echo "git_remote=${remote_url:-<no origin remote>}"
echo "git_push=success"
