"use client";
/** SmartStoreClient — 액션 카탈로그 / 제출 이력 탭 */
import { useState } from "react";
import type { ActionCatalog, ActionItem, CatalogSection, SubmitRecord } from "./page";

type Tab = "catalog" | "history";

const RISK_BADGE: Record<string, string> = {
  read:    "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]",
  prepare: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
  submit:  "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]",
};

const STATUS_BADGE: Record<string, string> = {
  implemented:    "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
  approval_gated: "bg-[#FEF3C7] text-[#92400E] border-[#FDE68A]",
  planned:        "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]",
};

function ActionCard({ action }: { action: ActionItem }) {
  return (
    <div className="border border-[#E5E7EB] rounded-lg p-3 bg-white hover:bg-[#F9FAFB] transition-colors">
      <div className="flex items-start gap-2 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold ${RISK_BADGE[action.risk] ?? RISK_BADGE.read}`}>
          {action.risk}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_BADGE[action.status] ?? STATUS_BADGE.planned}`}>
          {action.status}
        </span>
        <span className="text-xs font-mono text-[#6B7280] bg-[#F3F4F6] px-1.5 py-0.5 rounded border border-[#E5E7EB]">
          {action.action_id}
        </span>
      </div>
      <p className="mt-1.5 text-sm font-medium text-[#111827]">{action.label}</p>
      <p className="text-xs text-[#9CA3AF] font-mono truncate mt-0.5">{action.module}</p>
      {action.required_fields && action.required_fields.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          <span className="text-xs text-[#6B7280]">필수:</span>
          {action.required_fields.map((f) => (
            <span key={f} className="text-xs bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded">{f}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function SectionBlock({ section }: { section: CatalogSection }) {
  const SECTION_COLOR: Record<string, string> = {
    read:    "border-[#BBF7D0] bg-[#F0FDF4] text-[#16A34A]",
    prepare: "border-[#FED7AA] bg-[#FFF7ED] text-[#C2410C]",
    submit:  "border-[#FECACA] bg-[#FEF2F2] text-[#DC2626]",
  };
  const color = SECTION_COLOR[section.name] ?? "border-[#E5E7EB] bg-[#F9FAFB] text-[#6B7280]";

  return (
    <div className="space-y-2">
      <div className={`flex items-center gap-3 px-3 py-2 rounded-lg border ${color}`}>
        <span className="font-bold text-sm uppercase">{section.name}</span>
        <span className="text-xs">총 {section.summary.total}개</span>
        <span className="text-xs">구현 {section.summary.implemented}개</span>
        {section.summary.approval_gated > 0 && (
          <span className="text-xs">승인필요 {section.summary.approval_gated}개</span>
        )}
      </div>
      <div className="grid grid-cols-1 gap-2 pl-2">
        {section.actions.map((a) => (
          <ActionCard key={a.action_id} action={a} />
        ))}
      </div>
    </div>
  );
}

interface Props {
  catalog: ActionCatalog | null;
  catalogError: string | null;
  submit: SubmitRecord | null;
  submitError: string | null;
}

export default function SmartStoreClient({ catalog, catalogError, submit, submitError }: Props) {
  const [tab, setTab] = useState<Tab>("catalog");

  const TABS: { id: Tab; label: string }[] = [
    { id: "catalog", label: "액션 카탈로그" },
    { id: "history", label: "제출 이력" },
  ];

  return (
    <div className="space-y-4">
      {/* 계약 정책 배너 */}
      {catalog?.contract && (
        <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4">
          <p className="text-xs font-bold text-[#C2410C] mb-2">계약 정책 (읽기 전용)</p>
          <div className="grid grid-cols-1 gap-1">
            {Object.entries(catalog.contract).map(([k, v]) => (
              <div key={k} className="flex gap-2 text-xs">
                <span className="font-mono text-[#92400E] w-24 shrink-0">{k}:</span>
                <span className="text-[#78350F]">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-bold text-[#111827]">스마트스토어</span>
          <span className="text-xs bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0] px-2 py-0.5 rounded font-semibold">조회 전용</span>
          {catalog?.generated_at && (
            <span className="text-xs text-[#9CA3AF] ml-auto">{catalog.generated_at}</span>
          )}
        </div>

        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors ${
                tab === t.id
                  ? "border-[#F97316] text-[#F97316] font-semibold"
                  : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 액션 카탈로그 ── */}
        {tab === "catalog" && (
          <div className="space-y-6">
            {catalogError && (
              <p className="text-xs text-[#DC2626]">카탈로그 로드 오류: {catalogError}</p>
            )}
            {catalog?.sections.map((s) => (
              <SectionBlock key={s.name} section={s} />
            ))}
          </div>
        )}

        {/* ── 제출 이력 ── */}
        {tab === "history" && (
          <div className="space-y-3">
            {submitError && (
              <p className="text-xs text-[#DC2626]">제출 이력 로드 오류: {submitError}</p>
            )}
            {submit ? (
              <div className="border border-[#E5E7EB] rounded-xl p-4 bg-white space-y-2">
                <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wide">최근 제출 기록</p>
                {Object.entries(submit).map(([k, v]) => (
                  <div key={k} className="flex gap-3 text-sm">
                    <span className="font-mono text-xs text-[#6B7280] w-32 shrink-0">{k}</span>
                    <span className="text-[#111827] text-xs">
                      {v === true ? (
                        <span className="bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-1.5 py-0.5 rounded text-xs">dry_run</span>
                      ) : v === false ? (
                        <span className="bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded text-xs">live</span>
                      ) : (
                        String(v)
                      )}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              !submitError && (
                <div className="border border-[#E5E7EB] rounded-xl p-8 bg-white text-center">
                  <p className="text-sm text-[#6B7280]">제출 이력 없음</p>
                  <p className="text-xs text-[#9CA3AF] mt-1">아직 제출된 워크플로우가 없습니다.</p>
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}
