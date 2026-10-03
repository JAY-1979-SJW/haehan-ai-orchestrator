"use client";

export interface NewMailToastData {
  label: string;
  from: string;
  subject: string;
}

/** 새 메일 도착 알림 — 누르면 받은편지함 첫 쪽으로 이동한다. */
export function NewMailToast({ data, onOpen, onClose }: { data: NewMailToastData; onOpen: () => void; onClose: () => void }) {
  return (
    <div role="status" className="fixed bottom-4 right-4 z-50 flex max-w-sm items-start gap-3 rounded-xl border px-4 py-3 shadow-lg" style={{ background: "var(--surface, #fff)", borderColor: "#BFDBFE" }}>
      <button type="button" className="min-w-0 flex-1 text-left" onClick={onOpen}>
        <div className="text-[13px] font-semibold" style={{ color: "#1D4ED8" }}>새 메일 {data.label}통</div>
        {data.from && <div className="truncate text-[12px]">{data.from}</div>}
        {data.subject && <div className="truncate text-[12px] opacity-70">{data.subject}</div>}
      </button>
      <button type="button" aria-label="알림 닫기" className="text-[12px] underline" onClick={onClose}>닫기</button>
    </div>
  );
}
