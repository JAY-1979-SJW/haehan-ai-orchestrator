# Google Live Input No-Final-Submit Report - 2026-05-13

## Rule

Live input was run with `--no-final-submit`.

Final state-changing controls were not clicked:

- Gmail `Send`
- Cloud IAM `Grant` / `Save` / `Add`
- Search Console `Request indexing`
- YouTube Studio `Next` / `Publish`

## Results

| Action | Result | Filled | Not Filled / Needs Check | Evidence |
| --- | --- | --- | --- | --- |
| `cloud_iam_change_role` | partial success | `project`, `principal`, role picker typed | role visual selection needs manual check | `data/google_live_inputs/google_live_input_cloud_iam_change_role_20260512_215941.json` |
| `gmail_send_email` | success | `to`, `subject`, `body`, local image attachment | none; Gmail may autosave draft, Send not clicked | `data/google_live_inputs/google_live_input_gmail_send_email_20260512_223018.json` |
| `search_console_submit_indexing` | success | `url` | none; indexing request not clicked | `data/google_live_inputs/google_live_input_search_console_submit_indexing_20260512_220659.json` |
| `youtube_studio_upload_video` | partial success | local video file selected/upload draft created, description entered by follow-up direct input | title auto-filled from file name; publish/next not clicked | `data/google_live_inputs/google_live_input_youtube_studio_upload_video_20260512_221345.json` |
| `gmail_send_email` with image | superseded by successful run | `to`, `subject`, `body`, local image attachment | earlier compose/recipient selector issue fixed | `data/google_live_inputs/google_live_input_gmail_send_email_20260512_223018.json` |

## Added Hardening

- Manifest batch live-fill added:
  `python scripts\cdp_client.py google work live-fill-manifest <manifest.json> --no-final-submit`
- Live-fill coverage command added:
  `python scripts\cdp_client.py google work live-coverage`
- Template added:
  `configs/google_live_input_manifest_template.json`
- Final-control detection is saved in each live input artifact under
  `final_control_policy.detected_controls`.
- Latest coverage artifact:
  `data/google_live_input_coverage_latest.json`
- Current coverage: 9 approval actions support no-final-submit live input or
  safe handoff; 37 approval actions remain prepare/open-only.
- Full read-only Google surface exploration completed separately:
  `docs/reports/google_surface_exploration_completion_report_20260513.md`
- Additional safe pre-final adapters added for:
  `youtube_studio_edit_video_metadata`, `search_console_submit_sitemap`,
  `ai_studio_create_api_key`, `cloud_create_api_credential`, and
  `play_console_prepare_release`.

## Notes

- Local test video: `tmp/google_live_assets/haehan_google_input_test.mp4`
- Local test image: `tmp/google_live_assets/haehan_google_input_test.png`
- Play Console release, AI Studio key creation, Cloud credential creation, and
  other high-risk workflows now have safe pre-final handoff adapters, but
  real releases/keys/credential creation still require explicit approval.
- All runs preserved the final approval boundary.

## Follow-Up Fixes

- Gmail recipient selector was fixed for Korean Gmail combobox markup.
- Cloud IAM role selector needs a visual selection verification step after
  typing the role.
- Manifest should be copied to a run-specific file with real values/artifacts
  before filling all remaining workflows.
