"use client";

import React from "react";
import { UserPreviewDetails } from "./__fixtures__/submitApprovalPreview.fixture";

interface SubmitPreviewDetailsProps {
  details: UserPreviewDetails;
}

export default function SubmitPreviewDetails({
  details,
}: SubmitPreviewDetailsProps) {
  return (
    <div
      className="bg-white rounded-[12px] border border-slate-200 p-5 space-y-4"
      data-testid="submit-preview-details"
    >
      <h3 className="text-[15px] font-bold text-slate-900">자세한 정보</h3>

      {/* Site & Origin */}
      <div className="grid grid-cols-2 gap-4 py-[9px] border-b border-slate-100">
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            Site ID
          </p>
          <p className="text-[13px] text-slate-900 font-medium mt-1" data-testid="detail-site-id">
            {details.site_id}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            Origin
          </p>
          <p className="text-[13px] text-slate-900 font-medium mt-1" data-testid="detail-origin">
            {details.origin}
          </p>
        </div>
      </div>

      {/* Form & Button IDs */}
      <div className="grid grid-cols-2 gap-4 py-[9px] border-b border-slate-100">
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            Form ID
          </p>
          <p className="text-[13px] text-slate-900 font-medium mt-1" data-testid="detail-form-id">
            {details.form_id}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
            Submit Button
          </p>
          <p className="text-[13px] text-slate-900 font-medium mt-1" data-testid="detail-submit-button">
            {details.submit_button_id}
          </p>
        </div>
      </div>

      {/* Intent */}
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
          Intent
        </p>
        <p className="text-[13px] text-slate-900 font-medium mt-1" data-testid="detail-intent">
          {details.intent}
        </p>
      </div>

      {/* Policy Verdict */}
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
          정책 판정
        </p>
        <p
          className={`text-[13px] font-semibold mt-1 ${
            details.policy_verdict === "ALLOW"
              ? "text-green-700"
              : "text-red-700"
          }`}
          data-testid="detail-policy-verdict"
        >
          {details.policy_verdict === "ALLOW" ? "✓ 허용" : "✗ 거부"}
        </p>
      </div>

      {/* Security Verdicts */}
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide mb-2">
          보안 검증
        </p>
        <div className="space-y-1 text-[13px]">
          <p data-testid="detail-prompt-injection">
            프롬프트 인젝션:
            <span className="ml-2 text-green-700 font-medium">
              {details.prompt_injection_verdict}
            </span>
          </p>
          <p data-testid="detail-hidden-fields">
            숨겨진 필드:
            <span className="ml-2 text-green-700 font-medium">
              {details.hidden_fields_verdict}
            </span>
          </p>
          <p data-testid="detail-denied-fields">
            거부된 필드:
            <span className="ml-2 text-green-700 font-medium">
              {details.denied_fields_verdict}
            </span>
          </p>
        </div>
      </div>

      {/* Validation Reasons */}
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide mb-2">
          검증 사유
        </p>
        <ul className="space-y-1 text-[13px]">
          {details.validator_reasons.map((reason, idx) => (
            <li key={idx} className="text-slate-700 flex items-start gap-2">
              <span className="text-green-600 mt-0.5">✓</span>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Preview Hash - for traceability */}
      <div className="py-[9px] border-b border-slate-100">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
          Preview Hash
        </p>
        <p
          className="text-[11px] text-slate-900 font-mono break-all mt-1"
          data-testid="detail-preview-hash"
        >
          {details.preview_hash}
        </p>
      </div>

      {/* Validation ID */}
      <div className="py-[9px]">
        <p className="text-[11px] font-medium text-slate-600 uppercase tracking-wide">
          Validation ID
        </p>
        <p className="text-[13px] text-slate-900 font-mono mt-1" data-testid="detail-validation-id">
          {details.validation_id}
        </p>
      </div>
    </div>
  );
}
