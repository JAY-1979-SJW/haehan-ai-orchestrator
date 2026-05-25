from scripts.google import domain_taxonomy, surfaces


def test_domain_taxonomy_covers_every_google_surface_once() -> None:
    catalog = surfaces.build_surface_catalog()
    report = domain_taxonomy.build_google_domain_taxonomy()

    surface_keys = [item["key"] for item in catalog["surfaces"]]
    taxonomy_keys = [item["surface_key"] for item in report["domains"]]

    assert sorted(taxonomy_keys) == sorted(surface_keys)
    assert len(taxonomy_keys) == len(set(taxonomy_keys))
    assert report["counts"]["surfaces"] == 50
    assert report["counts"]["domain_groups"] == len(domain_taxonomy.GROUPS)


def test_domain_taxonomy_has_required_labels_for_each_surface() -> None:
    report = domain_taxonomy.build_google_domain_taxonomy()

    for item in report["domains"]:
        assert item["domain_group"] in domain_taxonomy.GROUPS
        assert item["section"]
        assert item["subsection"]
        assert item["handling_policy"]
        assert item["cost_label"]
        assert item["data_classification"]
        assert item["approval_level"] in {
            "readonly_allowed",
            "approval_required_for_mutation",
            "explicit_approval_required",
        }
        assert item["user_can_request"]
        assert "final submit without approval" in item["not_allowed"]


def test_domain_taxonomy_locks_sensitive_boundaries() -> None:
    report = domain_taxonomy.build_google_domain_taxonomy()
    by_key = {item["surface_key"]: item for item in report["domains"]}

    assert by_key["google_account"]["handling_policy"] == "user_present_login_only"
    assert by_key["cloud_billing"]["approval_level"] == "explicit_approval_required"
    assert by_key["cloud_apis_credentials"]["data_classification"] == "secret_sensitive"
    assert by_key["secret_manager"]["data_classification"] == "secret_sensitive"
    assert by_key["ads"]["approval_level"] == "explicit_approval_required"
    assert by_key["google_home"]["approval_level"] == "readonly_allowed"


def test_domain_taxonomy_execution_policy_is_fail_closed() -> None:
    report = domain_taxonomy.build_google_domain_taxonomy()

    assert report["execution_policy"]["login"] == "user_present_only_no_credential_replay"
    assert report["execution_policy"]["secret_export"] == "blocked"
    assert report["execution_policy"]["unknown_domain"] == "fail_closed"
