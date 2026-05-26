# Google Domain Readiness Audit

- Status: `ok`
- Surfaces: `50`
- API/OAuth first: `35`
- Browser read-only fallback: `15`
- CDP selection required: `15`

## Per-Domain Gate

| Surface | Host | Read | Fallback | Approval | Risk | Result |
|---|---|---|---|---|---|---|
| `ai_studio` | `aistudio.google.com` | `user_present_browser_readonly` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `gemini` | `gemini.google.com` | `user_present_browser_readonly` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `vertex_ai` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `android_developers` | `developer.android.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `readonly_allowed` | browser_fallback | PASS |
| `firebase_console` | `console.firebase.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `play_console` | `play.google.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `bigquery` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `cloud_apis_credentials` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | secret_sensitive, approval_actions_present | PASS |
| `cloud_billing` | `console.cloud.google.com` | `user_present_browser_readonly` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `cloud_console` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | standard | PASS |
| `cloud_iam` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `cloud_logging` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `cloud_monitoring` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `cloud_run` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `cloud_sql` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `cloud_storage` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `compute_engine` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `gke` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `maps_platform` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `pubsub` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `secret_manager` | `console.cloud.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | secret_sensitive, approval_actions_present | PASS |
| `apps_script` | `script.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `chrome_developers` | `developer.chrome.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `readonly_allowed` | browser_fallback | PASS |
| `colab` | `colab.research.google.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `google_developers` | `developers.google.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `readonly_allowed` | browser_fallback | PASS |
| `google_account` | `myaccount.google.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `readonly_allowed` | browser_fallback | PASS |
| `ads` | `ads.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `adsense` | `adsense.google.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `analytics` | `analytics.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `business_profile` | `business.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `looker_studio` | `lookerstudio.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `merchant_center` | `merchants.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `search_console` | `search.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `tag_manager` | `tagmanager.google.com` | `official_api_or_oauth_first` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present | PASS |
| `photos` | `photos.google.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `google_home` | `www.google.com` | `user_present_browser_readonly` | `user_present_browser_readonly_or_prepare_only` | `readonly_allowed` | browser_fallback | PASS |
| `calendar` | `calendar.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `chat` | `chat.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `contacts` | `contacts.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `docs` | `docs.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `drive` | `drive.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `forms` | `docs.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `gmail` | `mail.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `keep` | `keep.google.com` | `user_present_browser_readonly` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `meet` | `meet.google.com` | `user_present_browser_readonly` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present, browser_fallback | PASS |
| `sheets` | `docs.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `slides` | `docs.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `tasks` | `tasks.google.com` | `official_api_or_oauth_first` | `official_api_then_user_present_browser_no_final_submit` | `explicit_approval_required` | approval_actions_present | PASS |
| `youtube` | `www.youtube.com` | `user_present_browser_readonly` | `official_api_then_visible_browser_transcript_summary` | `explicit_approval_required` | approval_actions_present, browser_fallback, youtube_like_oauth_or_browser_fallback | PASS |
| `youtube_studio` | `studio.youtube.com` | `official_api_or_oauth_first` | `official_api_then_no_final_submit_browser_handoff` | `explicit_approval_required` | approval_actions_present, youtube_like_oauth_or_browser_fallback | PASS |

## Locked Prevention Rules

- OAuth/API path must be explicit before live Google automation work.
- Browser fallback must use user-present CDP session selection.
- Secret values, credential replay, and final submit without approval remain blocked.
- Blocked work must return a reason and next_step so the next AI can resume safely.
