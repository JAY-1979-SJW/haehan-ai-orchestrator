# Google Common SSO/OAuth Policy Coverage

Generated: 2026-05-25T23:58:34

## Summary

- surfaces: 50
- hosts: 32
- page_tabs: 185
- approval_surfaces: 50
- common policy: covered for every listed Google surface

## Common Policy

- connection_sequence: `google_home -> account_state -> target_subdomain -> approval_url`
- direct_oauth_entry_allowed: `False`
- agent_non_secret_prefill_allowed_when_observable: `True`
- final_external_create_requires_user: `True`
- local_cli_preferred_oauth_client: `desktop_app`
- web_app_client_for_local_cli_allowed: `False`
- mismatch_error_code: `OAUTH_CLIENT_REDIRECT_SCOPE_MISMATCH`
- direct_oauth_error_code: `SSO_DIRECT_OAUTH_ENTRY_BLOCKED`

## Surface Coverage

| Surface | Host | Group | Risk | Access | Approval | Page tabs | Policy |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `google_home` | `www.google.com` | `search_entry` | `read` | `browser_readonly` | `readonly_allowed` | 3 | `covered_common_sso_oauth_policy` |
| `google_account` | `myaccount.google.com` | `identity_access` | `auth_sensitive` | `manual_or_oauth_only` | `readonly_allowed` | 5 | `covered_common_sso_oauth_policy` |
| `gmail` | `mail.google.com` | `workspace_productivity` | `private_data` | `api_preferred` | `explicit_approval_required` | 5 | `covered_common_sso_oauth_policy` |
| `drive` | `drive.google.com` | `workspace_productivity` | `private_data` | `api_preferred` | `explicit_approval_required` | 5 | `covered_common_sso_oauth_policy` |
| `calendar` | `calendar.google.com` | `workspace_productivity` | `private_data_write_possible` | `api_preferred` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `docs` | `docs.google.com` | `workspace_productivity` | `private_data_write_possible` | `api_preferred` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `sheets` | `docs.google.com` | `workspace_productivity` | `private_data_write_possible` | `api_preferred` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `cloud_console` | `console.cloud.google.com` | `cloud_backend` | `billing_infra_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `search_console` | `search.google.com` | `marketing_seo` | `site_property_data` | `manual_live_read_or_api` | `explicit_approval_required` | 5 | `covered_common_sso_oauth_policy` |
| `ai_studio` | `aistudio.google.com` | `ai_model` | `model_key_project_write_possible` | `manual_live_read` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `gemini` | `gemini.google.com` | `ai_model` | `private_prompt_data` | `manual_live_read` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `android_developers` | `developer.android.com` | `android_app` | `public_read` | `browser_readonly` | `readonly_allowed` | 3 | `covered_common_sso_oauth_policy` |
| `play_console` | `play.google.com` | `android_app` | `app_release_billing_write_possible` | `manual_live_read` | `explicit_approval_required` | 5 | `covered_common_sso_oauth_policy` |
| `firebase_console` | `console.firebase.google.com` | `android_app` | `infra_data_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 5 | `covered_common_sso_oauth_policy` |
| `youtube` | `www.youtube.com` | `youtube_creator` | `account_media_interaction` | `browser_readonly` | `explicit_approval_required` | 7 | `covered_common_sso_oauth_policy` |
| `youtube_studio` | `studio.youtube.com` | `youtube_creator` | `channel_publish_monetization_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 10 | `covered_common_sso_oauth_policy` |
| `slides` | `docs.google.com` | `workspace_productivity` | `private_data_write_possible` | `api_preferred` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `forms` | `docs.google.com` | `workspace_productivity` | `private_data_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `meet` | `meet.google.com` | `workspace_productivity` | `meeting_join_or_create_possible` | `manual_live_read` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `chat` | `chat.google.com` | `workspace_productivity` | `message_send_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `contacts` | `contacts.google.com` | `workspace_productivity` | `contact_data_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `keep` | `keep.google.com` | `workspace_productivity` | `note_data_write_possible` | `manual_live_read` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `tasks` | `tasks.google.com` | `workspace_productivity` | `task_data_write_possible` | `api_preferred` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `photos` | `photos.google.com` | `media_private` | `private_media_write_possible` | `manual_live_read` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `maps_platform` | `console.cloud.google.com` | `cloud_backend` | `api_key_billing_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `business_profile` | `business.google.com` | `marketing_seo` | `public_business_listing_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `analytics` | `analytics.google.com` | `marketing_seo` | `analytics_config_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `tag_manager` | `tagmanager.google.com` | `marketing_seo` | `site_tag_publish_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 5 | `covered_common_sso_oauth_policy` |
| `ads` | `ads.google.com` | `marketing_seo` | `ad_spend_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `merchant_center` | `merchants.google.com` | `marketing_seo` | `product_listing_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `adsense` | `adsense.google.com` | `marketing_seo` | `monetization_config_write_possible` | `manual_live_read` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `looker_studio` | `lookerstudio.google.com` | `marketing_seo` | `report_data_share_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `google_developers` | `developers.google.com` | `developer_tools` | `public_read` | `browser_readonly` | `readonly_allowed` | 3 | `covered_common_sso_oauth_policy` |
| `chrome_developers` | `developer.chrome.com` | `developer_tools` | `public_read` | `browser_readonly` | `readonly_allowed` | 3 | `covered_common_sso_oauth_policy` |
| `apps_script` | `script.google.com` | `developer_tools` | `script_deploy_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `colab` | `colab.research.google.com` | `developer_tools` | `notebook_code_execution_possible` | `manual_live_read` | `explicit_approval_required` | 4 | `covered_common_sso_oauth_policy` |
| `cloud_apis_credentials` | `console.cloud.google.com` | `cloud_backend` | `credential_key_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `cloud_iam` | `console.cloud.google.com` | `cloud_backend` | `iam_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `cloud_billing` | `console.cloud.google.com` | `cloud_backend` | `billing_write_possible` | `manual_live_read` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `cloud_run` | `console.cloud.google.com` | `cloud_backend` | `deploy_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `compute_engine` | `console.cloud.google.com` | `cloud_backend` | `compute_resource_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `cloud_storage` | `console.cloud.google.com` | `cloud_backend` | `storage_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `bigquery` | `console.cloud.google.com` | `cloud_backend` | `data_query_or_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `gke` | `console.cloud.google.com` | `cloud_backend` | `cluster_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `cloud_sql` | `console.cloud.google.com` | `cloud_backend` | `database_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `pubsub` | `console.cloud.google.com` | `cloud_backend` | `messaging_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `secret_manager` | `console.cloud.google.com` | `cloud_backend` | `secret_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `cloud_logging` | `console.cloud.google.com` | `cloud_backend` | `logs_private_data` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `cloud_monitoring` | `console.cloud.google.com` | `cloud_backend` | `monitoring_config_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
| `vertex_ai` | `console.cloud.google.com` | `ai_model` | `model_training_deploy_write_possible` | `manual_live_read_or_api` | `explicit_approval_required` | 3 | `covered_common_sso_oauth_policy` |
