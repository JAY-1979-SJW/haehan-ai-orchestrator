"use client";
/** 메일함 — 상세 */
import type { InboxItem } from "@/lib/assistant/api";
import { CATEGORY_LABEL, SOURCE_LABEL } from "./inboxShared";

export function InboxDetail({ item }: { item: InboxItem }) {
  const classification = item.metadata?.classification as
    | { category?: string; priority?: string; needs_review?: boolean }
    | undefined;

  return (
    <div className="p-5 h-full overflow-y-auto">
      <div className="mb-4">
        <h2 className="text-base font-bold text-[#111827] mb-2">
          {item.title || "(제목 없음)"}
        </h2>
        <div className="flex flex-wrap gap-2 text-xs text-[#6B7280]">
          <span>
            <span className="font-medium">발신:</span>{" "}
            {item.sender || item.source_account || "-"}
          </span>
          <span>·</span>
          <span>
            <span className="font-medium">채널:</span>{" "}
            {SOURCE_LABEL[item.source_type ?? ""] ?? item.source_type ?? "-"}
          </span>
          <span>·</span>
          <span>
            <span className="font-medium">수신:</span>{" "}
            {item.received_at?.replace("T", " ").slice(0, 16) ?? "-"}
          </span>
          {classification?.category && (
            <>
              <span>·</span>
              <span className="px-1.5 py-0.5 rounded border border-[#DBEAFE] bg-[#EFF6FF] text-[#1D4ED8] font-medium">
                {CATEGORY_LABEL[classification.category] ?? classification.category}
              </span>
            </>
          )}
          {classification?.priority === "high" && (
            <span className="px-1.5 py-0.5 rounded border border-[#FECACA] bg-[#FEF2F2] text-[#B91C1C] font-medium">
              긴급
            </span>
          )}
        </div>
      </div>

      {item.body_summary && (
        <div className="mb-4 p-3 bg-[#F0FDF4] border border-[#BBF7D0] rounded-lg">
          <div className="text-xs font-semibold text-[#15803D] mb-1">AI 요약</div>
          <div className="text-sm text-[#166534]">{item.body_summary}</div>
        </div>
      )}

      <div className="bg-[#F9FAFB] border border-[#E5E7EB] rounded-lg p-4">
        <div className="text-xs font-semibold text-[#6B7280] mb-2">본문</div>
        <pre className="text-sm text-[#374151] whitespace-pre-wrap font-sans leading-relaxed">
          {item.body_raw || "(본문 없음)"}
        </pre>
      </div>

      {item.linked_task_id && (
        <div className="mt-3 text-xs text-[#6B7280]">
          연결 작업 ID:{" "}
          <span className="font-mono text-[#1D4ED8]">{item.linked_task_id}</span>
        </div>
      )}
    </div>
  );
}

// ── 메일 작성 모달 ──────────────────────────────────────────────────────────

