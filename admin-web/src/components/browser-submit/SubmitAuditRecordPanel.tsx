"use client";

import React from "react";
import { AuditPreviewRecord } from "./__fixtures__/submitApprovalPreview.fixture";

interface SubmitAuditRecordPanelProps {
  record: AuditPreviewRecord;
}

/**
 * SubmitAuditRecordPanel
 *
 * Layer 3: Admin/Auditor audit record
 * For compliance and audit trail purposes
 * Shows: event ID, redacted payload, timestamps, policy verdict
 * NEVER shows raw secrets/passwords/tokens
 */
export default function SubmitAuditRecordPanel({
  record,
}: SubmitAuditRecordPanelProps) {
  return (
    <div
      className="space-y-4 p-4 bg-slate-50 rounded-lg border border-slate-400"
      data-testid="submit-audit-record-panel"
    >
      <div className="flex items-center gap-2 pb-2 border-b border-slate-300">
        <span className="text-sm font-semibold text-slate-900">감사 레코드</span>
        <span className="text-xs bg-slate-200 text-slate-700 px-2 py-1 rounded">
          관리자용
        </span>
      </div>

      {/* Event ID */}
      <div>
        <p className="text-xs font-medium text-slate-600 uppercase">Event ID</p>
        <p
          className="text-xs text-slate-900 font-mono break-all"
          data-testid="audit-event-id"
        >
          {record.event_id}
        </p>
      </div>

      {/* Timestamps */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs font-medium text-slate-600 uppercase">생성일시</p>
          <p className="text-xs text-slate-900" data-testid="audit-created-at">
            {new Date(record.created_at).toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-slate-600 uppercase">Validation ID</p>
          <p className="text-xs text-slate-900 font-mono" data-testid="audit-validation-id">
            {record.validation_id}
          </p>
        </div>
      </div>

      {/* User & Tenant (if available) */}
      {(record.user_id || record.tenant_id) && (
        <div className="grid grid-cols-2 gap-4">
          {record.user_id && (
            <div>
              <p className="text-xs font-medium text-slate-600 uppercase">User ID</p>
              <p className="text-xs text-slate-900" data-testid="audit-user-id">
                {record.user_id}
              </p>
            </div>
          )}
          {record.tenant_id && (
            <div>
              <p className="text-xs font-medium text-slate-600 uppercase">Tenant ID</p>
              <p className="text-xs text-slate-900" data-testid="audit-tenant-id">
                {record.tenant_id}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Site & Form Details */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <p className="text-xs font-medium text-slate-600 uppercase">Site</p>
          <p className="text-xs text-slate-900" data-testid="audit-site-id">
            {record.site_id}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-slate-600 uppercase">Form</p>
          <p className="text-xs text-slate-900" data-testid="audit-form-id">
            {record.form_id}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-slate-600 uppercase">Button</p>
          <p className="text-xs text-slate-900" data-testid="audit-submit-button-id">
            {record.submit_button_id}
          </p>
        </div>
      </div>

      {/* Policy & User Confirmation */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <p className="text-xs font-medium text-slate-600 uppercase">정책</p>
          <p
            className={`text-xs font-semibold ${
              record.policy_verdict === "ALLOW"
                ? "text-green-700"
                : "text-red-700"
            }`}
            data-testid="audit-policy-verdict"
          >
            {record.policy_verdict}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-slate-600 uppercase">사용자 승인</p>
          <p
            className={`text-xs font-semibold ${
              record.user_confirmed ? "text-green-700" : "text-gray-700"
            }`}
            data-testid="audit-user-confirmed"
          >
            {record.user_confirmed ? "✓ Yes" : "○ No"}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-slate-600 uppercase">제출됨</p>
          <p
            className={`text-xs font-semibold ${
              record.submitted ? "text-green-700" : "text-gray-700"
            }`}
            data-testid="audit-submitted"
          >
            {record.submitted ? "✓ Yes" : "○ No"}
          </p>
        </div>
      </div>

      {/* Submit Result */}
      <div>
        <p className="text-xs font-medium text-slate-600 uppercase">제출 결과</p>
        <p
          className={`text-xs font-semibold ${
            record.submit_result === "success"
              ? "text-green-700"
              : record.submit_result === "pending"
                ? "text-yellow-700"
                : "text-red-700"
          }`}
          data-testid="audit-submit-result"
        >
          {record.submit_result.toUpperCase()}
        </p>
      </div>

      {/* Preview Hash */}
      <div>
        <p className="text-xs font-medium text-slate-600 uppercase">Preview Hash</p>
        <p
          className="text-xs text-slate-900 font-mono break-all"
          data-testid="audit-preview-hash"
        >
          {record.preview_hash}
        </p>
      </div>

      {/* Redacted Payload Summary */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-slate-600 uppercase">제출 데이터 (Redacted)</p>
        <div
          className="p-2 bg-white rounded border border-slate-300 text-xs space-y-1"
          data-testid="audit-redacted-payload"
        >
          {Object.entries(record.redacted_payload).map(([key, value]) => (
            <div key={key} className="flex justify-between font-mono text-slate-800">
              <span className="text-slate-600">{key}:</span>
              <span className="text-slate-900">
                {typeof value === "object" && value !== null
                  ? JSON.stringify(value)
                  : String(value)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Redaction Warning */}
      <div
        className="p-2 bg-amber-50 border border-amber-300 rounded text-xs text-amber-900"
        data-testid="redaction-notice"
      >
        <strong>ℹ️ Redaction 주의:</strong> 민감한 정보(비밀번호, 토큰, API 키, 세션)는
        마스킹되었습니다. 원본 값은 감사 로그에 기록되지 않습니다.
      </div>
    </div>
  );
}
