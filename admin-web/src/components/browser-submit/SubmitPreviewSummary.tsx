"use client";

import React from "react";
import { UserPreviewSummary } from "./__fixtures__/submitApprovalPreview.fixture";

interface SubmitPreviewSummaryProps {
  summary: UserPreviewSummary;
}

/**
 * SubmitPreviewSummary
 *
 * Layer 1: User-facing summary card
 * Shows essential info for quick approval decision
 * - Site & form title
 * - Key field values (3-5)
 * - Risk level badge
 * - Destructive warning
 * - Confirmation question
 */
export default function SubmitPreviewSummary({
  summary,
}: SubmitPreviewSummaryProps) {
  return (
    <div className="space-y-4" data-testid="submit-preview-summary">
      {/* Site & Form info */}
      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-600">대상 사이트</p>
        <p className="text-base font-semibold text-gray-900" data-testid="site-id">
          {summary.site_id}
        </p>
      </div>

      {/* Form title */}
      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-600">양식</p>
        <p className="text-base font-semibold text-gray-900" data-testid="form-title">
          {summary.form_title}
        </p>
      </div>

      {/* Target description */}
      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-600">대상</p>
        <p className="text-sm text-gray-700" data-testid="target-description">
          {summary.target_description}
        </p>
      </div>

      {/* Key fields summary (3-5 fields) */}
      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-600">주요 정보</p>
        <div
          className="space-y-2 p-3 bg-gray-50 rounded border border-gray-200"
          data-testid="field-summary"
        >
          {Object.entries(summary.field_summary).map(([key, value]) => (
            <div key={key} className="flex justify-between text-sm">
              <span className="text-gray-600">{key}:</span>
              <span className="text-gray-900 font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Risk level badge */}
      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-600">위험도</p>
        <div
          className={`px-3 py-2 rounded-lg font-medium text-sm inline-block ${
            summary.risk_level === "high"
              ? "bg-red-100 text-red-800"
              : summary.risk_level === "medium"
                ? "bg-yellow-100 text-yellow-800"
                : "bg-green-100 text-green-800"
          }`}
          data-testid="risk-level-badge"
        >
          {summary.risk_level === "high" && "⚠️ 높음"}
          {summary.risk_level === "medium" && "⚠️ 중간"}
          {summary.risk_level === "low" && "ℹ️ 낮음"}
        </div>
      </div>

      {/* Risk description */}
      <div className="space-y-2">
        <p className="text-sm text-gray-600">{summary.risk_description}</p>
      </div>

      {/* Destructive warning */}
      {summary.is_destructive && (
        <div
          className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800"
          data-testid="destructive-warning"
        >
          <strong>⚠️ 주의:</strong> {summary.destructive_warning}
        </div>
      )}

      {/* Confirmation question */}
      {summary.requires_confirmation && (
        <div
          className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900 font-medium"
          data-testid="confirmation-question"
        >
          {summary.confirmation_question}
        </div>
      )}
    </div>
  );
}
