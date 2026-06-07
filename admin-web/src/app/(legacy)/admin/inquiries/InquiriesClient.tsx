"use client";

import { useCallback, useEffect, useState } from "react";

interface Inquiry {
  id: string; name: string; contact: string; company: string;
  subject: string; message: string; status: string; memo: string; created_at: string;
}

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const t = window.localStorage.getItem("haehan_ai_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}
const J = { "Content-Type": "application/json" };

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  new: { label: "접수", cls: "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]" },
  read: { label: "확인", cls: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]" },
  done: { label: "답변완료", cls: "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]" },
};

export function InquiriesClient() {
  const [items, setItems] = useState<Inquiry[]>([]);
  const [counts, setCounts] = useState<{ total?: number; new?: number; done?: number }>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch("/api/proxy/api/v1/inquiries", { headers: authHeader() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setItems(d.items || []); setCounts(d.counts || {});
    } catch (e) { setError(String(e)); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function setStatus(id: string, status: string) {
    await fetch(`/api/proxy/api/v1/inquiries/${id}`, { method: "PATCH", headers: { ...J, ...authHeader() }, body: JSON.stringify({ status }) });
    await load();
  }
  async function saveMemo(id: string, memo: string) {
    await fetch(`/api/proxy/api/v1/inquiries/${id}`, { method: "PATCH", headers: { ...J, ...authHeader() }, body: JSON.stringify({ memo }) });
    await load();
  }

  return (
    <div className="space-y-3 max-w-4xl">
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={load} disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-[#F97316] text-white text-xs font-semibold hover:bg-[#EA580C] disabled:opacity-50">
          {loading ? "불러오는 중…" : "🔄 새로고침"}
        </button>
        <span className="text-xs text-[#6B7280]">전체 {counts.total ?? 0} · <span className="text-[#DC2626] font-semibold">미확인 {counts.new ?? 0}</span> · 완료 {counts.done ?? 0}</span>
      </div>

      {error && <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3 text-sm text-[#DC2626]">오류: {error}</div>}
      {!loading && items.length === 0 && <p className="text-sm text-[#9CA3AF]">접수된 문의가 없습니다.</p>}

      <div className="space-y-2">
        {items.map((q) => {
          const st = STATUS_LABEL[q.status] || STATUS_LABEL.new;
          const expanded = open === q.id;
          return (
            <div key={q.id} className="border border-[#E5E7EB] rounded-2xl bg-white overflow-hidden">
              <button onClick={() => { setOpen(expanded ? null : q.id); if (!expanded && q.status === "new") setStatus(q.id, "read"); }}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#FAFAFA]">
                <span className={`text-[11px] px-2 py-0.5 rounded-full border font-semibold shrink-0 ${st.cls}`}>{st.label}</span>
                <span className="flex-1 min-w-0">
                  <span className="text-sm font-semibold text-[#111827]">{q.subject}</span>
                  <span className="text-xs text-[#9CA3AF] ml-2">{q.name}{q.company ? ` · ${q.company}` : ""}</span>
                </span>
                <span className="text-[11px] text-[#9CA3AF] shrink-0">{q.created_at?.slice(0, 16).replace("T", " ")}</span>
              </button>
              {expanded && (
                <div className="px-4 pb-4 pt-1 space-y-3 border-t border-[#F3F4F6]">
                  <div className="text-sm text-[#374151] whitespace-pre-wrap">{q.message}</div>
                  <div className="text-xs text-[#6B7280]">연락처: <span className="font-medium text-[#111827]">{q.contact || "-"}</span></div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {(["new", "read", "done"] as const).map((s) => (
                      <button key={s} onClick={() => setStatus(q.id, s)}
                        className={`text-xs px-2.5 py-1 rounded-lg border ${q.status === s ? STATUS_LABEL[s].cls : "border-[#E5E7EB] text-[#6B7280] hover:bg-[#F9FAFB]"}`}>
                        {STATUS_LABEL[s].label}
                      </button>
                    ))}
                    {q.contact.includes("@") && (
                      <a href={`mailto:${q.contact}?subject=Re: ${encodeURIComponent(q.subject)}`}
                        className="text-xs px-2.5 py-1 rounded-lg border border-[#BFDBFE] text-[#1D4ED8] bg-[#EFF6FF] hover:bg-[#DBEAFE]">✉ 메일 답장</a>
                    )}
                  </div>
                  <textarea defaultValue={q.memo} placeholder="내부 메모 (저장하려면 포커스 해제)"
                    onBlur={(e) => { if (e.target.value !== q.memo) saveMemo(q.id, e.target.value); }}
                    rows={2} className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-xs outline-none focus:border-[#F97316] resize-none" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
