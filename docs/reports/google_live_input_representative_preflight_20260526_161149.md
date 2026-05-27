# Google Live Input Representative Preflight

- Status: passed
- Generated at: 2026-05-26T16:11:49.213672+00:00
- Live browser opened: False
- External state change: False
- Approval actions: 46
- Live input supported: 46
- Prepare/open-only: 0

## Checks

- approval_actions_46: True
- live_input_supported_46: True
- prepare_or_open_only_zero: True
- representatives_supported: True
- representatives_ready: True
- state_change_false: True

## Representatives

### gmail_send_email

- Surface: gmail
- Adapter mode: safe_pre_final_input
- Ready for approval: True
- Missing inputs: -
- State change: False
- Live command:

```text
python scripts\cdp_client.py google work live-fill C:\work\01. haehan-ai-orchestrator\data\google_prepares\google_prepare_gmail_send_email_20260526_161149.json --no-final-submit
```

### search_console_submit_sitemap

- Surface: search_console
- Adapter mode: safe_pre_final_input
- Ready for approval: True
- Missing inputs: -
- State change: False
- Live command:

```text
python scripts\cdp_client.py google work live-fill C:\work\01. haehan-ai-orchestrator\data\google_prepares\google_prepare_search_console_submit_sitemap_20260526_161149.json --no-final-submit
```

### cloud_create_api_credential

- Surface: cloud_apis_credentials
- Adapter mode: safe_secret_issue_final_click_ready
- Ready for approval: True
- Missing inputs: -
- State change: False
- Live command:

```text
python scripts\cdp_client.py google work live-fill C:\work\01. haehan-ai-orchestrator\data\google_prepares\google_prepare_cloud_create_api_credential_20260526_161149.json --no-final-submit
```

### cloud_iam_change_role

- Surface: cloud_iam
- Adapter mode: safe_pre_final_input
- Ready for approval: True
- Missing inputs: -
- State change: False
- Live command:

```text
python scripts\cdp_client.py google work live-fill C:\work\01. haehan-ai-orchestrator\data\google_prepares\google_prepare_cloud_iam_change_role_20260526_161149.json --no-final-submit
```

## Next Step

Run the listed live commands only when a user-present local browser session is ready.
Every command must include `--no-final-submit`; final Send/Submit/Create/Grant controls remain blocked.
