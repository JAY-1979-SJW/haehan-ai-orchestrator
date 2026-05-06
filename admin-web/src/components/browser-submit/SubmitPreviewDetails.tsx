"use client";

import React from "react";
import { UserPreviewDetails } from "./__fixtures__/submitApprovalPreview.fixture";

interface SubmitPreviewDetailsProps {
  details: UserPreviewDetails;
}

/**
 * SubmitPreviewDetails
 *
 * Layer 2: Detailed policy information ("자세히 보기" section)
 * Shows technical details for informed decision:
 * - Form/button IDs
 * - Policy validation details
 * - Preview hash for traceability
 * - Validation reasons
 */
export default function SubmitPreviewDetails({
  details,
}: SubmitPreviewDetailsProps) {
  return (
    <div
      className="space-y-4 p-4 bg-gray-50 rounded-lg border border-gray-200"
      data-testid="submit-preview-details"
    >
      <h3 className="font-semibold text-gray-900">자세한 정보</h3>

      {/* Site & Origin */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs font-medium text-gray-600 uppercase">Site ID</p>
          <p className="text-sm text-gray-900" data-testid="detail-site-id">
            {details.site_id}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-600 uppercase">Origin</p>
          <p className="text-sm text-gray-900" data-testid="detail-origin">
            {details.origin}
          </p>
        </div>
      </div>

      {/* Form & Button IDs */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs font-medium text-gray-600 uppercase">Form ID</p>
          <p className="text-sm text-gray-900" data-testid="detail-form-id">
            {details.form_id}
          </p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-600 uppercase">Submit Button</p>
          <p className="text-sm text-gray-900" data-testid="detail-submit-button">
            {details.submit_button_id}
          </p>
        </div>
      </div>

      {/* Intent */}
      <div>
        <p className="text-xs font-medium text-gray-600 uppercase">Intent</p>
        <p className="text-sm text-gray-900" data-testid="detail-intent">
          {details.intent}
        </p>
      </div>

      {/* Policy Verdict */}
      <div>
        <p className="text-xs font-medium text-gray-600 uppercase">정책 판정</p>
        <p
          className={`text-sm font-semibold ${
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
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-600 uppercase">보안 검증</p>
        <div className="space-y-1 text-sm">
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
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-600 uppercase">검증 사유</p>
        <ul className="space-y-1 text-sm">
          {details.validator_reasons.map((reason, idx) => (
            <li key={idx} className="text-gray-700 flex items-start gap-2">
              <span className="text-green-600 mt-0.5">✓</span>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Preview Hash - for traceability */}
      <div className="space-y-1 p-2 bg-white rounded border border-gray-300">
        <p className="text-xs font-medium text-gray-600 uppercase">Preview Hash</p>
        <p
          className="text-xs text-gray-900 font-mono break-all"
          data-testid="detail-preview-hash"
        >
          {details.preview_hash}
        </p>
      </div>

      {/* Validation ID */}
      <div>
        <p className="text-xs font-medium text-gray-600 uppercase">Validation ID</p>
        <p className="text-sm text-gray-900 font-mono" data-testid="detail-validation-id">
          {details.validation_id}
        </p>
      </div>
    </div>
  );
}
