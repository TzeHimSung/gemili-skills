import os
import stat
import subprocess
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parent
SCRIPT = SKILL_DIR / "scripts" / "update_fedora_packages.sh"
SKILL_MD = SKILL_DIR / "SKILL.md"
README = REPO_ROOT / "README.md"


def test_script_exists_and_is_executable():
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, f"{SCRIPT} must be executable by owner"


def test_script_is_noninteractive_and_never_system_upgrade():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "sudo -n" in text
    assert "system-upgrade" not in text


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_dry_run_with_fake_bins(tmp_path: Path, *, include_dnf5: bool) -> tuple[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_file = tmp_path / "commands.log"

    _write_executable(
        bin_dir / "sudo",
        f"""#!/bin/sh
printf 'sudo %s\\n' "$*" >> {log_file}
if [ "$1" = "-n" ]; then
  shift
fi
exec "$@"
""",
    )

    if include_dnf5:
        _write_executable(
            bin_dir / "dnf5",
            f"""#!/bin/sh
printf 'dnf5 %s\\n' "$*" >> {log_file}
exit 0
""",
        )
    else:
        _write_executable(
            bin_dir / "dnf",
            f"""#!/bin/sh
printf 'dnf %s\\n' "$*" >> {log_file}
exit 0
""",
        )

    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    result = subprocess.run(
        [str(SCRIPT), "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    return result.stdout, log_file.read_text(encoding="utf-8")


def test_dry_run_prefers_dnf5_and_uses_check_upgrade(tmp_path):
    output, commands = _run_dry_run_with_fake_bins(tmp_path, include_dnf5=True)

    assert "dry-run" in output.lower()
    assert "sudo -n" in commands
    assert "dnf5 check-upgrade --refresh" in commands
    assert " upgrade --refresh -y" not in commands


def test_dry_run_falls_back_to_dnf_and_uses_check_update(tmp_path):
    output, commands = _run_dry_run_with_fake_bins(tmp_path, include_dnf5=False)

    assert "dry-run" in output.lower()
    assert "sudo -n" in commands
    assert "dnf check-update --refresh" in commands
    assert " upgrade --refresh -y" not in commands


def test_skill_references_fixed_script_path():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "update-fedora-packages/scripts/update_fedora_packages.sh" in text


def test_readme_mentions_fixed_script_and_tests():
    text = README.read_text(encoding="utf-8")
    assert "update-fedora-packages/scripts/update_fedora_packages.sh" in text
    assert "update-fedora-packages/tests/test_update_fedora_packages.py" in text
