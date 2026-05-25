from scripts.google import android_app_dev_report
from scripts.google.android_app_dev_labels import build_android_app_dev_labels, label_for_surface


def test_android_app_dev_labels_cover_primary_surfaces() -> None:
    labels = build_android_app_dev_labels()

    assert labels["domain_group"] == "android_app_development"
    for surface_key in android_app_dev_report.PRIMARY_SURFACES:
        label = label_for_surface(surface_key)
        assert label["surface_key"] == surface_key
        assert label["cost_label"] != "not_android_app_dev_primary_surface"
        assert label["user_can_request"]


def test_android_app_dev_labels_keep_release_and_secret_gates() -> None:
    labels = build_android_app_dev_labels()

    assert labels["ui_policy"]["state_change"] == "approval_required"
    assert labels["ui_policy"]["secret_export"] == "blocked"
    assert "release rollout" in labels["labels"]["play_console"]["approval_required_for"]
    assert "credential create/update/delete" in labels["labels"]["cloud_apis_credentials"]["approval_required_for"]


def test_android_app_dev_report_uses_precision_evidence() -> None:
    report = android_app_dev_report.build_android_app_dev_report()

    assert report["domain_group"] == "android_app_development"
    assert report["counts"]["surfaces"] == len(android_app_dev_report.PRIMARY_SURFACES)
    assert report["counts"]["final_clicked"] == 0
    assert {surface["surface_key"] for surface in report["surfaces"]} == android_app_dev_report.PRIMARY_SURFACES
    for surface in report["surfaces"]:
        assert surface["android_app_dev_label"]["surface_key"] == surface["surface_key"]
