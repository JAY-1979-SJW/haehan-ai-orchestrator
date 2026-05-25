# Google Domain Taxonomy And Handling Labels

- Generated: 2026-05-25T12:42:22.493801+00:00
- Domain groups: 10
- Surfaces: 50
- Hosts: 32
- Approval surfaces: 45
- Read-only surfaces: 5

## Groups

- `search_entry`: Search / Entry / Public Entry (surfaces=1, approval=0)
- `identity_access`: Identity / Access / Account And SSO (surfaces=1, approval=0)
- `workspace_productivity`: Workspace / Productivity / Private Work Data (surfaces=12, approval=12)
- `cloud_backend`: Cloud / Backend / Server And Infrastructure (surfaces=15, approval=15)
- `ai_model`: AI / Model Tools / AI Execution (surfaces=3, approval=3)
- `android_app`: Android App Development / App Build Release Operate (surfaces=3, approval=2)
- `marketing_seo`: Marketing / SEO / Analytics / Site Growth And Measurement (surfaces=8, approval=8)
- `youtube_creator`: YouTube / Creator / Video Channel Operations (surfaces=2, approval=2)
- `media_private`: Personal Media / Private Media (surfaces=1, approval=1)
- `developer_tools`: Developer Tools / Developer Automation (surfaces=4, approval=2)

## Domain Labels

### Google Home
- Surface: `google_home`
- Group: `search_entry` / `home_and_public_search`
- Host: `www.google.com`
- Handling: `readonly_public_navigation`
- Cost label: `free_public_read`
- Data: `public_read`
- Approval: `readonly_allowed`
- User can request: Open Google Home read-only and identify visible account/project/property context.; Classify Google Home controls under `home_and_public_search` before attaching app UI.; Prepare a dry-run plan for Google Home changes without final submission.
- Approval required for: 
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Account
- Surface: `google_account`
- Group: `identity_access` / `account_security_and_session`
- Host: `myaccount.google.com`
- Handling: `user_present_login_only`
- Cost label: `account_required_no_direct_cost`
- Data: `account_context`
- Approval: `readonly_allowed`
- User can request: Open Google Account read-only and identify visible account/project/property context.; Classify Google Account controls under `account_security_and_session` before attaching app UI.; Prepare a dry-run plan for Google Account changes without final submission.
- Approval required for: 
- Not allowed: credential replay, cookie/session export, final submit without approval

### Gmail
- Surface: `gmail`
- Group: `workspace_productivity` / `mail`
- Host: `mail.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Gmail read-only and identify visible account/project/property context.; Classify Gmail controls under `mail` before attaching app UI.; Prepare a dry-run plan for Gmail changes without final submission.
- Approval required for: send
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Drive
- Surface: `drive`
- Group: `workspace_productivity` / `files`
- Host: `drive.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Google Drive read-only and identify visible account/project/property context.; Classify Google Drive controls under `files` before attaching app UI.; Prepare a dry-run plan for Google Drive changes without final submission.
- Approval required for: upload_share
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Calendar
- Surface: `calendar`
- Group: `workspace_productivity` / `calendar`
- Host: `calendar.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Google Calendar read-only and identify visible account/project/property context.; Classify Google Calendar controls under `calendar` before attaching app UI.; Prepare a dry-run plan for Google Calendar changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Docs
- Surface: `docs`
- Group: `workspace_productivity` / `documents`
- Host: `docs.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Google Docs read-only and identify visible account/project/property context.; Classify Google Docs controls under `documents` before attaching app UI.; Prepare a dry-run plan for Google Docs changes without final submission.
- Approval required for: create_edit
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Sheets
- Surface: `sheets`
- Group: `workspace_productivity` / `spreadsheets`
- Host: `docs.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Google Sheets read-only and identify visible account/project/property context.; Classify Google Sheets controls under `spreadsheets` before attaching app UI.; Prepare a dry-run plan for Google Sheets changes without final submission.
- Approval required for: update
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Cloud Console
- Surface: `cloud_console`
- Group: `cloud_backend` / `project_overview`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `admin_sensitive`
- Approval: `explicit_approval_required`
- User can request: Open Google Cloud Console read-only and identify visible account/project/property context.; Classify Google Cloud Console controls under `project_overview` before attaching app UI.; Prepare a dry-run plan for Google Cloud Console changes without final submission.
- Approval required for: create/update/publish/delete, billing_or_spend_change
- Not allowed: credential replay, cookie/session export, final submit without approval, payment or spend change without explicit approval

### Google Search Console
- Surface: `search_console`
- Group: `marketing_seo` / `seo_indexing_property`
- Host: `search.google.com`
- Handling: `readonly_property_context_then_approval`
- Cost label: `free_reporting_or_spend_billing_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Search Console read-only and identify visible account/project/property context.; Classify Google Search Console controls under `seo_indexing_property` before attaching app UI.; Prepare a dry-run plan for Google Search Console changes without final submission.
- Approval required for: submit
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google AI Studio
- Surface: `ai_studio`
- Group: `ai_model` / `ai_prompt_and_api_key_lab`
- Host: `aistudio.google.com`
- Handling: `readonly_then_approval_for_prompt_key_or_deploy`
- Cost label: `free_tier_or_usage_based_by_product`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google AI Studio read-only and identify visible account/project/property context.; Classify Google AI Studio controls under `ai_prompt_and_api_key_lab` before attaching app UI.; Prepare a dry-run plan for Google AI Studio changes without final submission.
- Approval required for: create_key
- Not allowed: credential replay, cookie/session export, final submit without approval

### Gemini
- Surface: `gemini`
- Group: `ai_model` / `chat_ai_app`
- Host: `gemini.google.com`
- Handling: `readonly_then_approval_for_prompt_key_or_deploy`
- Cost label: `free_tier_or_usage_based_by_product`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Gemini read-only and identify visible account/project/property context.; Classify Gemini controls under `chat_ai_app` before attaching app UI.; Prepare a dry-run plan for Gemini changes without final submission.
- Approval required for: submit_prompt
- Not allowed: credential replay, cookie/session export, final submit without approval

### Android Developers
- Surface: `android_developers`
- Group: `android_app` / `android_docs_and_ui_guidance`
- Host: `developer.android.com`
- Handling: `docs_free_console_approval_gated`
- Cost label: `free_docs_registration_or_usage_based_console`
- Data: `public_read`
- Approval: `readonly_allowed`
- User can request: Open Android Developers read-only and identify visible account/project/property context.; Classify Android Developers controls under `android_docs_and_ui_guidance` before attaching app UI.; Prepare a dry-run plan for Android Developers changes without final submission.
- Approval required for: 
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Play Console
- Surface: `play_console`
- Group: `android_app` / `android_release_testing_store`
- Host: `play.google.com`
- Handling: `docs_free_console_approval_gated`
- Cost label: `free_docs_registration_or_usage_based_console`
- Data: `admin_sensitive`
- Approval: `explicit_approval_required`
- User can request: Open Google Play Console read-only and identify visible account/project/property context.; Classify Google Play Console controls under `android_release_testing_store` before attaching app UI.; Prepare a dry-run plan for Google Play Console changes without final submission.
- Approval required for: release
- Not allowed: credential replay, cookie/session export, final submit without approval, payment or spend change without explicit approval

### Firebase Console
- Surface: `firebase_console`
- Group: `android_app` / `mobile_backend_and_analytics`
- Host: `console.firebase.google.com`
- Handling: `docs_free_console_approval_gated`
- Cost label: `free_docs_registration_or_usage_based_console`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Firebase Console read-only and identify visible account/project/property context.; Classify Firebase Console controls under `mobile_backend_and_analytics` before attaching app UI.; Prepare a dry-run plan for Firebase Console changes without final submission.
- Approval required for: deploy
- Not allowed: credential replay, cookie/session export, final submit without approval

### YouTube
- Surface: `youtube`
- Group: `youtube_creator` / `video_viewing_interaction`
- Host: `www.youtube.com`
- Handling: `readonly_channel_context_then_approval`
- Cost label: `free_viewing_publish_or_monetization_policy_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open YouTube read-only and identify visible account/project/property context.; Classify YouTube controls under `video_viewing_interaction` before attaching app UI.; Prepare a dry-run plan for YouTube changes without final submission.
- Approval required for: public_interaction
- Not allowed: credential replay, cookie/session export, final submit without approval

### YouTube Studio
- Surface: `youtube_studio`
- Group: `youtube_creator` / `channel_upload_publish_analytics`
- Host: `studio.youtube.com`
- Handling: `readonly_channel_context_then_approval`
- Cost label: `free_viewing_publish_or_monetization_policy_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open YouTube Studio read-only and identify visible account/project/property context.; Classify YouTube Studio controls under `channel_upload_publish_analytics` before attaching app UI.; Prepare a dry-run plan for YouTube Studio changes without final submission.
- Approval required for: edit, upload_publish
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Slides
- Surface: `slides`
- Group: `workspace_productivity` / `presentations`
- Host: `docs.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Google Slides read-only and identify visible account/project/property context.; Classify Google Slides controls under `presentations` before attaching app UI.; Prepare a dry-run plan for Google Slides changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Forms
- Surface: `forms`
- Group: `workspace_productivity` / `forms_and_responses`
- Host: `docs.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Google Forms read-only and identify visible account/project/property context.; Classify Google Forms controls under `forms_and_responses` before attaching app UI.; Prepare a dry-run plan for Google Forms changes without final submission.
- Approval required for: create_publish
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Meet
- Surface: `meet`
- Group: `workspace_productivity` / `meetings`
- Host: `meet.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Meet read-only and identify visible account/project/property context.; Classify Google Meet controls under `meetings` before attaching app UI.; Prepare a dry-run plan for Google Meet changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Chat
- Surface: `chat`
- Group: `workspace_productivity` / `messaging`
- Host: `chat.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Chat read-only and identify visible account/project/property context.; Classify Google Chat controls under `messaging` before attaching app UI.; Prepare a dry-run plan for Google Chat changes without final submission.
- Approval required for: send
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Contacts
- Surface: `contacts`
- Group: `workspace_productivity` / `contacts`
- Host: `contacts.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Google Contacts read-only and identify visible account/project/property context.; Classify Google Contacts controls under `contacts` before attaching app UI.; Prepare a dry-run plan for Google Contacts changes without final submission.
- Approval required for: create_update
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Keep
- Surface: `keep`
- Group: `workspace_productivity` / `notes`
- Host: `keep.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Keep read-only and identify visible account/project/property context.; Classify Google Keep controls under `notes` before attaching app UI.; Prepare a dry-run plan for Google Keep changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Tasks
- Surface: `tasks`
- Group: `workspace_productivity` / `tasks`
- Host: `tasks.google.com`
- Handling: `api_preferred_readonly_then_approval`
- Cost label: `workspace_plan_or_account_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Tasks read-only and identify visible account/project/property context.; Classify Google Tasks controls under `tasks` before attaching app UI.; Prepare a dry-run plan for Google Tasks changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Photos
- Surface: `photos`
- Group: `media_private` / `private_photo_library`
- Host: `photos.google.com`
- Handling: `readonly_private_media_then_approval`
- Cost label: `account_storage_plan_dependent`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Google Photos read-only and identify visible account/project/property context.; Classify Google Photos controls under `private_photo_library` before attaching app UI.; Prepare a dry-run plan for Google Photos changes without final submission.
- Approval required for: upload_share
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Maps Platform
- Surface: `maps_platform`
- Group: `cloud_backend` / `maps_api_billing_keys`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `admin_sensitive`
- Approval: `explicit_approval_required`
- User can request: Open Google Maps Platform read-only and identify visible account/project/property context.; Classify Google Maps Platform controls under `maps_api_billing_keys` before attaching app UI.; Prepare a dry-run plan for Google Maps Platform changes without final submission.
- Approval required for: change
- Not allowed: credential replay, cookie/session export, final submit without approval, payment or spend change without explicit approval

### Google Business Profile
- Surface: `business_profile`
- Group: `marketing_seo` / `public_business_listing`
- Host: `business.google.com`
- Handling: `readonly_property_context_then_approval`
- Cost label: `free_reporting_or_spend_billing_dependent`
- Data: `public_read`
- Approval: `explicit_approval_required`
- User can request: Open Google Business Profile read-only and identify visible account/project/property context.; Classify Google Business Profile controls under `public_business_listing` before attaching app UI.; Prepare a dry-run plan for Google Business Profile changes without final submission.
- Approval required for: post_update
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Analytics
- Surface: `analytics`
- Group: `marketing_seo` / `web_app_analytics`
- Host: `analytics.google.com`
- Handling: `readonly_property_context_then_approval`
- Cost label: `free_reporting_or_spend_billing_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Analytics read-only and identify visible account/project/property context.; Classify Google Analytics controls under `web_app_analytics` before attaching app UI.; Prepare a dry-run plan for Google Analytics changes without final submission.
- Approval required for: export_configure
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Tag Manager
- Surface: `tag_manager`
- Group: `marketing_seo` / `tag_container_publish`
- Host: `tagmanager.google.com`
- Handling: `readonly_property_context_then_approval`
- Cost label: `free_reporting_or_spend_billing_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Tag Manager read-only and identify visible account/project/property context.; Classify Google Tag Manager controls under `tag_container_publish` before attaching app UI.; Prepare a dry-run plan for Google Tag Manager changes without final submission.
- Approval required for: publish
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Ads
- Surface: `ads`
- Group: `marketing_seo` / `paid_ads_campaigns`
- Host: `ads.google.com`
- Handling: `readonly_property_context_then_approval`
- Cost label: `free_reporting_or_spend_billing_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Ads read-only and identify visible account/project/property context.; Classify Google Ads controls under `paid_ads_campaigns` before attaching app UI.; Prepare a dry-run plan for Google Ads changes without final submission.
- Approval required for: campaign_change
- Not allowed: credential replay, cookie/session export, final submit without approval, payment or spend change without explicit approval

### Google Merchant Center
- Surface: `merchant_center`
- Group: `marketing_seo` / `product_listing_feed`
- Host: `merchants.google.com`
- Handling: `readonly_property_context_then_approval`
- Cost label: `free_reporting_or_spend_billing_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Merchant Center read-only and identify visible account/project/property context.; Classify Google Merchant Center controls under `product_listing_feed` before attaching app UI.; Prepare a dry-run plan for Google Merchant Center changes without final submission.
- Approval required for: product_update
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google AdSense
- Surface: `adsense`
- Group: `marketing_seo` / `site_monetization`
- Host: `adsense.google.com`
- Handling: `readonly_property_context_then_approval`
- Cost label: `free_reporting_or_spend_billing_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google AdSense read-only and identify visible account/project/property context.; Classify Google AdSense controls under `site_monetization` before attaching app UI.; Prepare a dry-run plan for Google AdSense changes without final submission.
- Approval required for: change
- Not allowed: credential replay, cookie/session export, final submit without approval

### Looker Studio
- Surface: `looker_studio`
- Group: `marketing_seo` / `reports_dashboards`
- Host: `lookerstudio.google.com`
- Handling: `readonly_property_context_then_approval`
- Cost label: `free_reporting_or_spend_billing_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Looker Studio read-only and identify visible account/project/property context.; Classify Looker Studio controls under `reports_dashboards` before attaching app UI.; Prepare a dry-run plan for Looker Studio changes without final submission.
- Approval required for: create_share
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google for Developers
- Surface: `google_developers`
- Group: `developer_tools` / `google_api_docs_index`
- Host: `developers.google.com`
- Handling: `public_docs_readonly_console_actions_approval_gated`
- Cost label: `free_docs_usage_or_execution_dependent`
- Data: `public_read`
- Approval: `readonly_allowed`
- User can request: Open Google for Developers read-only and identify visible account/project/property context.; Classify Google for Developers controls under `google_api_docs_index` before attaching app UI.; Prepare a dry-run plan for Google for Developers changes without final submission.
- Approval required for: 
- Not allowed: credential replay, cookie/session export, final submit without approval

### Chrome for Developers
- Surface: `chrome_developers`
- Group: `developer_tools` / `chrome_webview_pwa_docs`
- Host: `developer.chrome.com`
- Handling: `public_docs_readonly_console_actions_approval_gated`
- Cost label: `free_docs_usage_or_execution_dependent`
- Data: `public_read`
- Approval: `readonly_allowed`
- User can request: Open Chrome for Developers read-only and identify visible account/project/property context.; Classify Chrome for Developers controls under `chrome_webview_pwa_docs` before attaching app UI.; Prepare a dry-run plan for Chrome for Developers changes without final submission.
- Approval required for: 
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Apps Script
- Surface: `apps_script`
- Group: `developer_tools` / `workspace_script_automation`
- Host: `script.google.com`
- Handling: `public_docs_readonly_console_actions_approval_gated`
- Cost label: `free_docs_usage_or_execution_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Apps Script read-only and identify visible account/project/property context.; Classify Google Apps Script controls under `workspace_script_automation` before attaching app UI.; Prepare a dry-run plan for Google Apps Script changes without final submission.
- Approval required for: deploy
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Colab
- Surface: `colab`
- Group: `developer_tools` / `notebook_runtime`
- Host: `colab.research.google.com`
- Handling: `public_docs_readonly_console_actions_approval_gated`
- Cost label: `free_docs_usage_or_execution_dependent`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Colab read-only and identify visible account/project/property context.; Classify Google Colab controls under `notebook_runtime` before attaching app UI.; Prepare a dry-run plan for Google Colab changes without final submission.
- Approval required for: execute
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Cloud APIs and Credentials
- Surface: `cloud_apis_credentials`
- Group: `cloud_backend` / `apis_credentials_oauth`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `secret_sensitive`
- Approval: `explicit_approval_required`
- User can request: Open Google Cloud APIs and Credentials read-only and identify visible account/project/property context.; Classify Google Cloud APIs and Credentials controls under `apis_credentials_oauth` before attaching app UI.; Prepare a dry-run plan for Google Cloud APIs and Credentials changes without final submission.
- Approval required for: create_key
- Not allowed: credential replay, cookie/session export, final submit without approval, secret value export

### Google Cloud IAM
- Surface: `cloud_iam`
- Group: `cloud_backend` / `identity_access_management`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `admin_sensitive`
- Approval: `explicit_approval_required`
- User can request: Open Google Cloud IAM read-only and identify visible account/project/property context.; Classify Google Cloud IAM controls under `identity_access_management` before attaching app UI.; Prepare a dry-run plan for Google Cloud IAM changes without final submission.
- Approval required for: iam_change
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Cloud Billing
- Surface: `cloud_billing`
- Group: `cloud_backend` / `billing_budget_payment`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `admin_sensitive`
- Approval: `explicit_approval_required`
- User can request: Open Google Cloud Billing read-only and identify visible account/project/property context.; Classify Google Cloud Billing controls under `billing_budget_payment` before attaching app UI.; Prepare a dry-run plan for Google Cloud Billing changes without final submission.
- Approval required for: billing_change
- Not allowed: credential replay, cookie/session export, final submit without approval, payment or spend change without explicit approval

### Cloud Run
- Surface: `cloud_run`
- Group: `cloud_backend` / `serverless_runtime`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Cloud Run read-only and identify visible account/project/property context.; Classify Cloud Run controls under `serverless_runtime` before attaching app UI.; Prepare a dry-run plan for Cloud Run changes without final submission.
- Approval required for: deploy
- Not allowed: credential replay, cookie/session export, final submit without approval

### Compute Engine
- Surface: `compute_engine`
- Group: `cloud_backend` / `virtual_machines_network_disks`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Compute Engine read-only and identify visible account/project/property context.; Classify Compute Engine controls under `virtual_machines_network_disks` before attaching app UI.; Prepare a dry-run plan for Compute Engine changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### Cloud Storage
- Surface: `cloud_storage`
- Group: `cloud_backend` / `object_storage`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Cloud Storage read-only and identify visible account/project/property context.; Classify Cloud Storage controls under `object_storage` before attaching app UI.; Prepare a dry-run plan for Cloud Storage changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### BigQuery
- Surface: `bigquery`
- Group: `cloud_backend` / `data_warehouse`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open BigQuery read-only and identify visible account/project/property context.; Classify BigQuery controls under `data_warehouse` before attaching app UI.; Prepare a dry-run plan for BigQuery changes without final submission.
- Approval required for: query_export
- Not allowed: credential replay, cookie/session export, final submit without approval

### Google Kubernetes Engine
- Surface: `gke`
- Group: `cloud_backend` / `kubernetes_clusters`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Google Kubernetes Engine read-only and identify visible account/project/property context.; Classify Google Kubernetes Engine controls under `kubernetes_clusters` before attaching app UI.; Prepare a dry-run plan for Google Kubernetes Engine changes without final submission.
- Approval required for: apply
- Not allowed: credential replay, cookie/session export, final submit without approval

### Cloud SQL
- Surface: `cloud_sql`
- Group: `cloud_backend` / `managed_database`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Cloud SQL read-only and identify visible account/project/property context.; Classify Cloud SQL controls under `managed_database` before attaching app UI.; Prepare a dry-run plan for Cloud SQL changes without final submission.
- Approval required for: change
- Not allowed: credential replay, cookie/session export, final submit without approval

### Pub/Sub
- Surface: `pubsub`
- Group: `cloud_backend` / `messaging_topics`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Pub/Sub read-only and identify visible account/project/property context.; Classify Pub/Sub controls under `messaging_topics` before attaching app UI.; Prepare a dry-run plan for Pub/Sub changes without final submission.
- Approval required for: create_publish
- Not allowed: credential replay, cookie/session export, final submit without approval

### Secret Manager
- Surface: `secret_manager`
- Group: `cloud_backend` / `secrets`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `secret_sensitive`
- Approval: `explicit_approval_required`
- User can request: Open Secret Manager read-only and identify visible account/project/property context.; Classify Secret Manager controls under `secrets` before attaching app UI.; Prepare a dry-run plan for Secret Manager changes without final submission.
- Approval required for: create_update
- Not allowed: credential replay, cookie/session export, final submit without approval, secret value export

### Cloud Logging
- Surface: `cloud_logging`
- Group: `cloud_backend` / `logs`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `private_or_account_data`
- Approval: `explicit_approval_required`
- User can request: Open Cloud Logging read-only and identify visible account/project/property context.; Classify Cloud Logging controls under `logs` before attaching app UI.; Prepare a dry-run plan for Cloud Logging changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### Cloud Monitoring
- Surface: `cloud_monitoring`
- Group: `cloud_backend` / `metrics_alerts`
- Host: `console.cloud.google.com`
- Handling: `readonly_project_context_then_approval`
- Cost label: `usage_based_or_billing_project_required`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Cloud Monitoring read-only and identify visible account/project/property context.; Classify Cloud Monitoring controls under `metrics_alerts` before attaching app UI.; Prepare a dry-run plan for Cloud Monitoring changes without final submission.
- Approval required for: create
- Not allowed: credential replay, cookie/session export, final submit without approval

### Vertex AI
- Surface: `vertex_ai`
- Group: `ai_model` / `cloud_ai_training_deploy`
- Host: `console.cloud.google.com`
- Handling: `readonly_then_approval_for_prompt_key_or_deploy`
- Cost label: `free_tier_or_usage_based_by_product`
- Data: `account_context`
- Approval: `explicit_approval_required`
- User can request: Open Vertex AI read-only and identify visible account/project/property context.; Classify Vertex AI controls under `cloud_ai_training_deploy` before attaching app UI.; Prepare a dry-run plan for Vertex AI changes without final submission.
- Approval required for: job_deploy
- Not allowed: credential replay, cookie/session export, final submit without approval
