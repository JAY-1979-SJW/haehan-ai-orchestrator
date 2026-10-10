from scripts.google import vision_usage_gate


def test_google_vision_free_gate_warns_before_monthly_limit() -> None:
    payload = vision_usage_gate.evaluate_vision_monthly_free_gate(
        current_month_units=0,
        image_count=900,
        features=["text_detection"],
    )

    assert payload["ok"] is True
    assert payload["status"] == "warn"
    assert payload["projected_month_units"] == 900
    assert payload["monthly_free_limit_units"] == 1000


def test_google_vision_free_gate_blocks_without_cost_approval_above_limit() -> None:
    payload = vision_usage_gate.evaluate_vision_monthly_free_gate(
        current_month_units=999,
        image_count=2,
        features=["text_detection"],
    )

    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    assert payload["failed_check_ids"] == ["google_vision_monthly_free_units_exceeded"]
    assert payload["cost_approval_required"] is True


def test_google_vision_free_gate_allows_explicit_cost_approval_above_limit() -> None:
    payload = vision_usage_gate.evaluate_vision_monthly_free_gate(
        current_month_units=999,
        image_count=2,
        features=["text_detection"],
        cost_approved=True,
    )

    assert payload["ok"] is True
    assert payload["status"] == "warn"
    assert payload["cost_approved"] is True
    assert payload["cost_approval_required"] is True


def test_google_vision_units_scale_by_feature_count() -> None:
    estimate = vision_usage_gate.estimate_vision_units(
        image_count=500,
        features=["text_detection", "label_detection"],
    )

    assert estimate["billable_items"] == 500
    assert estimate["feature_count"] == 2
    assert estimate["requested_units"] == 1000
    assert estimate["unit_formula"] == "(image_count + page_count) * feature_count"


def test_google_vision_gate_never_outputs_raw_secret_values() -> None:
    payload = vision_usage_gate.evaluate_vision_monthly_free_gate(
        current_month_units=0,
        image_count=1,
        features=["text_detection"],
    )

    assert payload["secret_values_output"] is False
    assert payload["policy"]["raw_secret_output"] == "blocked"
    assert payload["policy"]["api_key_or_service_account_required"] == "secret_action_mode_gate"
