# README Codeizable Workflows Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn the README's highest-value "后续最值得继续代码化" maintenance workflows into scripts/tests, excluding stock-deep-analysis because the README says it needs separate authorization.

**Architecture:** Add small, testable helpers beside existing skill scripts instead of adding new framework dependencies. Encode business rules in deterministic Python or shell, and add regression tests under each skill's existing test area or the top-level tests directory.

**Tech Stack:** Python 3 standard library, pytest, POSIX shell, existing repository layout.

---

### Task 1: Codeize flight-search aliases and price-source semantics

**Objective:** Allow documented city/airport aliases to resolve to IATA codes and make round-trip/segment price provenance explicit.

**Files:**
- Modify: `flight-search/scripts/flight_search.py`
- Create: `tests/test_flight_search.py`

**Step 1: Write failing tests**

Add tests that assert:
- `normalize_iata("广州") == "CAN"`, `normalize_iata("東京") == "TYO"`, `normalize_iata("羽田") == "HND"`, plain `can` still normalizes to `CAN`, and unknown aliases raise `ValueError`.
- `fetch_kiwi_prices()` fed a fake round-trip Kiwi payload creates one outbound offer and one return offer, carries `total_trip_price`, and preserves `deep_link`.
- `attach_prices()` only attaches outbound offers to outbound records and return offers to return records.
- Deep links appear in rendered source lines when present.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_flight_search.py -q`
Expected: FAIL before implementation.

**Step 2: Implement minimal code**

In `flight_search.py`:
- Add an `IATA_ALIASES` dict and `resolve_iata_alias()` helper used by `normalize_iata()`.
- Extend `PriceOffer` with `direction: str = ""` and `total_trip_price: Optional[float] = None`.
- When parsing Amadeus/Kiwi itineraries, mark outbound/return direction. For round trips, preserve the provider's grand total in `total_trip_price`; if only a total is available, expose per-segment display price as `total / segment_count` while noting the total in `raw_match_note`.
- In `attach_prices()`, match by direction when an offer has direction, and append provider deep links as `SourceRecord(provider, deep_link, "booking deep link")`.
- Update CLI help from "IATA airport code" to "IATA airport/city code or known alias".

**Step 3: Verify pass**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_flight_search.py -q`
Expected: PASS.

---

### Task 2: Codeize Anison JST date and official URL consistency

**Objective:** Stop local timezone drift and encode the official BanG Dream/LoveLive URL table as a tested contract.

**Files:**
- Modify: `anison-live-countdown/scripts/common.py`
- Modify: `anison-live-countdown/scripts/generate_report.py`
- Modify: `anison-live-countdown/scripts/scrape_bangdream.py`
- Modify: `anison-live-countdown/scripts/scrape_lovelive.py`
- Modify: `anison-live-countdown/tests/test_common.py`
- Create: `anison-live-countdown/tests/test_official_sources.py`

**Step 1: Write failing tests**

Add tests that assert:
- `jst_today()` uses `Asia/Tokyo` and can be monkeypatched at the module `datetime` level.
- `generate_markdown(..., today=None)` uses `common.jst_today()` instead of system-local `date.today()`.
- `OFFICIAL_SOURCE_URLS` includes exactly the enabled default sources: BanG Dream plus all LoveLive `SERIES_CONFIG` URLs/referers, with http(s) URLs and no Idolmaster source in the default set.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest anison-live-countdown/tests/test_common.py anison-live-countdown/tests/test_official_sources.py anison-live-countdown/tests/test_generate_report.py -q`
Expected: FAIL before implementation.

**Step 2: Implement minimal code**

- Add `jst_today()` to `common.py` using `datetime.now(ZoneInfo("Asia/Tokyo")).date()`.
- Import and use `jst_today()` in `generate_report.py` and `scrape_bangdream.py`.
- In `scrape_lovelive.py`, add `official_source_urls()` returning normalized source records for `SERIES_CONFIG`.
- In `scrape_bangdream.py`, add `official_source_urls()` for `BASE_URL`.

**Step 3: Verify pass**

Run the same pytest command. Expected: PASS.

---

### Task 3: Codeize Kaikatsu geocoding candidate scoring and cache completeness

**Objective:** Make nearest-store queries less dependent on the first Nominatim hit and fail fast when the coordinate cache is incomplete.

**Files:**
- Modify: `kaikatsu-club-vacancy/scripts/kaikatsu_vacancy.py`
- Modify: `kaikatsu-club-vacancy/tests/test_kaikatsu_vacancy.py`

**Step 1: Write failing tests**

Add tests that assert:
- Multiple Nominatim candidates are scored so an exact station/airport-like Japanese name can beat a generic distant administrative result even if it appears second.
- `fetch_store_catalog()` raises `KaikatsuError` when the ratio of coordinate-enriched stores is below a configurable threshold.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest kaikatsu-club-vacancy/tests/test_kaikatsu_vacancy.py -q`
Expected: FAIL before implementation.

**Step 2: Implement minimal code**

- Change Nominatim request `limit` from 1 to 5.
- Add `_score_geocode_candidate(query, result)` and `_select_best_geocode_candidate(query, results)`.
- Prefer exact/substring name matches, station/airport POI classes/types, then importance; penalize generic administrative boundaries.
- Add `min_coordinate_coverage: float = 0.8` to `fetch_store_catalog()`. If parsed stores exist but enriched stores are below the threshold, raise a clear `KaikatsuError` with counts.

**Step 3: Verify pass**

Run the same pytest command. Expected: PASS.

---

### Task 4: Codeize update-fedora-packages into a fixed script with dry-run tests

**Objective:** Move the prompt-only dnf/dnf5/sudo -n flow into a reusable script that cron can call safely.

**Files:**
- Create: `update-fedora-packages/scripts/update_fedora_packages.sh`
- Create: `update-fedora-packages/tests/test_update_fedora_packages.py`
- Modify: `update-fedora-packages/SKILL.md`
- Modify: `README.md`

**Step 1: Write failing tests**

Add tests that assert the script:
- Exists and is executable.
- Contains `sudo -n` for non-interactive execution.
- Does not contain `system-upgrade`.
- Supports `--dry-run` and uses check-upgrade/check-update in dry-run/verify mode.
- The skill references the script path.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest update-fedora-packages/tests/test_update_fedora_packages.py -q`
Expected: FAIL before implementation.

**Step 2: Implement minimal code**

- Write a strict shell script (`set -u`, `pipefail` when available) that detects Fedora release, selects `dnf5` before `dnf`, supports `--dry-run`, runs `sudo -n <dnf> upgrade --refresh -y` for real mode, and always performs a non-fatal verification check with the correct command.
- Update `SKILL.md` to instruct agents/cron to call the script rather than reconstructing commands from prose.
- Update README's update-fedora and scan-conclusion sections to mention the new script/test.

**Step 3: Verify pass**

Run the same pytest command. Expected: PASS.

---

### Task 5: Final repository verification and review

**Objective:** Prove all codeized workflows pass the repo's normal gates and get an independent review before PR.

**Files:**
- No planned production edits; fixes only if verification/review finds issues.

**Step 1: Run targeted and repo gates**

Run:
```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_flight_search.py anison-live-countdown/tests/test_common.py anison-live-countdown/tests/test_official_sources.py anison-live-countdown/tests/test_generate_report.py kaikatsu-club-vacancy/tests/test_kaikatsu_vacancy.py update-fedora-packages/tests/test_update_fedora_packages.py -q
PYTHONDONTWRITEBYTECODE=1 python3 scripts/skills_audit.py .
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests shared/tests anison-live-countdown/tests cron-multi-platform-delivery/tests kaikatsu-club-vacancy/tests update-fedora-packages/tests -q
git diff --check
```

**Step 2: Independent review**

Use `requesting-code-review` / delegate reviewer on the staged diff. Fix critical/security/logic issues only, then re-run gates.

**Step 3: Commit and PR**

Commit with a conventional message and open a PR against `master`:
```bash
git add -A
git commit -m "feat: codeize README workflow candidates"
git push -u origin HEAD
gh pr create --base master --head feat/codeize-readme-workflows --title "feat: codeize README workflow candidates" --body-file /tmp/codeize-readme-workflows-pr.md
```

If the repo uses `main` locally but the requested base is `master`, verify remote branches before PR creation and use `master` as requested if it exists.
