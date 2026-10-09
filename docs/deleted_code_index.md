# 삭제된 코드 목록 (2026-09-23 정리)

정리 직전 상태 태그: `backup/pre-cleanup-20260923` (커밋 889e4003). 삭제 파일 653개.

## 복원 방법

```bash
# 파일 하나 / 폴더 통째로 되살리기
git checkout backup/pre-cleanup-20260923 -- scripts/naver/mail/
# 삭제 당시 내용만 보기
git show backup/pre-cleanup-20260923:<경로>
```

git 없이 보려면: `C:\work\_backup\haehan-ai-orchestrator_deleted_20260923.zip` (삭제 파일 전체, 경로 유지 zip).

삭제 근거·검증은 각 커밋 메시지와 `docs/specs/2026-09-23_other_app_code_removal.md` 참고.

## 폴더별 목록

<details><summary><code>admin-web/src</code> — 124개</summary>

- `admin-web/src/app/(legacy)/admin/inquiries/InquiriesClient.tsx`
- `admin-web/src/app/(legacy)/admin/inquiries/page.tsx`
- `admin-web/src/app/(legacy)/admin/licenses/page.tsx`
- `admin-web/src/app/(legacy)/admin/page.tsx`
- `admin-web/src/app/(legacy)/admin/users/page.tsx`
- `admin-web/src/app/(legacy)/agent/AgentClient.tsx`
- `admin-web/src/app/(legacy)/agent/page.tsx`
- `admin-web/src/app/(legacy)/bid/page.tsx`
- `admin-web/src/app/(legacy)/browser-approvals/page.tsx`
- `admin-web/src/app/(legacy)/community/CommunityClient.tsx`
- `admin-web/src/app/(legacy)/community/communityShared.ts`
- `admin-web/src/app/(legacy)/community/page.tsx`
- `admin-web/src/app/(legacy)/community/sections/AutoReports.tsx`
- `admin-web/src/app/(legacy)/community/sections/InstantAnalyze.tsx`
- `admin-web/src/app/(legacy)/community/sections/MonitoredSites.tsx`
- `admin-web/src/app/(legacy)/community/sections/ReportView.tsx`
- `admin-web/src/app/(legacy)/community/sections/TelegramNotify.tsx`
- `admin-web/src/app/(legacy)/dataportal/page.tsx`
- `admin-web/src/app/(legacy)/eum/page.tsx`
- `admin-web/src/app/(legacy)/external-tasks/externalTasksData.ts`
- `admin-web/src/app/(legacy)/external-tasks/page.tsx`
- `admin-web/src/app/(legacy)/file-map/page.tsx`
- `admin-web/src/app/(legacy)/gabia/gabiaData.ts`
- `admin-web/src/app/(legacy)/gabia/page.tsx`
- `admin-web/src/app/(legacy)/google/GoogleChat.tsx`
- `admin-web/src/app/(legacy)/google/GoogleClient.tsx`
- `admin-web/src/app/(legacy)/google/ServiceGrid.tsx`
- `admin-web/src/app/(legacy)/google/[service]/page.tsx`
- `admin-web/src/app/(legacy)/google/[service]/serviceConfig.ts`
- `admin-web/src/app/(legacy)/google/googleCatalog.ts`
- `admin-web/src/app/(legacy)/google/page.tsx`
- `admin-web/src/app/(legacy)/grant-radar/page.tsx`
- `admin-web/src/app/(legacy)/hanafax/page.tsx`
- `admin-web/src/app/(legacy)/local-agents/LocalAgentsClient.tsx`
- `admin-web/src/app/(legacy)/local-agents/RegistrationCodesPanel.tsx`
- `admin-web/src/app/(legacy)/local-agents/components/DetailSections.tsx`
- `admin-web/src/app/(legacy)/local-agents/components/DiagnosticsSection.tsx`
- `admin-web/src/app/(legacy)/local-agents/components/RoleBadge.tsx`
- `admin-web/src/app/(legacy)/local-agents/components/TaskActionCell.tsx`
- `admin-web/src/app/(legacy)/local-agents/components/helpers.ts`
- `admin-web/src/app/(legacy)/local-agents/hooks/useAgentData.ts`
- `admin-web/src/app/(legacy)/local-agents/hooks/useCurrentUser.ts`
- `admin-web/src/app/(legacy)/local-agents/hooks/useModals.ts`
- `admin-web/src/app/(legacy)/local-agents/hooks/usePolling.ts`
- `admin-web/src/app/(legacy)/local-agents/hooks/useTaskData.ts`
- `admin-web/src/app/(legacy)/local-agents/page.tsx`
- `admin-web/src/app/(legacy)/local-agents/registrationCodesData.ts`
- `admin-web/src/app/(legacy)/market-research/MarketResearchClient.tsx`
- `admin-web/src/app/(legacy)/market-research/page.tsx`
- `admin-web/src/app/(legacy)/marketing/MarketingClient.tsx`
- `admin-web/src/app/(legacy)/marketing/MarketingOpsClient.tsx`
- `admin-web/src/app/(legacy)/marketing/page.tsx`
- `admin-web/src/app/(legacy)/server/ServerClient.tsx`
- `admin-web/src/app/(legacy)/server/page.tsx`
- `admin-web/src/app/(legacy)/settings/page.tsx`
- `admin-web/src/app/(legacy)/settings/sites/page.tsx`
- `admin-web/src/app/(legacy)/youtube/UploadCard.tsx`
- `admin-web/src/app/(legacy)/youtube/YoutubeClient.tsx`
- `admin-web/src/app/(legacy)/youtube/page.tsx`
- `admin-web/src/app/(legacy)/youtube/youtubeShared.ts`
- `admin-web/src/app/api/file-map/auth/clear/route.ts`
- `admin-web/src/app/api/file-map/auth/mock-verify/route.ts`
- `admin-web/src/app/api/file-map/auth/status/route.ts`
- `admin-web/src/app/api/file-map/cleanup-approval-request/route.ts`
- `admin-web/src/app/api/file-map/cleanup-audit/route.ts`
- `admin-web/src/app/api/file-map/cleanup-execute/route.ts`
- `admin-web/src/app/api/file-map/cleanup-execution-package/route.ts`
- `admin-web/src/app/api/file-map/cleanup-plan/route.ts`
- `admin-web/src/app/api/file-map/cleanup-preflight/route.ts`
- `admin-web/src/app/api/file-map/cleanup-preview/route.ts`
- `admin-web/src/app/api/file-map/cleanup-rollback/route.ts`
- `admin-web/src/app/api/file-map/report/route.ts`
- `admin-web/src/components/app/AppInstallButton.tsx`
- `admin-web/src/components/file-map/FileMapApprovalRequest.tsx`
- `admin-web/src/components/file-map/FileMapAuditLog.tsx`
- `admin-web/src/components/file-map/FileMapCleanupPlanViewer.tsx`
- `admin-web/src/components/file-map/FileMapCleanupPreview.tsx`
- `admin-web/src/components/file-map/FileMapExecute.tsx`
- `admin-web/src/components/file-map/FileMapExecuteFlow.tsx`
- `admin-web/src/components/file-map/FileMapExecuteResult.tsx`
- `admin-web/src/components/file-map/FileMapExecutionPackage.tsx`
- `admin-web/src/components/file-map/FileMapPreflight.tsx`
- `admin-web/src/components/file-map/FileMapReportViewer.tsx`
- `admin-web/src/components/file-map/approval/ApprovalChecklist.tsx`
- `admin-web/src/components/file-map/approval/ApprovalGroupsList.tsx`
- `admin-web/src/components/file-map/approval/ApprovalHeader.tsx`
- `admin-web/src/components/file-map/approval/ApprovalPolicyNotice.tsx`
- `admin-web/src/components/file-map/approval/ApprovalSummaryCards.tsx`
- `admin-web/src/components/file-map/approval/ExcludedGroupsList.tsx`
- `admin-web/src/components/file-map/execution/ExecutionBlockedOperations.tsx`
- `admin-web/src/components/file-map/execution/ExecutionGroupSelector.tsx`
- `admin-web/src/components/file-map/execution/ExecutionHeader.tsx`
- `admin-web/src/components/file-map/execution/ExecutionOperationsList.tsx`
- `admin-web/src/components/file-map/execution/ExecutionPreflight.tsx`
- `admin-web/src/components/file-map/execution/ExecutionRollbackInfo.tsx`
- `admin-web/src/components/file-map/execution/ExecutionSecurityPolicy.tsx`
- `admin-web/src/components/file-map/execution/ExecutionSummaryCards.tsx`
- `admin-web/src/components/file-map/index.ts`
- `admin-web/src/components/file-map/report/ReportContent.tsx`
- `admin-web/src/components/file-map/report/ReportHeader.tsx`
- `admin-web/src/components/file-map/report/ReportMaskingSettings.tsx`
- `admin-web/src/components/file-map/report/ReportPolicyNotice.tsx`
- `admin-web/src/components/ui/UsageHelp.tsx`
- `admin-web/src/lib/auth-session.ts`
- `admin-web/src/lib/file-map/__tests__/pythonExecutor.test.ts`
- `admin-web/src/lib/file-map/approvalToken.ts`
- `admin-web/src/lib/file-map/executePayload.ts`
- `admin-web/src/lib/file-map/pythonExecutor.ts`
- `admin-web/src/lib/fileMapApproval.ts`
- `admin-web/src/lib/fileMapAudit.ts`
- `admin-web/src/lib/fileMapCleanupPlan.ts`
- `admin-web/src/lib/fileMapExecutor.ts`
- `admin-web/src/lib/fileMapRollback.ts`
- `admin-web/src/lib/fileMapSettings.ts`
- `admin-web/src/lib/localConfig.ts`
- `admin-web/src/lib/privacy.ts`
- `admin-web/src/lib/sitesCatalog.ts`
- `admin-web/src/server/file-map/approvalRequestBuilder.ts`
- `admin-web/src/server/file-map/auditStore.ts`
- `admin-web/src/server/file-map/cleanupPreviewBuilder.ts`
- `admin-web/src/server/file-map/executionPackageBuilder.ts`
- `admin-web/src/server/file-map/planCache.ts`
- `admin-web/src/server/file-map/reportBuilder.ts`
- `admin-web/src/server/file-map/rollbackStore.ts`

</details>

<details><summary><code>agent/tests</code> — 77개</summary>

- `agent/tests/test_agent_readonly.py`
- `agent/tests/test_api_client_unit.py`
- `agent/tests/test_approval_policy_unit.py`
- `agent/tests/test_cleanup_audit.py`
- `agent/tests/test_cleanup_executor.py`
- `agent/tests/test_cleanup_paths.py`
- `agent/tests/test_cleanup_policy.py`
- `agent/tests/test_cleanup_preflight.py`
- `agent/tests/test_cleanup_rollback.py`
- `agent/tests/test_excel_batch_executor.py`
- `agent/tests/test_excel_cell_writer.py`
- `agent/tests/test_excel_change_planner.py`
- `agent/tests/test_excel_change_tracker.py`
- `agent/tests/test_excel_column_writer.py`
- `agent/tests/test_excel_com_connector_unit.py`
- `agent/tests/test_excel_com_smoke.py`
- `agent/tests/test_excel_connector.py`
- `agent/tests/test_excel_copy_saver.py`
- `agent/tests/test_excel_data_validator.py`
- `agent/tests/test_excel_diff_reporter.py`
- `agent/tests/test_excel_formula_scanner.py`
- `agent/tests/test_excel_formula_validator.py`
- `agent/tests/test_excel_formula_writer.py`
- `agent/tests/test_excel_header_detector.py`
- `agent/tests/test_excel_integrations.py`
- `agent/tests/test_excel_original_save_policy.py`
- `agent/tests/test_excel_pack_construction_estimate.py`
- `agent/tests/test_excel_pdf_exporter.py`
- `agent/tests/test_excel_reporter.py`
- `agent/tests/test_excel_row_finder.py`
- `agent/tests/test_excel_row_writer.py`
- `agent/tests/test_excel_structure_analyzer.py`
- `agent/tests/test_excel_style_copier.py`
- `agent/tests/test_excel_summary_sheet_writer.py`
- `agent/tests/test_excel_table_analyzer.py`
- `agent/tests/test_excel_total_validator.py`
- `agent/tests/test_excel_workflows.py`
- `agent/tests/test_file_policy_edges.py`
- `agent/tests/test_hancom_discovery.py`
- `agent/tests/test_hancom_dll_resolver.py`
- `agent/tests/test_hancom_hwp_com_smoke.py`
- `agent/tests/test_hancom_hwp_path_policy.py`
- `agent/tests/test_hancom_hwp_security_module.py`
- `agent/tests/test_hancom_hwp_security_module_detailed.py`
- `agent/tests/test_hancom_hwp_workflows.py`
- `agent/tests/test_hancom_hwpx_package_validator.py`
- `agent/tests/test_hwp_com_connector_unit.py`
- `agent/tests/test_import_smoke.py`
- `agent/tests/test_inspect_after_login.py`
- `agent/tests/test_local_agent_client.py`
- `agent/tests/test_local_agent_contract.py`
- `agent/tests/test_local_agent_running_and_safe_actions.py`
- `agent/tests/test_local_agent_server_router_gate.py`
- `agent/tests/test_local_agent_unit.py`
- `agent/tests/test_local_agent_ws_lifecycle.py`
- `agent/tests/test_local_agent_ws_runner.py`
- `agent/tests/test_local_agent_ws_smoke.py`
- `agent/tests/test_local_file_map.py`
- `agent/tests/test_local_file_map_cleanup_planner.py`
- `agent/tests/test_local_file_map_folder_summarizer.py`
- `agent/tests/test_local_file_map_report_privacy.py`
- `agent/tests/test_local_inventory_app_map.py`
- `agent/tests/test_local_inventory_smoke.py`
- `agent/tests/test_local_software_docker_download.py`
- `agent/tests/test_local_software_install_docker.py`
- `agent/tests/test_local_software_install_executor.py`
- `agent/tests/test_local_software_install_plan.py`
- `agent/tests/test_local_software_integrated_download_install.py`
- `agent/tests/test_local_software_manager.py`
- `agent/tests/test_local_software_vscode_fix.py`
- `agent/tests/test_local_software_windows_prereq.py`
- `agent/tests/test_login_with_secret.py`
- `agent/tests/test_result_spool_unit.py`
- `agent/tests/test_secret_store.py`
- `agent/tests/test_setup_hancom_security_module.py`
- `agent/tests/test_task_executor_com_policy_flow.py`
- `agent/tests/test_task_executor_unit.py`

</details>

<details><summary><code>scripts/ops</code> — 67개</summary>

- `scripts/ops/audit_5050_phase1e_adapter_implementation_plan.py`
- `scripts/ops/audit_5050_phase1f_adapter_skeleton_only.py`
- `scripts/ops/audit_5050_phase1g_adapter_unit_implementation.py`
- `scripts/ops/audit_5050_phase1h_route_wrapper_candidate_feature_flag_off.py`
- `scripts/ops/audit_5050_phase1i_staging_dry_run_internal_smoke.py`
- `scripts/ops/audit_5050_phase1j2_same_contract_response_schema_freeze.py`
- `scripts/ops/audit_5050_phase1j3_caller_migration_plan.py`
- `scripts/ops/audit_5050_phase1j4_caller_migration_dry_run.py`
- `scripts/ops/audit_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan.py`
- `scripts/ops/audit_5050_phase1j6_get_inbox_disable_readiness_review.py`
- `scripts/ops/audit_5050_phase1j7_get_inbox_disable_plan_approval_gate.py`
- `scripts/ops/audit_5050_phase1j8_get_inbox_disable_execution_after_approval.py`
- `scripts/ops/audit_5050_phase1j_same_contract_disable_candidate_review.py`
- `scripts/ops/audit_5050_phase1k_wrapper_route_integration_preflight.py`
- `scripts/ops/audit_5050_phase1l_feature_flag_off_route_integration_skeleton.py`
- `scripts/ops/audit_5050_phase1m_route_integration_skeleton_internal_smoke.py`
- `scripts/ops/audit_5050_phase1n_route_integration_final_preflight.py`
- `scripts/ops/audit_5050_phase1o_router_touch_design_only.py`
- `scripts/ops/audit_5050_phase1p_router_integration_implementation_plan.py`
- `scripts/ops/audit_5050_phase1q_closeout_router_touch_scope_pin.py`
- `scripts/ops/audit_5050_phase1q_router_touch_approval_gate.py`
- `scripts/ops/audit_5050_phase1r_actual_router_touch_feature_flag_off.py`
- `scripts/ops/audit_5050_phase1s_disabled_router_guard_behavior.py`
- `scripts/ops/audit_5050_phase1t_disabled_guard_expanded_smoke.py`
- `scripts/ops/audit_app_approval_gate_readonly_polish.py`
- `scripts/ops/audit_app_deployment_readonly_polish.py`
- `scripts/ops/audit_app_external_sites_readonly_polish.py`
- `scripts/ops/audit_app_logs_audit_readonly_view.py`
- `scripts/ops/audit_app_nav_active_state_polish.py`
- `scripts/ops/audit_app_storage_readonly_polish.py`
- `scripts/ops/audit_app_task_detail_readonly_polish.py`
- `scripts/ops/audit_backend_operation_stabilization_final.py`
- `scripts/ops/audit_backend_pre_deploy_smoke_plan.py`
- `scripts/ops/audit_desktop_agent_common_spec.py`
- `scripts/ops/audit_desktop_agentrun_smoke_blocker.py`
- `scripts/ops/audit_desktop_app_design.py`
- `scripts/ops/audit_desktop_app_watchdog.py`
- `scripts/ops/audit_desktop_ui_browser_screenshot_wiring.py`
- `scripts/ops/audit_desktop_webview_browser_cdp_package_smoke.py`
- `scripts/ops/audit_desktop_webview_local_e2e_smoke.py`
- `scripts/ops/audit_desktop_webview_pyinstaller_package.py`
- `scripts/ops/audit_desktop_webview_release_install.py`
- `scripts/ops/audit_haehan_admin_mode_webview_lazy_load.py`
- `scripts/ops/audit_haehan_consent_dialog.py`
- `scripts/ops/audit_haehan_desktop_install_shortcut.py`
- `scripts/ops/audit_haehan_desktop_release_baseline.py`
- `scripts/ops/audit_haehan_desktop_user_run_baseline.py`
- `scripts/ops/audit_haehan_legacy_entrypoint_guard.py`
- `scripts/ops/audit_haehan_single_exe_build.py`
- `scripts/ops/audit_haehan_single_exe_launcher_foundation.py`
- `scripts/ops/audit_haehan_stash_safe_restore.py`
- `scripts/ops/audit_haehan_tray_registration_merge.py`
- `scripts/ops/audit_haehan_whoami_route.py`
- `scripts/ops/audit_local_agent_exception_handler_p2.py`
- `scripts/ops/audit_local_agent_ip_allowlist_relax_deploy.py`
- `scripts/ops/audit_local_agent_preflight_p1.py`
- `scripts/ops/audit_local_agent_provider_error_p3.py`
- `scripts/ops/audit_local_desktop_agent_live_connection.py`
- `scripts/ops/audit_public_local_agent_ws_from_user_ip.py`
- `scripts/ops/audit_trusted_session_user_approval_policy.py`
- `scripts/ops/live_check_login_flow_20260520.py`
- `scripts/ops/setup_github_webhook.py`
- `scripts/ops/smoke_5050_phase1i_staging_dry_run_internal.py`
- `scripts/ops/smoke_5050_phase1j4_caller_migration_dry_run.py`
- `scripts/ops/smoke_5050_phase1m_route_integration_skeleton_internal.py`
- `scripts/ops/smoke_5050_phase1s_disabled_router_guard_behavior.py`
- `scripts/ops/smoke_app_ui_readonly_backend_status_cards.py`

</details>

<details><summary><code>tests</code> — 62개</summary>

- `tests/test_5050_phase1e_adapter_implementation_plan_20260517.py`
- `tests/test_5050_phase1f_adapter_skeleton_only_20260517.py`
- `tests/test_5050_phase1g_adapter_unit_implementation_20260517.py`
- `tests/test_5050_phase1h_route_wrapper_candidate_feature_flag_off_20260517.py`
- `tests/test_5050_phase1i_staging_dry_run_internal_smoke_20260517.py`
- `tests/test_5050_phase1j2_same_contract_response_schema_freeze_20260517.py`
- `tests/test_5050_phase1j3_caller_migration_plan_20260517.py`
- `tests/test_5050_phase1j4_caller_migration_dry_run_20260517.py`
- `tests/test_5050_phase1j5_get_inbox_caller_confirmation_and_migration_plan_20260517.py`
- `tests/test_5050_phase1j6_get_inbox_disable_readiness_review_20260517.py`
- `tests/test_5050_phase1j7_get_inbox_disable_plan_approval_gate_20260517.py`
- `tests/test_5050_phase1j8_get_inbox_disable_execution_after_approval_20260517.py`
- `tests/test_5050_phase1j_same_contract_disable_candidate_review_20260517.py`
- `tests/test_5050_phase1k_wrapper_route_integration_preflight_20260517.py`
- `tests/test_5050_phase1l_feature_flag_off_route_integration_skeleton_20260517.py`
- `tests/test_5050_phase1m_route_integration_skeleton_internal_smoke_20260517.py`
- `tests/test_5050_phase1n_route_integration_final_preflight_20260517.py`
- `tests/test_5050_phase1o_router_touch_design_only_20260517.py`
- `tests/test_5050_phase1p_router_integration_implementation_plan_20260517.py`
- `tests/test_5050_phase1q_closeout_router_touch_scope_pin_20260517.py`
- `tests/test_5050_phase1q_router_touch_approval_gate_20260517.py`
- `tests/test_5050_phase1r_actual_router_touch_feature_flag_off_20260517.py`
- `tests/test_5050_phase1s_disabled_router_guard_behavior_20260517.py`
- `tests/test_5050_phase1t_disabled_guard_expanded_smoke_20260517.py`
- `tests/test_backend_operation_stabilization_final_20260517.py`
- `tests/test_backend_pre_deploy_smoke_plan_20260517.py`
- `tests/test_browser_open_click_close_controlled.py`
- `tests/test_build_discovery_candidates_script_20260509.py`
- `tests/test_build_smoke_plan_script_20260509.py`
- `tests/test_cross_app_api_approval_boundary.py`
- `tests/test_desktop_common_spec_preflight.py`
- `tests/test_desktop_legacy_ui_removal.py`
- `tests/test_desktop_local_agent_daemon.py`
- `tests/test_desktop_local_runner.py`
- `tests/test_desktop_new_shell_phase1.py`
- `tests/test_desktop_new_shell_phase2_ui_smoke.py`
- `tests/test_desktop_status_provider.py`
- `tests/test_desktop_task_receiver_20260516.py`
- `tests/test_desktop_ui_browser_screenshot_wiring.py`
- `tests/test_desktop_webview_browser_cdp_package_smoke.py`
- `tests/test_desktop_webview_release_install.py`
- `tests/test_file_map_executor_service.py`
- `tests/test_haehan_admin_mode_webview_lazy_load.py`
- `tests/test_haehan_consent_dialog.py`
- `tests/test_haehan_desktop_install_shortcut.py`
- `tests/test_haehan_legacy_entrypoint_guard.py`
- `tests/test_haehan_single_exe_build_entrypoint.py`
- `tests/test_haehan_single_exe_launcher_foundation.py`
- `tests/test_haehan_tray_registration_merge.py`
- `tests/test_haehan_whoami_route.py`
- `tests/test_probe_local_agent_ws_readonly.py`
- `tests/test_run_allowlist_preflight_script_20260509.py`
- `tests/test_run_smoke_dryrun_script_20260509.py`
- `tests/test_ui_residue_audit.py`
- `tests/test_ui_residue_cleanup.py`
- `tests/test_user_browser_action_gate_20260509.py`
- `tests/test_user_browser_actions_20260509.py`
- `tests/test_user_browser_audit_log_20260509.py`
- `tests/test_user_browser_cdp_20260509.py`
- `tests/test_user_browser_intent_token_20260509.py`
- `tests/test_user_browser_secure_login_20260509.py`
- `tests/test_user_browser_session_20260509.py`

</details>

<details><summary><code>agent/excel</code> — 53개</summary>

- `agent/excel/__init__.py`
- `agent/excel/analysis_workflows.py`
- `agent/excel/approval_policy.py`
- `agent/excel/backup_manager.py`
- `agent/excel/batch_executor.py`
- `agent/excel/cell_writer.py`
- `agent/excel/change_log.py`
- `agent/excel/change_planner.py`
- `agent/excel/change_tracker.py`
- `agent/excel/column_writer.py`
- `agent/excel/copy_saver.py`
- `agent/excel/data_validator.py`
- `agent/excel/diff_reporter.py`
- `agent/excel/execution_workflows.py`
- `agent/excel/formula_scanner.py`
- `agent/excel/formula_validator.py`
- `agent/excel/formula_writer.py`
- `agent/excel/header_detector.py`
- `agent/excel/hidden_filter_detector.py`
- `agent/excel/integrations/__init__.py`
- `agent/excel/integrations/bid_analysis_adapter.py`
- `agent/excel/integrations/material_db_adapter.py`
- `agent/excel/merged_cell_detector.py`
- `agent/excel/operation_executor.py`
- `agent/excel/operation_normalizer.py`
- `agent/excel/operation_schema.py`
- `agent/excel/original_save_policy.py`
- `agent/excel/packs/__init__.py`
- `agent/excel/packs/construction_estimate.py`
- `agent/excel/packs/estimate_workflows.py`
- `agent/excel/packs/material_price_check.py`
- `agent/excel/packs/price_check_workflows.py`
- `agent/excel/packs/settlement_review.py`
- `agent/excel/packs/settlement_workflows.py`
- `agent/excel/pdf_exporter.py`
- `agent/excel/pdf_workflows.py`
- `agent/excel/planning_workflows.py`
- `agent/excel/print_area_manager.py`
- `agent/excel/report_table_builder.py`
- `agent/excel/report_workflows.py`
- `agent/excel/reporter.py`
- `agent/excel/row_finder.py`
- `agent/excel/row_writer.py`
- `agent/excel/structure_analyzer.py`
- `agent/excel/style_copier.py`
- `agent/excel/summary_sheet_writer.py`
- `agent/excel/table_analyzer.py`
- `agent/excel/table_region_detector.py`
- `agent/excel/total_validator.py`
- `agent/excel/type_validator.py`
- `agent/excel/validation_workflows.py`
- `agent/excel/validator.py`
- `agent/excel/workflows.py`

</details>

<details><summary><code>agent/local_inventory</code> — 43개</summary>

- `agent/local_inventory/__init__.py`
- `agent/local_inventory/app_detector.py`
- `agent/local_inventory/app_map/__init__.py`
- `agent/local_inventory/app_map/app_map_builder.py`
- `agent/local_inventory/app_map/capability_mapper.py`
- `agent/local_inventory/app_map/file_association_scanner.py`
- `agent/local_inventory/app_map/portable_app_detector.py`
- `agent/local_inventory/app_map/shortcut_scanner.py`
- `agent/local_inventory/app_map/software_catalog.py`
- `agent/local_inventory/change_watcher.py`
- `agent/local_inventory/com_scanner.py`
- `agent/local_inventory/consent_policy.py`
- `agent/local_inventory/diagnostics.py`
- `agent/local_inventory/dll_mapper.py`
- `agent/local_inventory/file_map/__init__.py`
- `agent/local_inventory/file_map/classifier.py`
- `agent/local_inventory/file_map/cleanup_audit.py`
- `agent/local_inventory/file_map/cleanup_executor.py`
- `agent/local_inventory/file_map/cleanup_executor_api.py`
- `agent/local_inventory/file_map/cleanup_paths.py`
- `agent/local_inventory/file_map/cleanup_planner.py`
- `agent/local_inventory/file_map/cleanup_policy.py`
- `agent/local_inventory/file_map/cleanup_preflight.py`
- `agent/local_inventory/file_map/cleanup_report_generator.py`
- `agent/local_inventory/file_map/cleanup_rollback.py`
- `agent/local_inventory/file_map/duplicate_detector.py`
- `agent/local_inventory/file_map/folder_summarizer.py`
- `agent/local_inventory/file_map/markdown_renderer.py`
- `agent/local_inventory/file_map/models.py`
- `agent/local_inventory/file_map/privacy.py`
- `agent/local_inventory/file_map/report_builder.py`
- `agent/local_inventory/file_map/scanner.py`
- `agent/local_inventory/file_map/storage.py`
- `agent/local_inventory/filesystem_scanner.py`
- `agent/local_inventory/inventory.py`
- `agent/local_inventory/inventory_store.py`
- `agent/local_inventory/metadata.py`
- `agent/local_inventory/policy.py`
- `agent/local_inventory/privacy_filter.py`
- `agent/local_inventory/registry_scanner.py`
- `agent/local_inventory/scan_level.py`
- `agent/local_inventory/scan_scope.py`
- `agent/local_inventory/scanner.py`

</details>

<details><summary><code>desktop</code> — 26개</summary>

- `desktop/DESIGN.md`
- `desktop/LEGACY_UI_DEPRECATED.md`
- `desktop/WEB_DESIGN.md`
- `desktop/__init__.py`
- `desktop/_broadcast.py`
- `desktop/admin_webview.py`
- `desktop/agent_runtime_boundary.py`
- `desktop/app_config.py`
- `desktop/audit_desktop.py`
- `desktop/blog_cafe_actions.py`
- `desktop/browser_routes.py`
- `desktop/browser_runtime_boundary.py`
- `desktop/consent.py`
- `desktop/local_agent_daemon.py`
- `desktop/local_agent_service.py`
- `desktop/local_runner.py`
- `desktop/local_server.py`
- `desktop/login_watcher.py`
- `desktop/main_launcher.py`
- `desktop/remote_access.py`
- `desktop/status_provider.py`
- `desktop/task_receiver.py`
- `desktop/tray_runtime.py`
- `desktop/user_settings.py`
- `desktop/ws_server.py`
- `desktop/ws_ui.py`

</details>

<details><summary><code>ai_orchestrator/local_agent</code> — 20개</summary>

- `scripts/browser/agent/site_map_store.py`
- `ai_orchestrator/local_agent/official_alternative_route_finder.py`
- `ai_orchestrator/local_agent/scenarios/__init__.py`
- `ai_orchestrator/local_agent/scenarios/cafe_to_blog.py`
- `ai_orchestrator/local_agent/scenarios/content_research_to_blog.py`
- `ai_orchestrator/local_agent/scenarios/document_download.py`
- `ai_orchestrator/local_agent/scenarios/financial_readonly.py`
- `ai_orchestrator/local_agent/scenarios/form_submit_with_permission.py`
- `ai_orchestrator/local_agent/scenarios/government_readonly.py`
- `ai_orchestrator/local_agent/scenarios/message_send_with_permission.py`
- `ai_orchestrator/local_agent/security_program_trust_list.py`
- `ai_orchestrator/local_agent/security_program_user_install_result_sanitizer.py`
- `ai_orchestrator/local_agent/security_route_policy.py`
- `ai_orchestrator/local_agent/user_browser_action_gate.py`
- `ai_orchestrator/local_agent/user_browser_actions.py`
- `ai_orchestrator/local_agent/user_browser_audit_log.py`
- `ai_orchestrator/local_agent/user_browser_cdp.py`
- `ai_orchestrator/local_agent/user_browser_intent_token.py`
- `ai_orchestrator/local_agent/user_browser_secure_login.py`
- `ai_orchestrator/local_agent/user_browser_session.py`

</details>

<details><summary><code>agent/hancom</code> — 15개</summary>

- `agent/hancom/__init__.py`
- `agent/hancom/discovery/__init__.py`
- `agent/hancom/discovery/com.py`
- `agent/hancom/discovery/diagnostics.py`
- `agent/hancom/discovery/dll_resolver.py`
- `agent/hancom/discovery/installation.py`
- `agent/hancom/discovery/registry.py`
- `agent/hancom/hwp/__init__.py`
- `agent/hancom/hwp/automation_connector.py`
- `agent/hancom/hwp/converter.py`
- `agent/hancom/hwp/path_policy.py`
- `agent/hancom/hwp/security_module.py`
- `agent/hancom/hwp/workflows.py`
- `agent/hancom/hwpx/__init__.py`
- `agent/hancom/hwpx/package_validator.py`

</details>

<details><summary><code>agent/local_software_manager</code> — 15개</summary>

- `agent/local_software_manager/__init__.py`
- `agent/local_software_manager/catalog.py`
- `agent/local_software_manager/detector.py`
- `agent/local_software_manager/docker_download.py`
- `agent/local_software_manager/docker_installer.py`
- `agent/local_software_manager/download_provider.py`
- `agent/local_software_manager/install_executor.py`
- `agent/local_software_manager/install_plan.py`
- `agent/local_software_manager/install_sources.py`
- `agent/local_software_manager/install_validator.py`
- `agent/local_software_manager/installer_verifier.py`
- `agent/local_software_manager/models.py`
- `agent/local_software_manager/post_install_verifier.py`
- `agent/local_software_manager/report_builder.py`
- `agent/local_software_manager/windows_feature_executor.py`

</details>

<details><summary><code>scripts</code> — 15개</summary>

- `scripts/audit_naver_search_status.py`
- `scripts/build_desktop_webview_app_windows.py`
- `scripts/build_discovery_candidates_from_fixture.py`
- `scripts/build_readonly_smoke_plan.py`
- `scripts/cdp_event_monitor.py`
- `scripts/chrome_ui_watcher.py`
- `scripts/eum_business_dashboard.py`
- `scripts/eum_task_runner.py`
- `scripts/probe_local_agent_ws_readonly.py`
- `scripts/run_allowlist_preflight.py`
- `scripts/run_readonly_smoke_dryrun.py`
- `scripts/setup_hancom_security_module.py`
- `scripts/status_reporter.py`
- `scripts/ui_residue_audit.py`
- `scripts/ui_residue_cleanup.py`

</details>

<details><summary><code>scripts/naver_mail</code> — 15개</summary>

- `scripts/naver_mail/__init__.py`
- `scripts/naver_mail/action_item_dashboard.py`
- `scripts/naver_mail/batch_runner.py`
- `scripts/naver_mail/body_pipeline_v2.py`
- `scripts/naver_mail/business_report.py`
- `scripts/naver_mail/folder_discovery.py`
- `scripts/naver_mail/folder_policy.py`
- `scripts/naver_mail/folder_profile.py`
- `scripts/naver_mail/inbox_collector.py`
- `scripts/naver_mail/pii_mask.py`
- `scripts/naver_mail/read_state_guard.py`
- `scripts/naver_mail/smart_folder_collector.py`
- `scripts/naver_mail/time_parser.py`
- `scripts/naver_mail/unknown_classification_rules.py`
- `scripts/naver_mail/unread_audit.py`

</details>

<details><summary><code>backend/compat</code> — 14개</summary>

- `backend/compat/__init__.py`
- `backend/compat/legacy_5050/__init__.py`
- `backend/compat/legacy_5050/adapters/__init__.py`
- `backend/compat/legacy_5050/adapters/common.py`
- `backend/compat/legacy_5050/adapters/inbox_email_fetch_adapter.py`
- `backend/compat/legacy_5050/adapters/task_approval_adapter.py`
- `backend/compat/legacy_5050/route_integration/__init__.py`
- `backend/compat/legacy_5050/route_integration/common.py`
- `backend/compat/legacy_5050/route_integration/inbox_email_fetch_route_skeleton.py`
- `backend/compat/legacy_5050/route_integration/task_approval_route_skeleton.py`
- `backend/compat/legacy_5050/wrappers/__init__.py`
- `backend/compat/legacy_5050/wrappers/common.py`
- `backend/compat/legacy_5050/wrappers/inbox_email_fetch_wrapper_candidate.py`
- `backend/compat/legacy_5050/wrappers/task_approval_wrapper_candidate.py`

</details>

<details><summary><code>scripts/naver</code> — 14개</summary>

- `scripts/naver/blog/community/targeted_engage.py`
- `scripts/naver/cafe/collection/excel_report.py`
- `scripts/naver/mail_write.py`
- `scripts/naver/smartstore/diagnose.py`
- `scripts/naver/smartstore/find_register_url.py`
- `scripts/naver/smartstore/find_v2.py`
- `scripts/naver/smartstore/general_analyzer.py`
- `scripts/naver/smartstore/general_full_analyze.py`
- `scripts/naver/smartstore/models.py`
- `scripts/naver/smartstore/product_analyzer.py`
- `scripts/naver/smartstore/router.py`
- `scripts/naver/smartstore/sidebar_expand.py`
- `scripts/naver/smartstore/sidebar_v3.py`
- `scripts/naver/smartstore/sitemap.py`

</details>

<details><summary><code>agent</code> — 13개</summary>

- `agent/api_client.py`
- `agent/app.py`
- `agent/approval_policy.py`
- `agent/config.py`
- `agent/errors.py`
- `agent/file_policy.py`
- `agent/local_agent.py`
- `agent/local_agent_client.py`
- `agent/local_agent_ws_runner.py`
- `agent/policy.py`
- `agent/result_spool.py`
- `agent/runner.py`
- `agent/task_executor.py`

</details>

<details><summary><code>scripts/file-map</code> — 10개</summary>

- `scripts/file-map/audit_component_lines.py`
- `scripts/file-map/audit_modularization.py`
- `scripts/file-map/audit_security_static.py`
- `scripts/file-map/generate_file_map_ops_report.py`
- `scripts/file-map/generate_file_map_status_report.py`
- `scripts/file-map/ops_monitoring_snapshot.py`
- `scripts/file-map/run_executor_service_2c_smoke_test.sh`
- `scripts/file-map/smoke_cleanup_execute_api_dry_run.py`
- `scripts/file-map/smoke_cleanup_execute_dry_run.py`
- `scripts/file-map/verify_audit_rollback.py`

</details>

<details><summary><code>scripts/local_agent</code> — 8개</summary>

- `scripts/local_agent/g2b/__init__.py`
- `scripts/local_agent/naver/cafe_attachments.py`
- `scripts/local_agent/naver/cafe_explore.py`
- `scripts/local_agent/naver/cafe_explorer.py`
- `scripts/local_agent/naver/cafe_list.py`
- `scripts/local_agent/naver/cafe_scraper.py`
- `scripts/local_agent/open_user_browser_session.py`
- `scripts/local_agent/run_universal_ai_site_agent_smoke.py`

</details>

<details><summary><code>mcp_server</code> — 6개</summary>

- `mcp_server/__init__.py`
- `mcp_server/config.py`
- `mcp_server/requirements.txt`
- `mcp_server/server.py`
- `mcp_server/upstream.py`
- `mcp_server/write_guard.py`

</details>

<details><summary><code>scripts/archive</code> — 6개</summary>

- `scripts/archive/explore/__init__.py`
- `scripts/archive/misc/discover_onedrive_roots.py`
- `scripts/archive/one_off/validate_discovery_candidates.py`
- `scripts/archive/poc/__init__.py`
- `scripts/archive/poc/excel_com_poc.py`
- `scripts/archive/poc/hwp_com_poc.py`

</details>

<details><summary><code>desktop/ui_dist</code> — 5개</summary>

- `desktop/ui_dist/assets/index-BQrtlMbv.css`
- `desktop/ui_dist/assets/index-BSD2fCeD.js`
- `desktop/ui_dist/favicon.svg`
- `desktop/ui_dist/icons.svg`
- `desktop/ui_dist/index.html`

</details>

<details><summary><code>services/file_map_executor</code> — 5개</summary>

- `services/file_map_executor/__init__.py`
- `services/file_map_executor/app.py`
- `services/file_map_executor/schemas.py`
- `services/file_map_executor/security.py`
- `services/file_map_executor/service.py`

</details>

<details><summary><code>agent/connectors</code> — 4개</summary>

- `agent/connectors/__init__.py`
- `agent/connectors/excel_com_connector.py`
- `agent/connectors/excel_connector.py`
- `agent/connectors/hwp_com_connector.py`

</details>

<details><summary><code>desktop/routes</code> — 4개</summary>

- `desktop/routes/__init__.py`
- `desktop/routes/agent.py`
- `desktop/routes/proxy.py`
- `desktop/routes/system.py`

</details>

<details><summary><code>desktop/ui_new</code> — 4개</summary>

- `desktop/ui_new/__init__.py`
- `desktop/ui_new/api.py`
- `desktop/ui_new/dashboard.py`
- `desktop/ui_new/shell_html.py`

</details>

<details><summary><code>scripts/community</code> — 3개</summary>

- `scripts/community/keyword_classifier.py`
- `scripts/community/sites/mlbpark.py`
- `scripts/community/sites/naver_cafe_new.py`

</details>

<details><summary><code>scripts/smartstore</code> — 3개</summary>

- `scripts/smartstore/__init__.py`
- `scripts/smartstore/actions.py`
- `scripts/smartstore/router.py`

</details>

<details><summary><code>(root)</code> — 2개</summary>

- `HaehanAI-Agent.spec`
- `HaehanAI-Desktop.spec`

</details>

<details><summary><code>ai_orchestrator/tests</code> — 2개</summary>

- `ai_orchestrator/tests/test_cad_mcp_split.py`
- `ai_orchestrator/tests/test_cad_proxy.py`

</details>

<details><summary><code>mcp_server/tests</code> — 2개</summary>

- `mcp_server/tests/__init__.py`
- `mcp_server/tests/test_write_guard.py`

</details>

<details><summary><code>scripts/form</code> — 2개</summary>

- `scripts/form/auto_resolver.py`
- `scripts/form/state_scanner.py`

</details>

<details><summary><code>scripts/haehan</code> — 2개</summary>

- `scripts/haehan/__init__.py`
- `scripts/haehan/create_desktop_shortcut.py`

</details>

<details><summary><code>admin-web/scripts</code> — 1개</summary>

- `admin-web/scripts/smoke_browser.py`

</details>

<details><summary><code>agent/docs</code> — 1개</summary>

- `agent/docs/reports/local_software_docker_install_run_4b_bridged_elevation.md`

</details>

<details><summary><code>ai_orchestrator</code> — 1개</summary>

- `ai_orchestrator/agent_ai_legacy_routing.py`

</details>

<details><summary><code>ai_orchestrator/connectors</code> — 1개</summary>

- `ai_orchestrator/connectors/eum_notice_scheduler.py`

</details>

<details><summary><code>ai_orchestrator/external_sites</code> — 1개</summary>

- `ai_orchestrator/external_sites/automation_capability_registry.py`

</details>

<details><summary><code>docker</code> — 1개</summary>

- `docker/file-map-executor.Dockerfile`

</details>

<details><summary><code>notice_radar</code> — 1개</summary>

- `notice_radar/runner.py`

</details>

<details><summary><code>scripts/eum</code> — 1개</summary>

- `scripts/eum/auto_fix_a4.py`

</details>

<details><summary><code>scripts/local</code> — 1개</summary>

- `scripts/local/__init__.py`

</details>

<details><summary><code>scripts/mk_catalog</code> — 1개</summary>

- `scripts/mk_catalog/line_light_detail_page.py`

</details>

<details><summary><code>scripts/youtube</code> — 1개</summary>

- `scripts/youtube/channel_analysis.py`

</details>

<details><summary><code>scripts/yt_upload</code> — 1개</summary>

- `scripts/yt_upload/__init__.py`

</details>

---

# 2026-09-24 추가 — OpenAI(GPT) 호출 코드 완전 삭제

기준서: `docs/specs/2026-09-24_openai_removal_claude_mcp.md`. 정리 직전 태그: `pre-openai-removal`.
사유: 앱 런타임 유료 AI API 호출 0, AI(판단·글쓰기·에이전트)는 Claude Code가 MCP(`ai_orchestrator/server/mcp_server.py`)로 앱에 붙어 수행.

## 복원 방법

```bash
git checkout pre-openai-removal -- <경로>
```

## 삭제 파일 (33개, `git show --stat 86b1c867`/`58dc0903` 실측 재확인 — 58dc0903은 편집만, 삭제 0개)

<details><summary>채팅 API·자율 에이전트 — 7개</summary>

- `ai_orchestrator/routers/agent_ai_proxy_router.py` — /agent-ai/chat·health·task 라우터
- `ai_orchestrator/openai_proxy_caller.py` — call_openai_chat/call_openai_agent
- `ai_orchestrator/gpt_planner.py`
- `ai_orchestrator/connectors/browser_agent_router.py` — /browser-agent/run
- `scripts/browser_agent/agent.py` — GPT 단계결정 CDP 에이전트(_decide)
- `scripts/browser_agent/free_agent.py` — GPT 자율 도구호출 에이전트
- `scripts/browser_agent/__init__.py`

</details>

<details><summary>도메인 GPT 채팅 루프·전용 작성기 — 3개</summary>

- `ai_orchestrator/connectors/gabia/chat.py` — /gabia/chat (전체 GPT 전용, 나머지 gabia 엔드포인트는 gabia_router.py에 그대로 있음)
- `scripts/naver/smartstore/product/gpt_description_writer.py` — GptDescriptionWriter(GPT-4o 상세설명·비전)
- `scripts/cdp_cli.py` — 독립 OpenAI 자연어 CDP REPL(미사용 경로)

(naver_blog_router.py·naver_cafe_router.py·smartstore/chat.py의 GPT 채팅 섹션은 파일 자체는
유지하되 해당 함수·엔드포인트만 삭제 — 아래 "편집" 참고)

</details>

<details><summary>local_agent 데스크톱 OpenAI 채팅·키 저장 — 6개</summary>

- `local_agent/ai_chat_adapter.py`
- `local_agent/ai_chat_client.py`
- `local_agent/ai_chat_models.py`
- `local_agent/openai_chat_client.py`
- `local_agent/openai_key_store.py`
- `local_agent/server_proxy_chat_client.py`

</details>

<details><summary>테스트·감사 스크립트(삭제 코드 전용) — 17개</summary>

- `tests/test_openai_server_proxy_client.py`
- `tests/test_openai_direct_test_call.py`
- `tests/test_openai_dev_key_store.py`
- `tests/test_local_agent_desktop_ui_openai_key_ux_spec.py`
- `tests/test_deploy_openai_proxy_to_prod.py`
- `tests/test_agent_ai_chat_api_client.py`
- `tests/test_chat_gpt_conversion.py`
- `tests/test_app_features_gpt.py`
- `tests/test_free_agent_web_search.py`
- `ai_orchestrator/tests/test_openai_client.py`
- `ai_orchestrator/tests/test_gpt_planner.py`
- `scripts/ops/audit_openai_server_proxy_client.py`
- `scripts/ops/audit_openai_direct_test_call.py`
- `scripts/ops/audit_openai_dev_key_store.py`
- `scripts/ops/audit_local_agent_desktop_ui_openai_key_ux_spec.py`
- `scripts/ops/audit_deploy_openai_proxy_to_prod.py`
- `scripts/ops/audit_agent_ai_chat_api_client.py`

</details>

## 주요 편집(삭제하지 않고 GPT 분기만 제거)

- `ai_orchestrator/router.py` — agent_ai_proxy_router·browser_agent_router import·include 제거
- `ai_orchestrator/connectors/naver_blog_router.py` — /chat(SSE GPT 루프)·/ai-generate GPT 본문 삭제(스텁 응답으로 대체)
- `ai_orchestrator/connectors/naver_cafe_router.py` — /chat(SSE GPT 루프)·_run_cafe_tool·_cafe_tool_defs 삭제, /ai-analyze·/cafe-to-haehan-blog(비AI)는 보존
- `ai_orchestrator/connectors/smartstore/chat.py` — 전체 재작성, /images/upload만 유지
- `ai_orchestrator/connectors/smartstore/description.py` — /description/ai-generate·/gpt-generate GPT 호출 제거(스텁 응답)
- `ai_orchestrator/connectors/gabia_router.py` — gabia/chat.py include 제거
- `ai_orchestrator/server/mcp_server.py` — generate_description 도구에서 model=gpt 제거, builder 전용화
- `ai_orchestrator/openai_client.py` — OpenAI 호출 분기 제거, 항상 MOCK 폴백 반환
- `ai_orchestrator/app_llm.py` — APP_LLM_PROVIDER="none", APP_LLM_MODEL/QUALITY_MODEL 상수 제거
- `ai_orchestrator/config.py` — OPENAI_API_KEY 설정 제거
- `ai_orchestrator/routers/config_router.py` — 데스크톱 배포 env 목록에서 OPENAI_API_KEY 제거
- `scripts/naver/smartstore/product/review_reply.py` — GPT 답변생성 제거, 별점 기반 고정 템플릿
- `scripts/naver/automation/integration/ai_responder.py` — OpenAI 분기 제거, 기본 provider="none"(anthropic은 opt-in 유지)
- `scripts/ops/generate_desc_templates_lighting.py` — Claude/GPT writer 제거, 섹션 빌더만 사용
- `log_analyzer.py` — generate_ai_ops_summary의 OpenAI 호출 제거, 항상 mock 요약
- `verify_local_runtime_dry_run.py` — check_ai_proxy(삭제된 local_agent 모듈 참조) 제거
- `tests/test_app_llm_boundary.py` — GPT 모델 단정 제거, provider="none" 검증으로 교체
- `tests/test_tool_registry.py` — cafe/blog/smartstore/agent 도메인 등록 검증 제거(해당 register 호출이 삭제된 채팅 루프에 있었음), 포맷 변환 유틸 테스트만 유지
- `tests/test_naver_cdp_thread_safety.py` — 삭제된 gabia/chat.py 항목 제거

## 관련 커밋

- `d4a4421d` chore(cleanup): 최근 60일 사용 흔적 없는 직접 실행 스크립트 19개 삭제 [allow-delete]
- `0c097029` docs(defect_index): #11 해결 표시(e9042657)
- `9a2a59e0` docs(defect_index): 정리 루프 결과 반영 — #7~#10 해결, #27~#30 추가
- `290f178b` refactor(lint): 쓰지 않는 지역변수·중복 정의 제거 5회차 (F841 47·F811 2)
- `5973ebd2` chore(cleanup): 이름만 언급되던 미도달 파일 정리 4회차 [allow-delete]
- `48a4aa4b` chore(cleanup): 끊어진 호환 shim·CAD 잔재 정리 3회차 — pytest 수집 오류 7→1 [allow-delete]
- `20bec5cd` refactor(lint): 쓰지 않는 import 제거 2회차 — 기존 lint 오류 있던 파일 동작 보존 정리
- `c3025ed1` refactor(lint): 쓰지 않는 import 제거 1회차 — lint 기존오류 없는 374 파일
- `88272216` chore(cleanup): 타 앱 연결 2차 삭제 — mcp_server·desktop·backend/compat·agent 잔여 [allow-delete]
- `ad187595` ﻿chore(cleanup): AI 에이전트 외 타 앱 연결 코드 삭제 — Excel·한컴·PC파일정리·legacy UI·CAD 잔재 [allow-delete]
- `e9042657` fix(repo): import 되는 scripts/session_tracker.py 가 .gitignore session* 에 막혀 누락 (#11)
- `b7323bb7` docs(defect_index): 골격 점검·코드맵 S1 결함 목차 26건
- `43715ee2` chore(cleanup): 코드맵 S1 미도달 파일 22개 + scripts/smartstore shim 3개 삭제 [allow-delete]

### 2026-09-24 범위 확장 — Anthropic 유료 API 호출 경로 (사용자 승인)
- `ai_orchestrator/connectors/ai_reply_caller.py` — 복원: `git checkout pre-openai-removal -- ai_orchestrator/connectors/ai_reply_caller.py`
- (파일 유지·호출부만 제거) `scripts/naver/smartstore/product/ai_description_writer.py`, `scripts/naver/automation/integration/ai_responder.py`, `ai_orchestrator/connectors/kakao_skill_router.py` — 원본: `git show pre-openai-removal:<경로>`

## 2026-10-01 추가 정리 — 네이버 로그인 죽은 코드

호출자 0건(텍스트 검색으로 확인 — 문자열 지연 import 포함)이라 삭제. 복원은 이 정리 커밋의 **부모**에서 한다:
`git checkout <이 커밋>^ -- <경로>` (커밋 해시는 `git log -1 --grep="네이버 로그인 죽은 코드 삭제"` 로 확인).

- `scripts/naver/cafe.py` — 같은 이름의 `scripts/naver/cafe/` 패키지가 가려 import 불가(실제 import 가 패키지로 해석됨을 확인)
- `scripts/browser/agent/secure_login.py` (+ `browser/__init__.py` 의 재내보내기 26개) — 가져다 쓰는 곳도 테스트도 없음
- `scripts/naver/auth.py::_human_type` — deprecated, 호출자 없음
- `scripts/login_detector.py::wait_for_logout` — 호출자 없음(독스트링에만 이름)
- `scripts/credentials.py::list_naver_accounts` — 호출자 없음(세션 라우터 `list_accounts` 가 같은 일을 따로 구현)

삭제하지 않고 남긴 것: `scripts/ops/make_inspection_video.py`(검측 데모 영상 도구 — 네이버 로그인 씬이 존재하지 않는 `_ID_SELECTORS` 등을 import 해 실행하면 ImportError. 고칠지 지울지 사용자 결정 필요).

---

## 2026-10-01 추가 삭제 — 미사용 비공개 도우미 함수 17개

근거: 저장소 전체 텍스트(코드·설정·문서·스크립트)에서 정의 외 참조 0, vulture 미사용, 모듈 최상위 비공개(`_`) 함수. 삭제로 새로 미사용이 된 import 는 함께 제거. 후보 선정 과정과 보류 목록: `docs/dead_code_candidates_20261001.md`.
복원: `git show <삭제 커밋>^:<경로>` (삭제 직전 내용). 함수 단위 삭제라 파일 전체 복원은 `git checkout <삭제 커밋>^ -- <경로>` 로 한다.

- `local_agent/browser_websocket_handshake.py` — `_get_hostname_hash`
- `local_agent/kras_connector.py` — `_http_error_detail`
- `scripts/cdp_client.py` — `_load_daemon_state`
- `scripts/cdp_daemon.py` — `_clear_session_restore_artifacts`
- `scripts/eum/auth.py` — `_prepare_login_page`
- `scripts/eum/shared/layout_openpyxl.py` — `_pt_to_px`, `_make_border`
- `scripts/google/precision_report.py` — `_host_from_surface`
- `scripts/mk_catalog/detail_page_template.py` — `_rounded_photo`
- `scripts/module_quality_gate_checks_web.py` — `_npm_audit_command`
- `scripts/naver/blog/seo/assets.py` — `_click_next_blog_index`
- `scripts/naver/browser_gate.py` — `_norm_path`
- `scripts/ops/export_cafe_keywords_excel.py` — `_cell`
- `scripts/ops/windows_auth_popup_monitor.py` — `_get_foreground_title`
- `scripts/site_access.py` — `_find_or_open_tab`
- `scripts/video/ig_dm_bot_ep01_visuals.py` — `_diagram_card`
- `scripts/video/record_promo.py` — `_video_dir`

---

## 2026-10-01 추가 삭제(2차) — 미사용 공개 함수·클래스 22개

근거: 저장소 전체 텍스트(코드·설정·문서·스크립트)에서 정의 외 참조 0(삭제 직전 재확인), vulture 미사용. 사용자 승인("D만 삭제")을 받은 분류 D. 삭제로 미사용이 된 import(`time`, `asdict`, `close_all_pages`)는 함께 제거. 보류 분류는 `docs/dead_code_candidates_20261001.md`.
복원: `git show <삭제 커밋>^:<경로>` (삭제 직전 내용).

- `ai_orchestrator/connectors/instagram_dm_db.py` — `set_legacy_ig_user_id`
- `tools/gates/auth.py` — `get_tenant_context`(build_tenant_context 의 별칭)
- `local_agent/runtime/delegated_permission_store.py` — `get_store_snapshot`
- `core/agent_runtime/runtime/task_client.py` — `poll_loop`
- `ai_orchestrator/openai_client.py` — `generate_plan_explanation`(호출되지 않는 유료 AI 호출 경로)
- `ai_orchestrator/persistence/registration_code_store.py` — `reset_store_for_tests`
- `ai_orchestrator/router.py` — `TelegramWebhookBody`
- `core/agent_runtime/agent.py` — `poll_task`
- `local_agent/browser_controller.py` — `BrowserApprovalError`, `BrowserSensitiveFieldError`, `create_and_inspect`
- `scripts/browser_tab_monitor.py` — `ensure_single_tab`
- `scripts/instagram/kotara_ctc_reel.py` — `render_thumbnail`, `render_all_frames`, `strip_audio`, `extract_check_frames`
- `scripts/naver/mail/collection/folder_discovery.py` — `folders_to_dicts`
- `scripts/naver/smartstore/product/detail_collector.py` — `list_cached_product_ids`
- `tools/repo_gates/codebase_layer_audit.py` — `issue_key`
- `scripts/session_tracker.py` — `clear_state`, `all_states`
- `scripts/web_connector.py` — `shutdown_browser_session`(탭·브라우저 전체 종료 — 로그인 세션 보존 정책과 반대)

## 2026-10-08 추가 삭제 — tests-split(B12) 중 발견한 미사용 archive 스크립트

근거: `scripts/archive/one_off/validate_site_policy_config.py` — 저장소 전체(코드·설정·CI·활성 운영 문서)에서
정의 외 참조 0(삭제 직전 재확인: import 0, configs/registry 외 참조 0, scripts/ops 게이트·감사 스크립트
참조 0, CI 참조 0, 활성 문서 참조 0 — docs/reports·docs/specs 의 역사적 언급만 있음, data 참조 0). 자기
시험(`tests/test_validate_site_policy_config_20260509.py`)만 호출하고 있어 시험도 같이 지운다.
(참고: 같은 B12 조사에서 함께 archive 로 분류됐던 `scripts/archive/misc/chrome_ui_monitor.py` 는 실제로
`scripts/browser/cdp/cdp_daemon.py` 가 서브프로세스로 띄우고 재시작시키는 **살아있는 코드**로 확인돼
삭제하지 않았다 — stage/no-cdp-autostart(a2ad1162) 병합 후 재확인 예정.)
복원: `git show <삭제 커밋>^:<경로>` (삭제 직전 내용).

- `scripts/archive/one_off/validate_site_policy_config.py` — 사이트 정책 설정 검증 one-off 스크립트
- `tests/test_validate_site_policy_config_20260509.py` — 위 스크립트만 시험하던 파일
---

## 2026-10-08 추가 삭제(3차) — browser_tool submit 6파일 + gui_chat_state.py 전체 삭제

근거: 운영 import·호출 0(실제 submit 플로우는 ai_orchestrator/local_agent/actions/browser_submit_with_user_approval.py 등 별도 구현이 담당, 이 파일들을 import 안 함), 문자열 경로·workflow·spec·Electron·.mcp.json·훅·docs 실행 안내·PC 예약 작업 참조 0. model_adapters.py 의 "impl" 문자열 1건만 걸려있었고(정책 설명용, 실제 호출 아님) 실제 구현 경로로 수정함. 삭제마다 같은 모듈만 전용으로 검사하는 시험 파일도 함께 제거(다른 기능과 섞인 test_browser_action_registry_risk_mapping_20260506.py 는 보존). 삭제 전후 `pytest --collect-only` 12849→12522(차이 327 = 삭제된 시험 파일 몫), 영향 시험(test_browser_gate_module_design, test_browser_action_registry_risk_mapping, model_adapters 관련 3파일) 전부 통과 확인(HAEHAN_NO_BROWSER_LAUNCH=1, py -3.14).
복원: `git show <삭제 커밋>^:<경로>` (삭제 직전 내용).

소스 파일:
- `ai_orchestrator/browser_tool/controlled_submit.py`
- `ai_orchestrator/browser_tool/submit_policy.py`
- `ai_orchestrator/browser_tool/submit_preview.py`
- `ai_orchestrator/browser_tool/submit_execution_gate.py`
- `ai_orchestrator/browser_tool/submit_audit_log.py`
- `ai_orchestrator/browser_tool/submit_approval_state.py`
- `local_agent/gui_chat_state.py` — `ChatUiController`, `ChatUiMessage`, `AiModeState`, `ChatUiState`, `mode_label_kr`, `ai_status_label_kr`

전용 시험 파일(위 6개 소스만 검사):
- `tests/test_browser_submit_controlled_browser_smoke_20260506.py`
- `tests/test_browser_submit_controlled_internal_20260506.py`
- `tests/test_browser_submit_gate_controlled_integration_smoke_20260506.py`
- `tests/test_browser_submit_real_browser_audit_integration_20260506.py`
- `tests/test_browser_submit_real_browser_controlled_click_smoke_20260506.py`
- `tests/test_browser_submit_approval_state_persistence_20260506.py`
- `tests/test_browser_submit_audit_log_persistence_20260506.py`
- `tests/test_browser_submit_execution_gate_validator_20260506.py`
- `tests/test_browser_submit_execution_gate_schema_20260506.py`
- `tests/test_browser_submit_policy_validator_20260506.py`
- `tests/test_browser_submit_policy_design_20260506.py`
- `tests/test_browser_submit_preview_schema_20260506.py`

전용 fixture(위 시험 파일에서만 참조, 다른 곳 0):
- `tests/fixtures/browser_controlled_submit_form_20260506.html`
- `tests/fixtures/browser_submit_policy_allowlist_20260506.json`

보존(사용처 0 아님): `tests/fixtures/browser_submit_execution_gate_fixture_20260506.json` — 남아있는 `tests/test_browser_gate_module_design_20260506.py` 가 여전히 참조(파일 없으면 skip 처리되어 삭제해도 안 깨지지만, 다른 시험이 참조 중이라 보존).
- `scripts/web_connector.py` — `shutdown_browser_session`(탭·브라우저 전체 종료 — 로그인 세션 보존 정책과 반대)
