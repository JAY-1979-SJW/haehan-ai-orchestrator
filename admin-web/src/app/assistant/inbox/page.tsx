"use client";
/**
 * 메일 inbox 조회 페이지 — read-only
 * GET /api/v1/inbox → InboxItem 목록 표시
 */
import { useEffect, useState, useCallback } from "react";
import { getAssistantInbox } from "@/lib/assistant/api";
import type { InboxItem } from "@/lib/assistant/api";

const SOURCE_LABEL: Record<string, string> = {
  telegram_command: "텔레그램",
  email: "이메일",
  gmail: "Gmail",
  naver_mail: "네이버",
  hiworks: "하이웍스",
  manual: "수동",
};

const STATUS_STYLE: Record<string, string> = {
  new: "bg-blue-50 text-blue-700 border-blue-200",
  reviewed: "bg-yellow-50 text-yellow-700 border-yellow-200",
  task_created: "bg-green-50 text-green-700 border-green-200",
  archived: "bg-gray-50 text-gray-500 border-gray-200",
};

const STATUS_LABEL: Record<string, string> = {
  new: "신규",
  reviewed: "검토됨",
  task_created: "작업생성",
  archived: "보관",
};

function timeAgo(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 60) return `${m}분 전`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}시간 전`;
    return `${Math.floor(h / 24)}일 전`;
  } catch {
    return iso?.slice(0, 10) ?? "-";
  }
}

function InboxRow({
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

function InboxDetail({ item }: { item: InboxItem }) {
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

export default function InboxPage() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<InboxItem | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAssistantInbox();
      const sorted = [...(res.items as InboxItem[])].reverse();
      setItems(sorted);
      if (sorted.length > 0 && !selected) setSelected(sorted[0]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "불러오기 실패");
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  const filtered =
    filter === "all" ? items : items.filter((i) => i.status === filter);

  return (
    <div className="flex flex-col h-full">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-[#E5E7EB] bg-white">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-bold text-[#111827]">메일 inbox</h1>
          {!loading && (
            <span className="text-xs text-[#6B7280]">
              총 {items.length}건
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="text-xs border border-[#E5E7EB] rounded px-2 py-1 text-[#374151]"
          >
            <option value="all">전체</option>
            <option value="new">신규</option>
            <option value="reviewed">검토됨</option>
            <option value="task_created">작업생성</option>
            <option value="archived">보관</option>
          </select>
          <button
            onClick={load}
            disabled={loading}
            className="text-xs px-3 py-1 border border-[#E5E7EB] rounded text-[#374151] hover:bg-[#F3F4F6] disabled:opacity-50"
          >
            {loading ? "로딩…" : "새로고침"}
          </button>
        </div>
      </div>

      {/* 에러 */}
      {error && (
        <div className="mx-4 mt-3 p-3 bg-red-50 border border-red-200 rounded text-xs text-red-700">
          ⚠ {error}
        </div>
      )}

      {/* 본문 — 목록 + 상세 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 목록 */}
        <div className="w-80 flex-shrink-0 border-r border-[#E5E7EB] overflow-y-auto bg-white">
          {loading && items.length === 0 ? (
            <div className="p-6 text-center text-xs text-[#9CA3AF]">
              불러오는 중…
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-6 text-center text-xs text-[#9CA3AF]">
              메일이 없습니다
            </div>
          ) : (
            filtered.map((item) => (
              <InboxRow
                key={item.item_id}
                item={item}
                selected={selected?.item_id === item.item_id}
                onClick={() => setSelected(item)}
              />
            ))
          )}
        </div>

        {/* 상세 */}
        <div className="flex-1 overflow-hidden bg-white">
          {selected ? (
            <InboxDetail item={selected} />
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-[#9CA3AF]">
              메일을 선택하세요
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
