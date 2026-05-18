/** AuditLogList — 로그·감사 통합 뷰 (APP_LOGS_AUDIT_READONLY_VIEW_01)
 * read-only. execute/approve/reject 없음. token/cookie/secret 원문 표시 금지.
 */
"use client";
import { useState } from "react";
import type { UnifiedLogEntry } from "@/types/assistant";

// ── 상태 스타일 ────────────────────────────────────────────────────────────
const LEVEL_STYLE: Record<string, { bg: string; text: string; border: string }> = {
  INFO:    { bg: "bg-[#F0FDF4]", text: "text-[#059669]", border: "border-[#BBF7D0]" },
  WARN:    { bg: "bg-[#FFFBEB]", text: "text-[#D97706]", border: "border-[#FDE68A]" },
  ERROR:   { bg: "bg-[#FEF2F2]", text: "text-[#B91C1C]", border: "border-[#FECACA]" },
  BLOCKED: { bg: "bg-[#F5F3FF]", text: "text-[#6D28D9]", border: "border-[#DDD6FE]" },
};

// ── 소스 뱃지 ──────────────────────────────────────────────────────────────
function SourceBadge({ source }: { source: UnifiedLogEntry["source"] }) {
  if (source === "ops-api") {
    return (
      <span className="text-[9px] font-mono bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-1 py-0.5 rounded">
        ops-api
      </span>
    );
  }
  return (
    <span className="text-[9px] font-mono bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB] px-1 py-0.5 rounded">
      app-mock
    </span>
  );
}

// ── 요약 카드 ─────────────────────────────────────────────────────────────
function SummaryCards({ entries }: { entries: UnifiedLogEntry[] }) {
  const total = entries.length;
  const warns = entries.filter((e) => e.level === "WARN").length;
  const errors = entries.filter((e) => e.level === "ERROR" || e.level === "BLOCKED").length;

  return (
    <div className="grid grid-cols-3 gap-2">
      {[
        { label: "총 이벤트", value: total, color: "text-[#374151]", bg: "bg-[#F9FAFB]", border: "border-[#E5E7EB]" },
        { label: "경고", value: warns, color: "text-[#D97706]", bg: "bg-[#FFFBEB]", border: "border-[#FDE68A]" },
        { label: "오류·차단", value: errors, color: "text-[#B91C1C]", bg: "bg-[#FEF2F2]", border: "border-[#FECACA]" },
      ].map((card) => (
        <div key={card.label} className={`rounded-lg border ${card.border} ${card.bg} px-3 py-2 text-center`}>
          <div className={`text-lg font-bold font-mono ${card.color}`}>{card.value}</div>
          <div className="text-[10px] text-[#6B7280]">{card.label}</div>
        </div>
      ))}
    </div>
  );
}

// ── 필터 정의 ─────────────────────────────────────────────────────────────
const LEVEL_FILTERS = [
  { value: "ALL", label: "전체" },
  { value: "INFO", label: "INFO" },
  { value: "WARN", label: "WARN" },
  { value: "ERROR", label: "ERROR" },
  { value: "BLOCKED", label: "BLOCKED" },
];

const SOURCE_FILTERS = [
  { value: "ALL", label: "전체" },
  { value: "ops-api", label: "ops-api" },
  { value: "app-mock", label: "app-mock" },
];

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────
export function AuditLogList({ entries }: { entries: UnifiedLogEntry[] }) {
  const [levelFilter, setLevelFilter] = useState("ALL");
  const [sourceFilter, setSourceFilter] = useState("ALL");

  const filtered = entries.filter((e) => {
    const levelOk = levelFilter === "ALL" || e.level === levelFilter;
    const sourceOk = sourceFilter === "ALL" || e.source === sourceFilter;
    return levelOk && sourceOk;
  });

  return (
    <div className="space-y-3">
      {/* 보안 안내 */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-semibold text-[#374151]">감사 로그</span>
        <span className="text-[10px] bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA] px-1.5 py-0.5 rounded font-mono">
          secret/token/cookie 원문 표시 금지
        </span>
        <span className="text-[10px] font-mono text-[#9CA3AF] ml-auto">READ_ONLY</span>
      </div>

      {/* 요약 카드 */}
      <SummaryCards entries={entries} />

      {/* 필터바 */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-[#9CA3AF] font-mono mr-1">상태:</span>
          {LEVEL_FILTERS.map((f) => {
            const style = f.value !== "ALL" ? LEVEL_STYLE[f.value] : null;
            return (
              <button
                key={f.value}
                onClick={() => setLevelFilter(f.value)}
                className={`text-[10px] px-2 py-0.5 rounded border font-mono transition-colors ${
                  levelFilter === f.value
                    ? (style ? `${style.bg} ${style.text} ${style.border}` : "bg-[#374151] text-white border-[#374151]")
                    : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F3F4F6]"
                }`}
              >
                {f.label}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-[#9CA3AF] font-mono mr-1">소스:</span>
          {SOURCE_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setSourceFilter(f.value)}
              className={`text-[10px] px-2 py-0.5 rounded border font-mono transition-colors ${
                sourceFilter === f.value
                  ? "bg-[#1D4ED8] text-white border-[#1D4ED8]"
                  : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F3F4F6]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="text-[10px] font-mono text-[#9CA3AF] self-center ml-auto">
          {filtered.length}/{entries.length}건 표시
        </span>
      </div>

      {/* 빈 상태 */}
      {filtered.length === 0 && (
        <div className="text-sm text-[#9CA3AF] py-6 text-center rounded-lg border border-[#E5E7EB] bg-[#F9FAFB]">
          현재 표시할 이벤트가 없습니다.
          <span className="ml-1 font-mono text-[10px]">READ_ONLY</span>
        </div>
      )}

      {/* 이벤트 테이블 */}
      {filtered.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-[#E5E7EB]">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-[#F9FAFB] border-b border-[#E5E7EB] text-[10px] text-[#6B7280] uppercase tracking-wide">
                <th className="text-left py-2 px-3">시각</th>
                <th className="text-left py-2 px-3">상태</th>
                <th className="text-left py-2 px-3">소스</th>
                <th className="text-left py-2 px-3">이벤트 유형</th>
                <th className="text-left py-2 px-3">대상</th>
                <th className="text-left py-2 px-3">요약</th>
                <th className="text-left py-2 px-3">실행자</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => {
                const style = LEVEL_STYLE[entry.level] ?? LEVEL_STYLE.INFO;
                return (
                  <tr key={entry.id} className="border-b border-[#F3F4F6] hover:bg-[#FAFAFA] transition-colors">
                    <td className="py-2 px-3 font-mono text-[10px] text-[#6B7280] whitespace-nowrap">
                      {entry.timestamp.slice(0, 19).replace("T", " ")}
                    </td>
                    <td className="py-2 px-3">
                      <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${style.bg} ${style.text} ${style.border}`}>
                        {entry.level}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <SourceBadge source={entry.source} />
                    </td>
                    <td className="py-2 px-3 font-mono text-[10px] text-[#374151] max-w-[160px] truncate" title={entry.eventType}>
                      {entry.eventType}
                    </td>
                    <td className="py-2 px-3 font-mono text-[10px] text-[#9CA3AF]">
                      {entry.taskId ?? "—"}
                    </td>
                    <td className="py-2 px-3 text-[11px] text-[#6B7280] max-w-[220px] truncate" title={entry.summary}>
                      {entry.summary}
                    </td>
                    <td className="py-2 px-3 text-[10px] text-[#9CA3AF]">
                      {entry.actor ?? "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* read-only 정책 footer */}
      <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#9CA3AF] border-t border-[#F3F4F6] pt-2">
        <span>execute 없음</span><span>·</span>
        <span>approve 없음</span><span>·</span>
        <span>delete 없음</span><span>·</span>
        <span>token 원문 표시 금지</span><span>·</span>
        <span>B-3 감사 미완 — 토큰 금고 잠금 상태</span>
      </div>
    </div>
  );
}
