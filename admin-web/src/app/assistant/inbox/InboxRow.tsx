"use client";
/** 메일함 — 목록 행 */
import type { InboxItem } from "@/lib/assistant/api";
import { SOURCE_LABEL, STATUS_LABEL, STATUS_STYLE, timeAgo } from "./inboxShared";

export function InboxRow({
  item,
  onClick,
  selected,
}: {
  item: InboxItem;
  onClick: () => void;
  selected: boolean;
}) {
  const statusStyle = STATUS_STYLE[item.status ?? "new"] ?? STATUS_STYLE["new"];
  const sourceLabel = SOURCE_LABEL[item.source_type ?? ""] ?? item.source_type ?? "-";

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 border-b border-[#F3F4F6] hover:bg-[#F9FAFB] transition-colors ${
        selected ? "bg-[#EFF6FF]" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs px-1.5 py-0.5 rounded border font-medium bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]">
              {sourceLabel}
            </span>
            <span
              className={`text-xs px-1.5 py-0.5 rounded border font-medium ${statusStyle}`}
            >
              {STATUS_LABEL[item.status ?? "new"] ?? item.status}
            </span>
            <span className="text-xs text-[#9CA3AF] ml-auto">
              {timeAgo(item.received_at ?? "")}
            </span>
          </div>
          <div className="text-sm font-semibold text-[#111827] truncate">
            {item.title || "(제목 없음)"}
          </div>
          <div className="text-xs text-[#6B7280] truncate mt-0.5">
            {item.sender || item.source_account || "-"}
          </div>
        </div>
      </div>
    </button>
  );
}

