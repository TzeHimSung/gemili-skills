# UZI-Skill Known Bugs & Fixes (v3.2.0)

Apply these patches before running stage2 if errors occur.

## Bug 1: special_cards.py — f-string backslash escape (Python 3.12+)

**Symptom:**
```
SyntaxError: f-string expression part cannot include a backslash
```

**File:** `lib/report/special_cards.py` line ~500

**Fix:**
```python
# BEFORE (broken):
f'      {f"· <span style=\"color:#9ca3af\">—{skip}</span>" if skip else ""}'

# AFTER (fixed):
f'      {("<span style=color:#9ca3af>—" + str(skip) + "</span>") if skip else ""}'
```

---

## Bug 2: institutional.py — missing svg_sparkline and svg_radar imports

**Symptom:**
```
NameError: name 'svg_sparkline' is not defined
NameError: name 'svg_radar' is not defined
```

**File:** `lib/report/institutional.py` line ~28

**Fix** — add both to the import:
```python
# BEFORE:
from lib.report.svg_primitives import (
    COLOR_BULL, COLOR_BEAR, COLOR_GOLD, COLOR_CYAN, COLOR_MUTED,
    svg_gauge, svg_progress_row,
)

# AFTER:
from lib.report.svg_primitives import (
    COLOR_BULL, COLOR_BEAR, COLOR_GOLD, COLOR_CYAN, COLOR_MUTED,
    svg_gauge, svg_progress_row, svg_sparkline, svg_radar,
)
```

---

## Bug 3: Stage2 blocked by self-review for missing A-share-only dimensions

**Symptom:**
```
RuntimeError: ⛔ BLOCKED by self-review: NVDA 有 8 个 critical 问题待修
```
Missing dimensions: `4_peers`, `5_chain`, `6_research`, `12_capital_flow`, `14_moat`, `17_sentiment`, `18_trap`, `19_contests`

**Fix:** For US stocks, these dimensions either don't apply (A-share specific: lhb/sentiment/contests) or need agent_analysis.json to fill. Either:
1. Write all missing dims in `agent_analysis.json` → then `UZI_SKIP_REVIEW=1` to bypass
2. Or re-run stage1 with `--no-resume` to force re-fetch

**Quick bypass (debug only):** `UZI_SKIP_REVIEW=1 python3 -c "from run_real_test import stage2; stage2('TICKER')"`

---

## Bug 4: DCF returns ¥0 for US stocks

**Symptom:** DCF intrinsic_value_per_share = 0 (currency mismatch, RMB symbol in output)

**Status:** Not fully fixed. DCF engine may not handle USD-denominated stocks properly. Agent must manually override in agent_analysis.json.
