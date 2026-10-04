"use client";

import { useRef } from "react";
import type { Folder } from "../lib/api";

interface Props {
  folders: Folder[];
  current: string;
  onSelect: (id: string) => void;
  onCompose: () => void;
  onEmpty: (f: Folder) => void;
  /** 폴더 위에 잠깐 머물렀을 때 — 첫 페이지를 미리 받아 두면 클릭할 때 바로 열린다 */
  onHover: (f: Folder) => void;
  loading: boolean;
}

const ICON: Record<string, string> = {
  inbox: "📥",
  sent: "📤",
  drafts: "📝",
  junk: "🚫",
  trash: "🗑",
  user: "📁",
};

/** 목차(폴더 목록) — 시스템 폴더 다음에 내 폴더. 안 읽은 수는 주황 배지. */
export function FolderTree({ folders, current, onSelect, onCompose, onEmpty, onHover, loading }: Props) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoverStart = (f: Folder) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onHover(f), 150);
  };
  const hoverEnd = () => {
    if (timer.current) clearTimeout(timer.current);
  };

  return (
    <nav aria-label="메일함 목차" className="flex h-full min-h-0 flex-col bg-white">
      <div className="shrink-0 p-3">
        <button
          type="button"
          onClick={onCompose}
          className="w-full rounded-xl bg-[#F97316] py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[#EA580C]"
        >
          ✉ 메일 쓰기
        </button>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto pb-3">
        {loading && folders.length === 0 && <li className="px-4 py-2 text-[12px] text-[#9CA3AF]">불러오는 중…</li>}
        {folders.map((f, i) => {
          const active = f.id === current;
          const firstUser = f.kind === "user" && (i === 0 || folders[i - 1].kind !== "user");
          const emptiable = (f.kind === "trash" || f.kind === "junk") && f.total > 0;
          return (
            <li key={f.id} className="group relative">
              {firstUser && <div className="mx-3 mb-1 mt-3 border-t border-[#F3F4F6] pt-2 text-[10px] font-semibold tracking-widest text-[#9CA3AF]">내 폴더</div>}
              <button
                type="button"
                disabled={!f.selectable}
                onClick={() => onSelect(f.id)}
                onMouseEnter={() => hoverStart(f)}
                onMouseLeave={hoverEnd}
                aria-current={active ? "page" : undefined}
                className="flex w-full items-center gap-2 py-[7px] pr-3 text-left text-[13px] transition-colors disabled:opacity-40"
                style={{
                  paddingLeft: 16 + f.depth * 14,
                  background: active ? "#FFF7ED" : "transparent",
                  color: active ? "#C2410C" : "#374151",
                  fontWeight: active || f.unseen > 0 ? 600 : 400,
                }}
              >
                <span aria-hidden="true" className="w-4 shrink-0 text-center text-[12px]">{ICON[f.kind] ?? ICON.user}</span>
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                {f.unseen > 0 && (
                  <span className="shrink-0 rounded-full bg-[#F97316] px-[7px] py-px text-[10px] font-bold text-white">{f.unseen}</span>
                )}
              </button>
              {emptiable && (
                <button
                  type="button"
                  onClick={() => onEmpty(f)}
                  title={`${f.name} 비우기 (영구 삭제)`}
                  aria-label={`${f.name} 비우기`}
                  className="absolute right-[44px] top-1/2 hidden -translate-y-1/2 rounded bg-white px-[6px] py-px text-[10px] text-[#B91C1C] shadow ring-1 ring-[#FECACA] group-hover:block focus:block"
                >
                  비우기
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
