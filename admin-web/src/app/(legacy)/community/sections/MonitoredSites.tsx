"use client";
/** 커뮤니티 레이더 — 모니터링 사이트 등록/목록 */
import { useState } from "react";
import { type Site, authHeader, J } from "../communityShared";

export function MonitoredSites({ sites, analyzingUrl, onAnalyze, onChanged, onError }: {
  sites: Site[];
  analyzingUrl: string | null;
  onAnalyze: (url: string, label: string) => void;
  onChanged: () => void;
  onError: (msg: string | null) => void;
}) {
  const [newUrl, setNewUrl] = useState("");
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);

  async function addSite() {
    if (!newUrl.trim()) return;
    setAdding(true); onError(null);
    try {
      const r = await fetch("/api/proxy/api/v1/community/sites", {
        method: "POST", headers: { ...J, ...authHeader() },
        body: JSON.stringify({ url: newUrl.trim(), name: newName.trim() }),
      });
      const d = await r.json();
      if (!r.ok || d.ok === false) throw new Error(d.detail || "등록 실패");
      setNewUrl(""); setNewName(""); onChanged();
    } catch (e) { onError(String(e)); } finally { setAdding(false); }
  }

  async function removeSite(id: string) {
    await fetch(`/api/proxy/api/v1/community/sites/${id}`, { method: "DELETE", headers: authHeader() });
    onChanged();
  }

  return (
    <div className="border border-[#E5E7EB] rounded-2xl bg-white p-4 space-y-3">
      <p className="text-sm font-bold text-[#111827]">모니터링 사이트</p>
      <div className="flex flex-wrap gap-2">
        <input value={newUrl} onChange={(e) => setNewUrl(e.target.value)}
          placeholder="게시판 URL (예: https://www.clien.net/service/board/park)"
          className="flex-1 min-w-[260px] border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#F97316]" />
        <input value={newName} onChange={(e) => setNewName(e.target.value)}
          placeholder="이름(선택)"
          className="w-32 border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#F97316]" />
        <button onClick={addSite} disabled={adding || !newUrl.trim()}
          className="px-4 py-2 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-40">
          {adding ? "등록 중…" : "+ 등록"}
        </button>
      </div>
      <p className="text-[11px] text-[#9CA3AF]">URL만 등록하면 사이트별 설정 없이 AI가 게시글을 추출·분석합니다(휴리스틱→GPT).</p>

      <div className="divide-y divide-[#F3F4F6]">
        {sites.length === 0 && <p className="text-sm text-[#9CA3AF] py-3">등록된 사이트가 없습니다.</p>}
        {sites.map((s) => (
          <div key={s.id} className="flex items-center gap-3 py-2.5">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[#111827] truncate">{s.name}</p>
              <p className="text-[11px] text-[#9CA3AF] truncate">{s.url}</p>
            </div>
            <button onClick={() => onAnalyze(s.url, s.name)} disabled={analyzingUrl === s.url}
              className="px-3 py-1.5 rounded-lg bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] text-xs font-semibold hover:bg-[#FED7AA] disabled:opacity-40 shrink-0">
              {analyzingUrl === s.url ? "분석 중…" : "🔍 수집·분석"}
            </button>
            <button onClick={() => removeSite(s.id)}
              className="text-[#9CA3AF] hover:text-[#DC2626] text-sm px-1 shrink-0">✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}
