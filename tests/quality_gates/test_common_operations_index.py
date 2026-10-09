from tools.repo_gates.validate_common_operations_index import _load_index, validate_index


def test_common_operations_index_is_valid() -> None:
    data = _load_index()
    assert validate_index(data) == []


def test_common_operations_index_includes_core_sites() -> None:
    data = _load_index()
    site_ids = {site["site_id"] for site in data["sites"]}
    assert {
        "orchestrator",
        "homepage",
        "eum",
        "hiworks",
        "naver",
        "smartstore",
        "g2b",
        "google",
    }.issubset(site_ids)
