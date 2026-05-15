#!/bin/sh
set -u
if (set -o pipefail) 2>/dev/null; then
  set -o pipefail
fi

usage() {
  printf 'Usage: %s [--dry-run]\n' "$0"
}

read_os_release_value() {
  key=$1
  value=''
  if [ -r /etc/os-release ]; then
    while IFS= read -r line; do
      case "$line" in
        "$key"=*)
          value=${line#*=}
          value=${value#\"}
          value=${value%\"}
          printf '%s\n' "$value"
          return 0
          ;;
      esac
    done < /etc/os-release
  fi
  return 1
}

detect_fedora_release() {
  release=''
  if [ -r /etc/fedora-release ]; then
    IFS= read -r release < /etc/fedora-release || release=''
  fi

  if [ -z "$release" ]; then
    release=$(read_os_release_value PRETTY_NAME 2>/dev/null || true)
  fi

  if [ -z "$release" ]; then
    release='unknown Fedora release'
  fi

  printf '%s\n' "$release"
}

select_dnf() {
  # Never resolve dnf from the inherited PATH before running it under sudo.
  # Cron/gateway environments can have user-writable directories in PATH; only
  # trusted system locations are accepted. Tests may prepend a temporary trusted
  # directory, but only while pytest exposes PYTEST_CURRENT_TEST.
  candidate_dirs=''
  if [ -n "${PYTEST_CURRENT_TEST:-}" ] && [ -n "${HERMES_FEDORA_UPDATE_TEST_BIN_DIR:-}" ]; then
    candidate_dirs="$HERMES_FEDORA_UPDATE_TEST_BIN_DIR"
  fi
  candidate_dirs="$candidate_dirs /usr/bin /usr/local/bin /bin"

  for dir in $candidate_dirs; do
    if [ -x "$dir/dnf5" ]; then
      DNF="$dir/dnf5"
      DNF_FLAVOR='dnf5'
      VERIFY_SUBCOMMAND='check-upgrade'
      return 0
    fi
  done

  for dir in $candidate_dirs; do
    if [ -x "$dir/dnf" ]; then
      DNF="$dir/dnf"
      DNF_FLAVOR='dnf'
      VERIFY_SUBCOMMAND='check-update'
      return 0
    fi
  done

  printf 'error: trusted system dnf5/dnf not found (/usr/bin, /usr/local/bin, /bin)\n' >&2
  exit 127
}

DRY_RUN=0
if [ "$#" -gt 1 ]; then
  usage >&2
  exit 2
fi

if [ "$#" -eq 1 ]; then
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
fi

select_dnf
FEDORA_RELEASE=$(detect_fedora_release)
printf 'fedora_release=%s\n' "$FEDORA_RELEASE"
printf 'package_manager=%s\n' "$DNF_FLAVOR"

update_rc=0
if [ "$DRY_RUN" -eq 1 ]; then
  printf 'mode=dry-run\n'
  printf 'dry_run_update=skipped\n'
else
  printf 'mode=real\n'
  printf 'running=sudo -n %s upgrade --refresh -y\n' "$DNF_FLAVOR"
  sudo -n "$DNF" upgrade --refresh -y
  update_rc=$?
  printf 'upgrade_exit_code=%s\n' "$update_rc"
fi

printf 'verifying=sudo -n %s %s --refresh\n' "$DNF_FLAVOR" "$VERIFY_SUBCOMMAND"
sudo -n "$DNF" "$VERIFY_SUBCOMMAND" --refresh
verify_rc=$?
printf '%s_%s_exit_code=%s\n' "$DNF_FLAVOR" "$VERIFY_SUBCOMMAND" "$verify_rc"

if [ "$DRY_RUN" -eq 1 ]; then
  case "$verify_rc" in
    0|100)
      exit 0
      ;;
    *)
      exit "$verify_rc"
      ;;
  esac
fi

exit "$update_rc"
