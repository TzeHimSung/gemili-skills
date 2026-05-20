"""Pytest isolation for stock-deep-analysis.

Runtime code writes task outputs and API cache under `.cache` by default. Tests should
not create or reuse repository-local runtime cache, because those files may contain
user-specific tickers or stale network responses.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_OWNED_CACHE_DIR: Path | None = None

if "UZI_CACHE_DIR" not in os.environ:
    _OWNED_CACHE_DIR = Path(tempfile.mkdtemp(prefix="stock-deep-pytest-cache-"))
    os.environ["UZI_CACHE_DIR"] = str(_OWNED_CACHE_DIR)


def pytest_sessionfinish(session, exitstatus):  # pragma: no cover - pytest hook
    if _OWNED_CACHE_DIR is not None:
        shutil.rmtree(_OWNED_CACHE_DIR, ignore_errors=True)
