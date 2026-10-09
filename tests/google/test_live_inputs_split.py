"""google live_inputs 모듈 분리 검증 (공개 API 보존)."""


def test_config_leaf_separated():
    """설정/상수/env 헬퍼는 live_inputs_config 공유 leaf 로 분리된다."""
    from scripts.google.common import live_inputs_config as c
    for name in ("ROOT", "LIVE_INPUT_ADAPTERS", "_env_int", "_page_timeout",
                 "DOMAIN_SPECIFIC_PREFILL_MODES"):
        assert hasattr(c, name), f"config 누락: {name}"


def test_public_api_preserved_via_facade():
    """live_inputs 파사드가 공개 API 와 내부 이름을 모두 재노출한다."""
    from scripts.google.common import live_inputs as li
    for name in ("ROOT", "_env_int", "DOMAIN_SPECIFIC_PREFILL_MODES",
                 "build_live_input_coverage", "run_live_input"):
        assert hasattr(li, name), f"파사드 누락: {name}"


def test_all_leaves_separated_and_facade():
    """live_inputs 가 6개 leaf 로 분리되고 파사드가 공개 API 를 보존한다."""
    import importlib
    for leaf in ("config", "cdp", "coverage", "fill", "domain_fillers", "report"):
        importlib.import_module(f"scripts.google.common.live_inputs_{leaf}")
    from scripts.google.common import live_inputs as li
    for name in ("run_live_input", "run_live_input_manifest", "build_live_input_coverage",
                 "print_live_input_summary", "_fill_gmail_send", "_cdp_fill_first"):
        assert hasattr(li, name), f"파사드 누락: {name}"


def test_root_is_thin():
    """live_inputs 루트는 ≤400 LOC (오케스트레이션+파사드)."""
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "google" / "common" / "live_inputs.py"
    assert sum(1 for _ in p.open(encoding="utf-8")) <= 400
