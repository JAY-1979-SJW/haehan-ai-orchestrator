# 죽은 코드 후보 (2026-10-01 측정)

측정 방법: `vulture`(신뢰도 60% 이상)가 미사용으로 지목한 **모듈 최상위 함수·클래스** 중, 이름이 저장소 전체 텍스트
(코드·설정·문서·스크립트)에서 정의 한 곳에만 나오는 것(A). 메서드는 상속·동적 호출 오탐이 많아 제외했다.
라우트 데코레이터·`__all__`·`test_`·진입점은 제외. 동적 디스패치(`getattr(mod, 'cmd_' + x)`)는 이름 검색에 안 잡히므로
삭제 전 호출 규칙을 사람이 확인해야 한다.

## 1단계 — 삭제 완료 (비공개 도우미 17개)
- `core/agent_runtime/browser/bridge/browser_websocket_handshake.py`: `_get_hostname_hash`(함수,L0)
- `core/agent_runtime/tools/kras_connector.py`: `_http_error_detail`(함수,L0)
- `scripts/cdp_client.py`: `_load_daemon_state`(함수,L0)
- `scripts/browser/cdp/cdp_daemon.py`: `_clear_session_restore_artifacts`(함수,L0)
- `scripts/eum/auth.py`: `_prepare_login_page`(함수,L0)
- `scripts/eum/shared/layout_openpyxl.py`: `_make_border`(함수,L0), `_pt_to_px`(함수,L0)
- `scripts/google/precision_report.py`: `_host_from_surface`(함수,L0)
- `scripts/mk_catalog/detail_page_template.py`: `_rounded_photo`(함수,L0)
- `tools/quality/module_quality_gate_checks_web.py`: `_npm_audit_command`(함수,L0)
- `scripts/naver/blog/seo/assets.py`: `_click_next_blog_index`(함수,L0)
- `scripts/naver/browser_gate.py`: `_norm_path`(함수,L0)
- `scripts/ops/export_cafe_keywords_excel.py`: `_cell`(함수,L0)
- `scripts/ops/popup/windows_auth_popup_monitor.py`: `_get_foreground_title`(함수,L0)
- `scripts/site_engine/site_access.py`: `_find_or_open_tab`(함수,L0)
- `scripts/video/ig_dm_bot_ep01_visuals.py`: `_diagram_card`(함수,L0)
- `scripts/video/record_promo.py`: `_video_dir`(함수,L0)

복원: `git show <삭제 커밋>^:<경로>` 로 삭제 직전 내용을 볼 수 있다.

## 2단계 — 삭제하지 않음: 연결 안 된 안전 검사·기록 함수 (21개)
호출되지 않는 게이트·검증·차단·기록 함수다. 지우면 "보호가 연결되지 않았다"는 사실만 묻히므로 결함으로 등록해
연결 여부를 확인한다(결함 #116). `scripts/browser/cdp/cdp_db.py` 의 기록 함수는 결함 #16(항상 0행인 테이블)의 원인이다.
- `ai_orchestrator/browser_tool/policy.py`: `requires_dry_run_only`(function,L88)
- `core/agent_runtime/runtime/universal/unknown_site_fallback_policy.py`: `is_allowed_on_unknown_site`(function,L93)
- `core/agent_runtime/runtime/universal/workflow_template_engine.py`: `get_step_risk_level`(function,L170)
- `ai_orchestrator/server/external_url_blocker.py`: `guard_server_playwright_invocation`(function,L110), `is_browser_module_call_blocked`(function,L133)
- `scripts/browser/cdp/cdp_db.py`: `log_request`(function,L158), `log_mail_send`(function,L335), `update_mail_send`(function,L370), `update_automation_run`(function,L454), `log_security_event`(function,L555)
- `scripts/g2b/validators.py`: `validate_notice_search_payload`(function,L91), `validate_notice_detail_payload`(function,L98), `validate_attachment_payload`(function,L111), `validate_bid_analysis_draft_payload`(function,L122), `validate_submit_draft_payload`(function,L131)
- `scripts/google/gates.py`: `gate_google_search`(function,L22), `gate_google_publish_plan`(function,L65)
- `scripts/naver/cafe/write/join_request.py`: `approve_join_submit`(function,L188)
- `scripts/naver/shopping/gate.py`: `gate_order_write`(function,L48), `gate_price_change`(function,L67)
- `scripts/youtube/gates.py`: `gate_youtube_read`(function,L12)

## 3단계 — 사용자 판단 필요: 공개 함수·클래스 (78개)
지금은 호출되지 않지만 기능 도구함·캠페인 도우미일 수 있다. 삭제 전 소유자 확인이 필요하다.
- `ai_orchestrator/browser_tool/policy/site_access_compatibility_auditor.py`: `build_site_access_audit_target`(function,L43), `build_site_access_audit_result`(function,L242)
- `ai_orchestrator/clients/telegram_sender.py`: `answer_callback_query`(function,L96)
- `ai_orchestrator/connectors/instagram/instagram_dm_db.py`: `set_legacy_ig_user_id`(function,L234)
- `tools/gates/auth.py`: `get_tenant_context`(function,L176)
- `ai_orchestrator/agent_hub/action_registry.py`: `list_action_names`(function,L22), `list_actions_by_grade`(function,L26)
- `ai_orchestrator/contracts/action_risk_policy.py`: `get_all_delegatable_actions`(function,L118), `get_all_blocked_actions`(function,L122)
- `scripts/browser/agent/approval_api_client.py`: `approval_api_configured`(function,L34)
- `scripts/browser/agent/browser_session.py`: `wait_for_user_action`(function,L128)
- `scripts/browser/agent/sitemap_detector.py`: `detect_selectors_by_network`(function,L93)
- `core/agent_runtime/runtime/permission/delegated_permission_store.py`: `get_store_snapshot`(function,L96)
- `core/agent_runtime/runtime/universal/generic_selector_discovery.py`: `get_risk_button_types`(function,L134)
- `scripts/naver/blog/naver_content_safe_result.py`: `build_publish_result`(function,L104)
- `core/agent_runtime/runtime/site_profile/selector_pack_registry.py`: `is_pack_registered`(function,L91)
- `core/agent_runtime/runtime/site_profile/site_capability_matrix.py`: `get_all_capabilities`(function,L153)
- `core/agent_runtime/runtime/site_profile/site_profile_registry.py`: `get_all_site_ids`(function,L323)
- `core/agent_runtime/runtime/task_client.py`: `poll_loop`(function,L130)
- `core/agent_runtime/runtime/notify/user_attention_notifier.py`: `build_timeout_notice`(function,L61), `build_cancel_notice`(function,L70)
- `core/agent_runtime/runtime/universal/workflow_template_engine.py`: `get_all_workflow_ids`(function,L162)
- `ai_orchestrator/openai_client.py`: `generate_plan_explanation`(function,L30)
- `ai_orchestrator/persistence/registration_code_store.py`: `reset_store_for_tests`(function,L779)
- `ai_orchestrator/router.py`: `TelegramWebhookBody`(class,L162)
- `ai_orchestrator/server/action_task_api.py`: `api_get_approval_request`(function,L168), `api_list_approval_requests`(function,L172), `api_get_evidence`(function,L179), `api_list_evidence`(function,L183)
- `apps/ig-comment-dm-bot/core/settings_store.py`: `load_rules`(function,L44)
- `core/agent_runtime/agent.py`: `poll_task`(function,L110)
- `core/agent_runtime/browser/browser_action_executor.py`: `build_request_from_payload`(function,L355)
- `core/agent_runtime/browser/browser_controller.py`: `BrowserApprovalError`(class,L113), `BrowserSensitiveFieldError`(class,L119), `create_and_inspect`(function,L663)
- `core/agent_runtime/browser/browser_realtime_watcher.py`: `detect_login_states`(function,L170)
- `core/agent_runtime/browser/bridge/browser_websocket_schema.py`: `safe_result_dict`(function,L497)
- `core/agent_runtime/gui/gui_chat_state.py`: `mode_label_kr`(function,L24), `ai_status_label_kr`(function,L40), `ChatUiController`(class,L99)
- `scripts/browser/cdp/browser_tab_monitor.py`: `ensure_single_tab`(function,L138)
- `scripts/community/sites/iboss.py`: `list_board`(function,L53), `fetch_post_detail`(function,L99)
- `scripts/google/developer/__init__.py`: `android_app_labels`(function,L23), `android_app_report`(function,L27)
- `scripts/inquiry/store.py`: `looks_like_contact`(function,L108)
- `scripts/instagram/api_publish.py`: `publish_story`(function,L177), `get_media_insights`(function,L201), `get_account_insights`(function,L208), `search_hashtag_id`(function,L227), `get_hashtag_media`(function,L241), `get_media_comments`(function,L260), `reply_to_comment`(function,L266), `get_content_publishing_limit`(function,L278)
- `scripts/instagram/kotara_ctc_reel.py`: `render_thumbnail`(function,L133), `render_all_frames`(function,L404), `strip_audio`(function,L557), `extract_check_frames`(function,L565)
- `scripts/common/logger.py`: `enable_debug`(function,L111), `disable_debug`(function,L116)
- `scripts/naver/blog/marketing/multichannel.py`: `generate_community_answer`(function,L91)
- `scripts/naver/mail/collection/background_runner.py`: `find_mail_target_id`(function,L63)
- `scripts/naver/mail/collection/folder_discovery.py`: `folders_to_dicts`(function,L344)
- `scripts/naver/mail/processing/read_state_guard.py`: `snapshot_unread_count`(function,L173)
- `scripts/naver/mail/read/cdp.py`: `find_target`(function,L24), `screenshot_png`(function,L91)
- `scripts/naver/smartstore/navigation/cdp_popup_manager.py`: `quick_handle`(function,L603)
- `scripts/naver/smartstore/product/ai_description_writer.py`: `build_trust_summary`(function,L117)
- `scripts/naver/smartstore/product/detail_collector.py`: `list_cached_product_ids`(function,L86)
- `tools/repo_gates/codebase_layer_audit.py`: `issue_key`(function,L1303)
- `scripts/browser/popup/popup_monitor.py`: `ChromeUIWatcher`(class,L366), `chrome_ui_status`(function,L463)
- `scripts/browser/session/session_tracker.py`: `clear_state`(function,L32), `all_states`(function,L37)
- `scripts/video/_cdp_tab.py`: `TabCDP`(class,L20), `close_tab`(function,L105)
- `scripts/video/scripted_recorder.py`: `place_chrome`(function,L179)
- `scripts/web_connector.py`: `shutdown_browser_session`(function,L563)

## 제외
- `scripts/mk_catalog/vision_extract.py` (2개): GPT 비전 호출 코드는 정책상 코드 레벨에서 차단돼 있고 재활성화는 사용자 승인 사항이라 보존한다.
- 테스트에서만 참조되는 최상위 함수·클래스 178개(B): 삭제하려면 테스트도 같이 지워야 해서 이번 범위에서 제외.

## 진행 기록
- 2026-10-01 1단계(비공개 도우미 17개) 삭제 완료.
- 2026-10-01 3단계 중 분류 D(공개 함수·클래스 22개) 삭제 완료(사용자 승인). 분류 K(유지 23개: Instagram Graph API 래퍼·디버그 토글·레지스트리 접근자·영상 도구), F(연결 누락 의심 10개), R(소유자 판단 23개)는 보존.
