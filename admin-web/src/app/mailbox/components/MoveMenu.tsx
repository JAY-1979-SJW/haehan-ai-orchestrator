"use client";

import { useEffect, useRef, useState } from "react";
import type { Folder } from "../lib/api";

interface Props {
  folders: Folder[];
  /** 지금 있는 폴더(목록에서 뺀다) */
  currentId: string;
  disabled?: boolean;
  onPick: (dest: Folder) => void;
  className?: string;
}

/** "이동 ▾" — 옮길 폴더를 고르는 드롭다운(시스템 폴더 + 내 폴더). */
export function MoveMenu({ folders, currentId, disabled, onPick, className = "" }: Props) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const targets = folders.filter((f) => f.selectable && f.id !== currentId);

  return (
    <div ref={box} className="relative inline-block">
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={`rounded-lg border border-[#E5E7EB] bg-white px-3 py-[5px] text-[12px] text-[#374151] transition-colors hover:bg-[#F9FAFB] disabled:opacity-40 ${className}`}
      >
        📁 이동 ▾
      </button>
      {open && (
        <ul role="menu" aria-label="옮길 폴더" className="absolute left-0 top-full z-30 mt-1 max-h-64 w-52 overflow-y-auto rounded-lg border border-[#E5E7EB] bg-white py-1 shadow-lg">
          {targets.length === 0 && <li className="px-3 py-2 text-[12px] text-[#9CA3AF]">옮길 폴더가 없습니다</li>}
          {targets.map((f) => (
            <li key={f.id} role="none">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onPick(f);
                }}
                className="block w-full truncate py-[6px] pr-3 text-left text-[12px] text-[#374151] hover:bg-[#FFF7ED]"
                style={{ paddingLeft: 12 + f.depth * 12 }}
              >
                {f.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
