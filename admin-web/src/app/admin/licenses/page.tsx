"use client";
import { useState, useEffect, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";

const AUTH = typeof btoa !== "undefined"
  ? `Basic ${btoa(`${process.env.NEXT_PUBLIC_API_USER ?? "owner"}:${process.env.NEXT_PUBLIC_API_PASS ?? ""}`)}`
  : "";

interface License {
  key:         string;
  name:        string;
  email:       string;
  plan:        string;
  issued_at:   string;
  expires_at:  string;
  active:      boolean;
  call_count:  number;
  last_seen:   string | null;
  online:      boolean;
}

export default function LicensesPage() {
  const [licenses, setLicenses]   = useState<License[]>([]);
  const [loading, setLoading]     = useState(false);
  const [issuing, setIssuing]     = useState(false);
  const [form, setForm]           = useState({ name: "", email: "", plan: "basic", days: "365" });
  const [newLicense, setNewLicense] = useState<License | null>(null);
  const [copied, setCopied]       = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/smartstore/admin/licenses`,
        { headers: { Authorization: AUTH } });
      const d = await r.json();
      setLicenses(d.licenses ?? []);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const issue = async () => {
    setIssuing(true);
    setNewLicense(null);
    try {
      const r = await fetch(`${API_BASE}/api/v1/smartstore/admin/licenses/issue`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: AUTH },
        body: JSON.stringify({ name: form.name, email: form.email, plan: form.plan, expire_days: Number(form.days) }),
      });
      const d = await r.json();
      if (d.ok) { setNewLicense(d.license); load(); }
    } finally { setIssuing(false); }
  };

  const revoke = async (key: string) => {
    if (!confirm("라이선스를 취소하시겠습니까?")) return;
    await fetch(`${API_BASE}/api/v1/smartstore/admin/licenses/${encodeURIComponent(key)}`, {
      method: "DELETE", headers: { Authorization: AUTH },
    });
    load();
  };

  const copy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const online  = licenses.filter(l => l.online).length;
  const active  = licenses.filter(l => l.active).length;

  return (
    <PageShell title="라이선스 관리" description="사용자 라이선스 발급·조회·취소" chatDomain="default">
      <div className="space-y-6">

        {/* 통계 */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "전체 발급", value: licenses.length, color: "#1D4ED8" },
            { label: "활성",      value: active,          color: "#16A34A" },
            { label: "온라인",    value: online,          color: "#F97316" },
          ].map(s => (
            <div key={s.label} className="bg-white border border-[#E5E7EB] rounded-xl p-4 text-center">
              <p className="text-2xl font-bold" style={{ color: s.color }}>{s.value}</p>
              <p className="text-xs text-[#6B7280] mt-1">{s.label}</p>
            </div>
          ))}
        </div>

        {/* 발급 폼 */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 space-y-4">
          <p className="text-sm font-bold text-[#111827]">새 라이선스 발급</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-[#374151] block mb-1">이름</label>
              <input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))}
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]" />
            </div>
            <div>
              <label className="text-xs font-semibold text-[#374151] block mb-1">이메일</label>
              <input value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))}
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]" />
            </div>
            <div>
              <label className="text-xs font-semibold text-[#374151] block mb-1">플랜</label>
              <select value={form.plan} onChange={e => setForm(f => ({...f, plan: e.target.value}))}
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]">
                <option value="basic">Basic</option>
                <option value="pro">Pro</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-[#374151] block mb-1">유효 기간(일)</label>
              <input type="number" value={form.days} onChange={e => setForm(f => ({...f, days: e.target.value}))}
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]" />
            </div>
          </div>
          <button onClick={issue} disabled={issuing || !form.name || !form.email}
            className="px-4 py-2 bg-[#F97316] text-white text-sm font-semibold rounded-lg hover:bg-[#EA580C] disabled:opacity-40">
            {issuing ? "발급 중..." : "라이선스 발급"}
          </button>

          {newLicense && (
            <div className="bg-[#F0FDF4] border border-[#BBF7D0] rounded-xl p-4 space-y-2">
              <p className="text-sm font-bold text-[#16A34A]">발급 완료 — 키를 복사해서 사용자에게 전달하세요</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 font-mono text-sm bg-white border border-[#E5E7EB] rounded px-3 py-2 text-[#111827]">
                  {newLicense.key}
                </code>
                <button onClick={() => copy(newLicense.key)}
                  className="px-3 py-2 bg-[#16A34A] text-white text-xs font-semibold rounded-lg">
                  {copied ? "복사됨!" : "복사"}
                </button>
              </div>
              <p className="text-xs text-[#6B7280]">만료: {newLicense.expires_at}</p>
            </div>
          )}
        </div>

        {/* 목록 */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[#E5E7EB]">
            <p className="text-sm font-bold text-[#111827]">발급된 라이선스</p>
            <button onClick={load} disabled={loading}
              className="text-xs text-[#6B7280] hover:text-[#111827] disabled:opacity-40">
              {loading ? "로드 중..." : "새로고침"}
            </button>
          </div>
          <div className="divide-y divide-[#F3F4F6]">
            {licenses.length === 0 && (
              <p className="text-sm text-[#9CA3AF] text-center py-8">발급된 라이선스 없음</p>
            )}
            {licenses.map(lic => (
              <div key={lic.key} className="px-5 py-4 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-[#111827]">{lic.name}</span>
                    <span className="text-xs text-[#6B7280]">{lic.email}</span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      lic.online ? "bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0]"
                                 : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]"
                    }`}>{lic.online ? "온라인" : "오프라인"}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                      lic.active ? "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]"
                                 : "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]"
                    }`}>{lic.plan}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-[#9CA3AF]">
                    <span>만료: {lic.expires_at?.split("T")[0]}</span>
                    <span>호출: {lic.call_count}회</span>
                    {lic.last_seen && <span>최근: {new Date(lic.last_seen).toLocaleString("ko-KR")}</span>}
                  </div>
                  <code className="text-[10px] font-mono text-[#9CA3AF] mt-0.5 block truncate">{lic.key}</code>
                </div>
                <button onClick={() => copy(lic.key)}
                  className="text-xs px-2.5 py-1 border border-[#E5E7EB] rounded-lg text-[#6B7280] hover:bg-[#F3F4F6] shrink-0">
                  키 복사
                </button>
                {lic.active && (
                  <button onClick={() => revoke(lic.key)}
                    className="text-xs px-2.5 py-1 border border-[#FECACA] rounded-lg text-[#DC2626] hover:bg-[#FEF2F2] shrink-0">
                    취소
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </PageShell>
  );
}
