#!/usr/bin/env bash
set -Eeuo pipefail

repo="${HERMES_SNAPSHOT_REPO:-/home/jhseng/gemili-skills}"
snapshot_dir="$repo/hermes_snapshot"
passphrase_file="${HERMES_SNAPSHOT_PASSPHRASE_FILE:-$HOME/.hermes/secrets/hermes_snapshot_passphrase.txt}"
retain_local="${HERMES_SNAPSHOT_RETAIN_LOCAL:-3}"
ts="$(date +%Y%m%d-%H%M%S)"
zip_path="${HERMES_SNAPSHOT_EXISTING_ZIP:-}"
release_tag="${HERMES_SNAPSHOT_RELEASE_TAG:-}"
release_title="${HERMES_SNAPSHOT_RELEASE_TITLE:-}"
owner_repo="${HERMES_SNAPSHOT_GITHUB_REPOSITORY:-}"
manifest_path="$snapshot_dir/manifest.json"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "$1 command not found"
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

repo_owner_from_origin() {
  local url
  url="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
  url="${url#git@github.com:}"
  url="${url#https://github.com/}"
  url="${url%.git}"
  printf '%s' "$url"
}

get_api_token() {
  if [ -n "${HERMES_SNAPSHOT_GITHUB_TOKEN:-}" ]; then
    printf '%s' "$HERMES_SNAPSHOT_GITHUB_TOKEN"
  elif [ -n "${GITHUB_TOKEN:-}" ]; then
    printf '%s' "$GITHUB_TOKEN"
  elif [ -n "${GH_TOKEN:-}" ]; then
    printf '%s' "$GH_TOKEN"
  else
    return 1
  fi
}

ensure_passphrase_file() {
  mkdir -p "$(dirname "$passphrase_file")"
  chmod 700 "$(dirname "$passphrase_file")" 2>/dev/null || true
  if [ -n "${HERMES_SNAPSHOT_PASSPHRASE:-}" ]; then
    umask 077
    printf '%s' "$HERMES_SNAPSHOT_PASSPHRASE" > "$passphrase_file"
    echo "passphrase_source=HERMES_SNAPSHOT_PASSPHRASE"
  elif [ -s "$passphrase_file" ]; then
    echo "passphrase_source=$passphrase_file"
  else
    umask 077
    openssl rand -base64 48 > "$passphrase_file"
    echo "passphrase_source=generated:$passphrase_file"
  fi
  chmod 600 "$passphrase_file"
}

create_backup_if_needed() {
  mkdir -p "$snapshot_dir"
  if [ -n "$zip_path" ]; then
    [ -s "$zip_path" ] || die "existing zip missing or empty: $zip_path"
    return
  fi
  zip_path="$snapshot_dir/hermes-backup-$ts.zip"
  echo "Creating full Hermes backup..."
  echo "Output: $zip_path"
  hermes backup --output "$zip_path"
}

verify_zip() {
  [ -s "$zip_path" ] || die "backup zip missing or empty: $zip_path"
  if command -v unzip >/dev/null 2>&1; then
    unzip -t "$zip_path" >/tmp/hermes_snapshot_unzip_test.log
  else
    python3 - "$zip_path" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as zf:
    bad = zf.testzip()
    if bad:
        raise SystemExit(f"bad zip member: {bad}")
PY
  fi
}

encrypt_and_verify() {
  encrypted_path="$zip_path.gpg"
  gpg --batch --yes --pinentry-mode loopback \
    --passphrase-file "$passphrase_file" \
    --symmetric --cipher-algo AES256 \
    --output "$encrypted_path" "$zip_path"
  [ -s "$encrypted_path" ] || die "encrypted asset missing or empty: $encrypted_path"

  tmp_restore="$(mktemp --suffix=.zip)"
  trap 'rm -f "$tmp_restore"' RETURN
  gpg --batch --yes --pinentry-mode loopback \
    --passphrase-file "$passphrase_file" \
    --output "$tmp_restore" --decrypt "$encrypted_path" >/tmp/hermes_snapshot_gpg_verify.log 2>&1
  unzip -t "$tmp_restore" >/tmp/hermes_snapshot_decrypted_unzip_test.log
}

create_release_with_gh() {
  command -v gh >/dev/null 2>&1 || return 1
  gh auth status >/dev/null 2>&1 || return 1
  if gh release view "$release_tag" --repo "$owner_repo" >/dev/null 2>&1; then
    gh release upload "$release_tag" "$encrypted_path" --repo "$owner_repo" --clobber
  else
    gh release create "$release_tag" "$encrypted_path" \
      --repo "$owner_repo" \
      --target "$(git -C "$repo" rev-parse HEAD)" \
      --title "$release_title" \
      --notes "Encrypted Hermes full backup. Store the passphrase outside GitHub."
  fi
  release_url="https://github.com/$owner_repo/releases/tag/$release_tag"
}

create_release_with_api() {
  local token create_json response upload_url upload_response asset_name
  token="$(get_api_token)" || return 1
  asset_name="$(basename "$encrypted_path")"
  create_json="$(python3 - "$release_tag" "$release_title" "$(git -C "$repo" rev-parse HEAD)" <<'PY'
import json, sys
print(json.dumps({
    "tag_name": sys.argv[1],
    "name": sys.argv[2],
    "target_commitish": sys.argv[3],
    "body": "Encrypted Hermes full backup. Store the passphrase outside GitHub.",
    "draft": False,
    "prerelease": False,
}))
PY
)"
  response="$(mktemp)"
  http_code="$(curl -sS -o "$response" -w '%{http_code}' \
    -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer $token" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/$owner_repo/releases" \
    -d "$create_json")"
  if [ "$http_code" = "422" ]; then
    # Release already exists; fetch it and upload/replace asset.
    http_code="$(curl -sS -o "$response" -w '%{http_code}' \
      -H "Accept: application/vnd.github+json" \
      -H "Authorization: Bearer $token" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "https://api.github.com/repos/$owner_repo/releases/tags/$release_tag")"
  fi
  [ "$http_code" = "200" ] || [ "$http_code" = "201" ] || die "GitHub release API failed with HTTP $http_code: $(cat "$response")"
  upload_url="$(python3 - "$response" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)
print(data['upload_url'].split('{', 1)[0])
PY
)"
  release_url="$(python3 - "$response" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)
print(data.get('html_url', ''))
PY
)"
  upload_response="$(mktemp)"
  http_code="$(curl -sS -o "$upload_response" -w '%{http_code}' \
    -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer $token" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "@$encrypted_path" \
    "${upload_url}?name=${asset_name}")"
  [ "$http_code" = "201" ] || die "GitHub asset upload failed with HTTP $http_code: $(cat "$upload_response")"
}

write_manifest() {
  local zip_size encrypted_size sha256_zip sha256_gpg created_at
  created_at="$(date -Iseconds)"
  zip_size="$(wc -c < "$zip_path" | tr -d ' ')"
  encrypted_size="$(wc -c < "$encrypted_path" | tr -d ' ')"
  sha256_zip="$(sha256sum "$zip_path" | cut -d' ' -f1)"
  sha256_gpg="$(sha256sum "$encrypted_path" | cut -d' ' -f1)"
  python3 - "$manifest_path" <<PY
import json
manifest = {
  "created_at": "$created_at",
  "repository": "$owner_repo",
  "release_tag": "$release_tag",
  "release_url": "$release_url",
  "local_zip_path": "$zip_path",
  "encrypted_asset_name": "$(basename "$encrypted_path")",
  "encrypted": True,
  "encryption": "gpg symmetric AES256",
  "passphrase_file_hint": "$passphrase_file",
  "zip_size_bytes": int("$zip_size"),
  "encrypted_size_bytes": int("$encrypted_size"),
  "zip_sha256": "$sha256_zip",
  "encrypted_sha256": "$sha256_gpg",
  "restore_summary": "Download the .zip.gpg release asset, decrypt with gpg using the passphrase, verify unzip -t, then run hermes import <zip>."
}
with open("$manifest_path", "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
}

local_retention() {
  mapfile -t all_zips < <(find "$snapshot_dir" -maxdepth 1 -type f -name 'hermes-backup-*.zip' -printf '%f\n' | sort)
  if [ "${#all_zips[@]}" -gt "$retain_local" ]; then
    prune_count=$((${#all_zips[@]} - retain_local))
    for zip_name in "${all_zips[@]:0:$prune_count}"; do
      rm -f -- "$snapshot_dir/$zip_name" "$snapshot_dir/$zip_name.gpg"
      echo "pruned_local=$snapshot_dir/$zip_name"
    done
  fi
}

commit_manifest() {
  cd "$repo"
  if ! grep -qx 'hermes_snapshot/*.zip' .gitignore 2>/dev/null; then
    printf '\n# Local Hermes backups can exceed GitHub limits and may contain secrets.\nhermes_snapshot/*.zip\n' >> .gitignore
  fi
  if ! grep -qx 'hermes_snapshot/*.zip.gpg' .gitignore 2>/dev/null; then
    printf 'hermes_snapshot/*.zip.gpg\n' >> .gitignore
  fi
  git add .gitignore hermes_snapshot/manifest.json
  if git diff --cached --quiet -- .gitignore hermes_snapshot/manifest.json; then
    echo "manifest_commit=<none>"
    return
  fi
  git commit -m "backup: record hermes snapshot $ts manifest" -- .gitignore hermes_snapshot/manifest.json
  manifest_commit="$(git rev-parse --short HEAD)"
  git pull --rebase --autostash
  git push
  echo "manifest_commit=$manifest_commit"
}

main() {
  need_cmd hermes
  need_cmd gpg
  need_cmd openssl
  need_cmd git
  need_cmd python3
  need_cmd curl
  [ -d "$repo" ] || die "skills repository not found: $repo"
  git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git repository: $repo"
  if [ -z "$owner_repo" ]; then owner_repo="$(repo_owner_from_origin)"; fi
  [ -n "$owner_repo" ] || die "cannot derive GitHub owner/repo"

  create_backup_if_needed
  verify_zip
  ensure_passphrase_file
  encrypt_and_verify

  if [ -z "$release_tag" ]; then
    base="$(basename "$zip_path" .zip)"
    release_tag="hermes-snapshot-${base#hermes-backup-}"
  fi
  if [ -z "$release_title" ]; then
    release_title="Hermes snapshot ${release_tag#hermes-snapshot-}"
  fi

  if ! create_release_with_gh; then
    create_release_with_api || die "GitHub upload requires either authenticated gh or HERMES_SNAPSHOT_GITHUB_TOKEN/GITHUB_TOKEN/GH_TOKEN"
  fi
  write_manifest
  local_retention
  commit_manifest

  echo ""
  echo "Hermes encrypted snapshot release completed."
  echo "backup_path=$zip_path"
  echo "encrypted_path=$encrypted_path"
  echo "release_tag=$release_tag"
  echo "release_url=$release_url"
  echo "manifest_path=$manifest_path"
  echo "passphrase_file=$passphrase_file"
  echo "git_push=success"
}

main "$@"
