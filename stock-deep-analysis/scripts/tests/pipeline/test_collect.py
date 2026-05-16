"""v3.0.0 Phase 4 · pipeline.collect 测试."""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SCRIPTS))


def test_is_pipeline_enabled_env_flag():
    from lib.pipeline import is_pipeline_enabled
    os.environ.pop("UZI_PIPELINE", None)
    assert is_pipeline_enabled() is False
    os.environ["UZI_PIPELINE"] = "1"
    try:
        assert is_pipeline_enabled() is True
    finally:
        os.environ.pop("UZI_PIPELINE", None)


def test_is_resume_valid_rejects_error_quality():
    from lib.pipeline.collect import _is_resume_valid
    assert _is_resume_valid({"data": {"x": 1}, "quality": "full"}) is True
    assert _is_resume_valid({"data": {}, "quality": "error"}) is False
    assert _is_resume_valid({"data": None, "quality": "missing"}) is False
    assert _is_resume_valid(None) is False
    assert _is_resume_valid({"data": {"x": 1}}) is True  # 老格式兼容


def test_dependent_dims_set():
    from lib.pipeline.collect import DEPENDENT_DIMS, COMPUTE_DIMS
    assert "3_macro" in DEPENDENT_DIMS
    assert "7_industry" in DEPENDENT_DIMS
    assert "9_futures" in DEPENDENT_DIMS
    assert "13_policy" in DEPENDENT_DIMS
    assert COMPUTE_DIMS == {"20_valuation_models", "21_research_workflow", "22_deep_methods"}
    # 0_basic 不应该在
    assert "0_basic" not in DEPENDENT_DIMS
    assert "0_basic" not in COMPUTE_DIMS


def test_compute_dims_receive_full_raw_context_with_top_level_fields(monkeypatch):
    """20-22 compute dim 需要 raw['similar_stocks'] / fund_managers 等顶层溢出字段。"""
    import importlib
    collect_mod = importlib.import_module("lib.pipeline.collect")
    from lib.pipeline import Quality

    captured = {}

    class FakeResult:
        quality = Quality.FULL

        def __init__(self, dim_key, data=None, top_level=None):
            self.dim_key = dim_key
            self.data = data or {"ok": True}
            self.top_level_fields = top_level or {}

        def to_dict(self):
            return {"data": self.data, "_pipeline": {"quality": "full"}}

    class BasicFetcher:
        def fetch(self, ticker):
            return FakeResult("0_basic", {"name": "测试"}, {"similar_stocks": [{"code": "000002.SZ"}]})

    class ComputeFetcher:
        pass

    def fake_get_fetcher(dim_key):
        return BasicFetcher() if dim_key == "0_basic" else ComputeFetcher()

    def fake_fetch_with_context(fetcher, ticker, raw_context):
        captured["raw_context"] = raw_context
        return FakeResult("20_valuation_models", {"summary": {"ok": True}})

    monkeypatch.setattr(collect_mod, "FETCHER_REGISTRY", {"0_basic": object(), "20_valuation_models": object()})
    monkeypatch.setattr(collect_mod, "DEPENDENT_DIMS", set())
    monkeypatch.setattr(collect_mod, "COMPUTE_DIMS", {"20_valuation_models"})
    monkeypatch.setattr(collect_mod, "COMPUTE_DIM_ORDER", ("20_valuation_models",))
    monkeypatch.setattr(collect_mod, "get_fetcher", fake_get_fetcher)
    monkeypatch.setattr(collect_mod, "_fetch_with_context", fake_fetch_with_context)

    collect_mod.collect("000001.SZ")

    assert captured["raw_context"]["dimensions"]["0_basic"]["data"]["name"] == "测试"
    assert captured["raw_context"]["similar_stocks"] == [{"code": "000002.SZ"}]
