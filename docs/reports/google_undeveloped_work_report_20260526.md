# Google Undeveloped Work Report - 2026-05-26

## Summary

- Total Google work actions: 96
- Read-only actions implemented: 50
- Approval actions: 46
- Live input supported with `--no-final-submit`: 9
- Prepare/open-only approval actions: 37
- Missing adapter profiles: 0
- Production final execution by agent: blocked for all 46 approval actions until a separately approved production adapter exists

## Baseline

Google work must follow the locked connection sequence:

```text
Google Home -> My Account -> registered Google subdomain -> OAuth/approval URL
```

Final external state changes remain user-approved. The agent may prepare plans
and may prefill supported non-secret inputs only under `--no-final-submit`.

## Implemented Live Input Actions

- `gmail_send_email`
- `youtube_studio_upload_video`
- `youtube_studio_edit_video_metadata`
- `search_console_submit_indexing`
- `search_console_submit_sitemap`
- `ai_studio_create_api_key`
- `cloud_create_api_credential`
- `cloud_iam_change_role`
- `play_console_prepare_release`

## Prepare/Open-Only Development Backlog

- `drive_upload_share_file`
- `calendar_create_event`
- `docs_create_edit_document`
- `sheets_update_cells`
- `slides_create_presentation`
- `forms_create_publish`
- `meet_create_meeting`
- `chat_send_message`
- `contacts_create_update`
- `keep_create_note`
- `tasks_create_task`
- `photos_upload_share`
- `youtube_comment_or_subscribe`
- `gemini_submit_prompt`
- `firebase_deploy_rules`
- `cloud_billing_budget_or_link`
- `cloud_run_deploy_service`
- `compute_engine_create_vm`
- `cloud_storage_create_bucket`
- `bigquery_run_query_or_export`
- `gke_apply_change`
- `cloud_sql_change_instance`
- `pubsub_create_or_publish`
- `secret_manager_create_update`
- `cloud_logging_create_sink`
- `cloud_monitoring_create_alert`
- `vertex_ai_start_job_or_deploy`
- `apps_script_deploy`
- `colab_execute_notebook`
- `maps_platform_change_key_or_quota`
- `business_profile_post_or_update`
- `analytics_export_or_configure`
- `tag_manager_publish_version`
- `ads_campaign_budget_change`
- `merchant_center_product_update`
- `adsense_ad_unit_or_payment_change`
- `looker_studio_create_or_share_report`

## Verification

```text
python scripts\cdp_client.py google work undeveloped
python -m py_compile scripts\google\workflows.py scripts\google\router.py
python -m pytest tests\test_google_workflows.py tests\test_google_subdomain_logic.py tests\test_google_tab_logic.py -q
python scripts\ops\audit_google_automation_baseline_contract.py
git diff --check
```

All checks passed on 2026-05-26.
