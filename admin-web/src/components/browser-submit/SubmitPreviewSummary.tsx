"use client";

import React from "react";
import { UserPreviewSummary } from "./__fixtures__/submitApprovalPreview.fixture";

interface SubmitPreviewSummaryProps {
  summary: UserPreviewSummary;
}

export default function SubmitPreviewSummary({
  summary,
}: SubmitPreviewSummaryProps) {
  return (
    <div
      className="bg-white rounded-[12px] border border-slate-200 p-5 space-y-4"
      data-testid="submit-preview-summary"
    >
      {/* Site & Form info */}
      <div className="space-y-1">
        <p className="text-[12px] font-medium text-slate-600 uppercase tracking-wide">
          대상 사이트
        </p>
        <p className="text-[15px] font-bold text-slate-900" data-testid="site-id">
          {summary.site_id}
        </p>
      </div>

      {/* Form title */}
      <div className="space-y-1">
        <p className="text-[12px] font-medium text-slate-600 uppercase tracking-wide">
          양식
        </p>
        <p className="text-[15px] font-bold text-slate-900" data-testid="form-title">
          {summary.form_title}
        </p>
      </div>

      {/* Target description */}
      <div className="space-y-1">
        <p className="text-[12px] font-medium text-slate-600 uppercase tracking-wide">
          대상
        </p>
        <p className="text-[13px] text-slate-700" data-testid="target-description">
          {summary.target_description}
        </p>
      </div>

      {/* Key fields summary (3-5 fields) */}
      <div className="space-y-2">
        <p className="text-[12px] font-medium text-slate-600 uppercase tracking-wide">
          주요 정보
        </p>
        <div
          className="space-y-2 p-4 bg-slate-50 rounded-[8px] border border-slate-200"
          data-testid="field-summary"
        >
          {Object.entries(summary.field_summary).map(([key, value]) => (
            <div key={key} className="flex justify-between text-[13px]">
              <span className="text-slate-600">{key}:</span>
              <span className="text-slate-900 font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Risk level badge */}
      <div className="space-y-2">
        <p className="text-[12px] font-medium text-slate-600 uppercase tracking-wide">
          위험도
        </p>
        <div
          className={`inline-flex items-center px-3 py-1 rounded-full border text-[11px] font-semibold ${
            summary.risk_level === "high"
              ? "bg-red-100 text-red-800 border-red-300"
              : summary.risk_level === "medium"
                ? "bg-yellow-100 text-yellow-800 border-yellow-300"
                : "bg-green-100 text-green-800 border-green-300"
          }`}
          data-testid="risk-level-badge"
        >
          {summary.risk_level === "high" && "⚠️ 높음"}
          {summary.risk_level === "medium" && "⚠️ 중간"}
          {summary.risk_level === "low" && "ℹ️ 낮음"}
        </div>
      </div>

      {/* Risk description */}
      <div className="space-y-1">
        <p className="text-[12px] text-slate-600">{summary.risk_description}</p>
      </div>

      {/* Destructive warning */}
      {summary.is_destructive && (
        <div
          className="p-3 bg-red-50 border border-red-200 rounded-[8px] text-[12px] text-red-900"
          data-testid="destructive-warning"
        >
          <strong>⚠️ 주의:</strong> {summary.destructive_warning}
        </div>
      )}

      {/* Confirmation question */}
      {summary.requires_confirmation && (
        <div
          className="p-3 bg-blue-50 border border-blue-200 rounded-[8px] text-[12px] text-blue-900 font-medium"
          data-testid="confirmation-question"
        >
          {summary.confirmation_question}
        </div>
      )}
    </div>
  );
}
