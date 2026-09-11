"use client";
/** /assistant/inbox — 셸: 목록+상세+작성 조립 */
import { useEffect, useState, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { getAssistantInbox } from "@/lib/assistant/api";
import type { InboxItem } from "@/lib/assistant/api";
import { InboxRow } from "./InboxRow";
import { InboxDetail } from "./InboxDetail";
import { ComposeModal } from "./ComposeModal";

export function InboxClient() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<InboxItem | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [showCompose, setShowCompose] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAssistantInbox();
      const sorted = [...(res.items as InboxItem[])].reverse();
      setItems(sorted);
      setSelected((prev) => prev ?? (sorted.length > 0 ? sorted[0] : null));
    } catch (e) {
      setError(e instanceof Error ? e.message : "불러오기 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const filtered =
    filter === "all" ? items : items.filter((i) => i.status === filter);

  return (
    <PageShell title="문의함" description="이메일 · 카카오톡 등 전 채널 문의 통합" chatDomain="inbox">
    <div className="flex flex-col h-full">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-[#E5E7EB] bg-white">
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold text-[#111827]">문의함</span>
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
          <button
            onClick={() => setShowCompose(true)}
            className="text-xs px-3 py-1 bg-[#F97316] text-white rounded hover:bg-[#EA580C]"
          >
            메일 쓰기
          </button>
        </div>
      </div>

      {showCompose && <ComposeModal onClose={() => setShowCompose(false)} />}

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
    </PageShell>
  );
}
