"use client";

import { useRef, useState } from "react";
import type { Folder, MessageList as MessageListData } from "../lib/api";
import { formatListDate, formatSize, senderName } from "../lib/format";
import { MoveMenu } from "./MoveMenu";

export type MailFilter = "all" | "unseen" | "attach";

interface Props {
  data: MessageListData | null;
  loading: boolean;
  error: string | null;
  selectedUid: number | null;
  /** 체크박스로 고른 메일 */
  checked: number[];
  filter: MailFilter;
  query: string;
  folder: Folder | undefined;
  folders: Folder[];
  onSelect: (uid: number) => void;
  /** 마우스를 잠깐 올려 둔 메일 — 미리 받아 두면 클릭할 때 바로 열린다 */
  onHover: (uid: number) => void;
  onCheck: (uid: number, on: boolean) => void;
  onCheckAll: (on: boolean) => void;
  onFilter: (f: MailFilter) => void;
  onSearch: (q: string) => void;
  onPage: (page: number) => void;
  onRefresh: () => void;
  onTrash: () => void;
  onMove: (dest: Folder) => void;
  onSeen: (seen: boolean) => void;
  onPurge: () => void;
  onEmpty: () => void;
}

const FILTERS: { key: MailFilter; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "unseen", label: "안읽음" },
  { key: "attach", label: "첨부" },
];

const HOVER_DELAY_MS = 120; // 스치듯 지나가는 것까지 받지 않도록 잠깐 머물렀을 때만

export function MessageList(p: Props) {
  const [draft, setDraft] = useState(p.query);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function hoverStart(uid: number) {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hoverTimer.current = setTimeout(() => p.onHover(uid), HOVER_DELAY_MS);
  }

  function hoverEnd() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
  }

  const { data } = p;
  const lastPage = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;
  const rows = data?.messages ?? [];
  const allChecked = rows.length > 0 && rows.every((m) => p.checked.includes(m.uid));
  const none = p.checked.length === 0;
  const purgeable = p.folder?.kind === "trash" || p.folder?.kind === "junk";
  const tool = "rounded-lg border border-[#E5E7EB] bg-white px-3 py-[5px] text-[12px] text-[#374151] transition-colors hover:bg-[#F9FAFB] disabled:opacity-40";

  return (
    <section aria-label="메일 목록" className="flex h-full min-h-0 flex-col bg-white">
      <div className="shrink-0 space-y-2 border-b border-[#F3F4F6] p-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-bold text-[#0F172A]">
            {p.folder?.name ?? "받은편지함"} <span className="text-[12px] font-normal text-[#9CA3AF]">{data ? `${data.total}통` : ""}</span>
            {p.loading && <span role="status" className="ml-2 text-[12px] font-normal text-[#F97316]">불러오는 중…</span>}
          </h2>
          <button type="button" onClick={p.onRefresh} className="rounded-lg px-2 py-1 text-[12px] text-[#6B7280] hover:bg-[#F3F4F6]" title="새로고침">
            ↻ 새로고침
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            p.onSearch(draft.trim());
          }}
          className="flex gap-2"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="제목·보낸 사람 검색"
            className="min-w-0 flex-1 rounded-lg border border-[#E5E7EB] px-3 py-[6px] text-[13px] outline-none focus:border-[#F97316]"
          />
          <button type="submit" className="shrink-0 rounded-lg border border-[#E5E7EB] px-3 text-[12px] text-[#374151] hover:bg-[#F9FAFB]">검색</button>
        </form>
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => p.onFilter(f.key)}
              className="rounded-full px-3 py-[3px] text-[12px]"
              style={{
                background: p.filter === f.key ? "#FFF7ED" : "#F3F4F6",
                color: p.filter === f.key ? "#C2410C" : "#6B7280",
                border: p.filter === f.key ? "1px solid #FED7AA" : "1px solid transparent",
                fontWeight: p.filter === f.key ? 600 : 400,
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* 도구줄: 선택한 메일에 적용 (네이버 메일처럼 목록 위) */}
      <div role="toolbar" aria-label="선택한 메일 작업" className="flex shrink-0 flex-wrap items-center gap-1 border-b border-[#F3F4F6] bg-[#FAFAFA] px-3 py-[6px]">
        <label className="mr-1 flex items-center gap-1 text-[12px] text-[#6B7280]">
          <input type="checkbox" aria-label="이 페이지 전체 선택" checked={allChecked} onChange={(e) => p.onCheckAll(e.target.checked)} />
          {none ? "전체" : `${p.checked.length}개`}
        </label>
        {purgeable ? (
          <>
            <button type="button" className={`${tool} text-[#B91C1C]`} disabled={none} onClick={p.onPurge}>영구 삭제</button>
            <button type="button" className={`${tool} text-[#B91C1C]`} disabled={!data || data.total === 0} onClick={p.onEmpty}>
              {p.folder?.kind === "trash" ? "휴지통 비우기" : "스팸 비우기"}
            </button>
          </>
        ) : (
          <button type="button" className={`${tool} text-[#B91C1C]`} disabled={none} onClick={p.onTrash}>🗑 삭제</button>
        )}
        <MoveMenu folders={p.folders} currentId={p.folder?.id ?? ""} disabled={none} onPick={p.onMove} />
        <button type="button" className={tool} disabled={none} onClick={() => p.onSeen(true)}>읽음</button>
        <button type="button" className={tool} disabled={none} onClick={() => p.onSeen(false)}>안읽음</button>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto transition-opacity" style={{ opacity: p.loading && data ? 0.5 : 1 }} aria-busy={p.loading}>
        {p.error && <li className="p-4 text-[13px] text-[#B91C1C]">{p.error}</li>}
        {p.loading && !data && <li className="p-4 text-[13px] text-[#9CA3AF]">불러오는 중…</li>}
        {data && rows.length === 0 && !p.error && <li className="p-6 text-center text-[13px] text-[#9CA3AF]">메일이 없습니다</li>}
        {rows.map((m) => {
          const active = m.uid === p.selectedUid;
          const isChecked = p.checked.includes(m.uid);
          return (
            <li key={m.uid} className="flex items-stretch border-b border-[#F3F4F6] hover:bg-[#FAFAFA]" style={{ background: isChecked ? "#FFFBEB" : active ? "#FFF7ED" : undefined }}>
              <label className="flex w-9 shrink-0 cursor-pointer items-center justify-center">
                <input type="checkbox" aria-label={`${senderName(m.from)}: ${m.subject || "(제목 없음)"} 선택`} checked={isChecked} onChange={(e) => p.onCheck(m.uid, e.target.checked)} />
              </label>
              <button
                type="button"
                onClick={() => p.onSelect(m.uid)}
                onMouseEnter={() => hoverStart(m.uid)}
                onFocus={() => hoverStart(m.uid)}
                onMouseLeave={hoverEnd}
                className="block min-w-0 flex-1 py-[9px] pr-3 text-left"
              >
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: m.seen ? "transparent" : "#F97316" }} aria-label={m.seen ? "읽음" : "안 읽음"} />
                  <span className="min-w-0 flex-1 truncate text-[13px]" style={{ fontWeight: m.seen ? 400 : 700, color: "#111827" }}>
                    {senderName(m.from)}
                  </span>
                  <span className="shrink-0 text-[11px] text-[#9CA3AF]">{formatListDate(m.date_iso, m.date)}</span>
                </div>
                <div className="mt-[2px] flex items-center gap-1 pl-4">
                  <span className="min-w-0 flex-1 truncate text-[12px]" style={{ fontWeight: m.seen ? 400 : 600, color: m.seen ? "#6B7280" : "#1F2937" }}>
                    {m.subject || "(제목 없음)"}
                  </span>
                  {m.has_attachment && <span title="첨부 파일" aria-label="첨부 파일 있음" className="shrink-0 text-[12px]">📎</span>}
                  <span className="shrink-0 text-[10px] text-[#9CA3AF]">{formatSize(m.size)}</span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>

      {data && (
        <div className="flex shrink-0 items-center justify-between border-t border-[#F3F4F6] px-3 py-2 text-[12px] text-[#6B7280]">
          <button type="button" disabled={data.page <= 1} onClick={() => p.onPage(data.page - 1)} className="rounded-lg px-2 py-1 hover:bg-[#F3F4F6] disabled:opacity-30">◀ 이전</button>
          <span>
            {data.page} / {lastPage}
            {data.truncated && <span title="검색은 최근 500통까지만 훑습니다"> · 최근 500통</span>}
          </span>
          <button type="button" disabled={data.page >= lastPage} onClick={() => p.onPage(data.page + 1)} className="rounded-lg px-2 py-1 hover:bg-[#F3F4F6] disabled:opacity-30">다음 ▶</button>
        </div>
      )}
    </section>
  );
}
