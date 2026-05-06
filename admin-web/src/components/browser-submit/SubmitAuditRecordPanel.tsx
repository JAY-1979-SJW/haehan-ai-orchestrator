"use client";

import React from "react";
import { AuditPreviewRecord } from "./__fixtures__/submitApprovalPreview.fixture";

interface SubmitAuditRecordPanelProps {
  record: AuditPreviewRecord;
}

export default function SubmitAuditRecordPanel({
  record,
}: SubmitAuditRecordPanelProps) {
  return (
    <div
      className="bg-white rounded-[12px] border border-slate-200 p-5 space-y-4"
      data-testid="submit-audit-record-panel"
    >
      {/* Header */}
      <div className="flex items-center gap-2 pb-3 border-b border-slate-200">
        <span className="text-[13px] font-bold text-slate-900">감사 레코드</span>
        <span className="text-[10px] bg-slate-100 text-slate-700 px-2.5 py-0.5 rounded-full font-semibold">
          관리자용
        </span>
      </div>

      {/* Event ID */}
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
          Event ID
        </p>
        <p
          className="text-[11px] text-slate-900 font-mono break-all mt-1"
          data-testid="audit-event-id"
        >
          {record.event_id}
        </p>
      </div>

      {/* Timestamps */}
      <div className="grid grid-cols-2 gap-4 py-[9px] border-b border-slate-100">
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            생성일시
          </p>
          <p className="text-[12px] text-slate-900 mt-1" data-testid="audit-created-at">
            {new Date(record.created_at).toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            Validation ID
          </p>
          <p className="text-[11px] text-slate-900 font-mono mt-1" data-testid="audit-validation-id">
            {record.validation_id}
          </p>
        </div>
      </div>

      {/* User & Tenant (if available) */}
      {(record.user_id || record.tenant_id) && (
        <div className="grid grid-cols-2 gap-4 py-[9px] border-b border-slate-100">
          {record.user_id && (
            <div>
              <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
                User ID
              </p>
              <p className="text-[12px] text-slate-900 mt-1" data-testid="audit-user-id">
                {record.user_id}
              </p>
            </div>
          )}
          {record.tenant_id && (
            <div>
              <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
                Tenant ID
              </p>
              <p className="text-[12px] text-slate-900 mt-1" data-testid="audit-tenant-id">
                {record.tenant_id}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Site & Form Details */}
      <div className="grid grid-cols-3 gap-3 py-[9px] border-b border-slate-100">
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            Site
          </p>
          <p className="text-[12px] text-slate-900 mt-1" data-testid="audit-site-id">
            {record.site_id}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            Form
          </p>
          <p className="text-[12px] text-slate-900 mt-1" data-testid="audit-form-id">
            {record.form_id}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            Button
          </p>
          <p className="text-[12px] text-slate-900 mt-1" data-testid="audit-submit-button-id">
            {record.submit_button_id}
          </p>
        </div>
      </div>

      {/* Policy & User Confirmation */}
      <div className="grid grid-cols-3 gap-3 py-[9px] border-b border-slate-100">
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            정책
          </p>
          <p
            className={`text-[12px] font-semibold mt-1 ${
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
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            사용자 승인
          </p>
          <p
            className={`text-[12px] font-semibold mt-1 ${
              record.user_confirmed ? "text-green-700" : "text-slate-600"
            }`}
            data-testid="audit-user-confirmed"
          >
            {record.user_confirmed ? "✓ Yes" : "○ No"}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            제출됨
          </p>
          <p
            className={`text-[12px] font-semibold mt-1 ${
              record.submitted ? "text-green-700" : "text-slate-600"
            }`}
            data-testid="audit-submitted"
          >
            {record.submitted ? "✓ Yes" : "○ No"}
          </p>
        </div>
      </div>

      {/* Submit Result */}
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
          제출 결과
        </p>
        <p
          className={`text-[12px] font-semibold mt-1 ${
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
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
          Preview Hash
        </p>
        <p
          className="text-[11px] text-slate-900 font-mono break-all mt-1"
          data-testid="audit-preview-hash"
        >
          {record.preview_hash}
        </p>
      </div>

      {/* Redacted Payload Summary */}
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide mb-2">
          제출 데이터 (Redacted)
        </p>
        <div
          className="p-3 bg-slate-50 rounded-[8px] border border-slate-200 text-[12px] space-y-1"
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
        className="p-3 bg-amber-50 border border-amber-200 rounded-[8px] text-[12px] text-amber-900"
        data-testid="redaction-notice"
      >
        <strong>ℹ️ Redaction 주의:</strong> 민감한 정보(비밀번호, 토큰, API 키, 세션)는
        마스킹되었습니다. 원본 값은 감사 로그에 기록되지 않습니다.
      </div>
    </div>
  );
}
