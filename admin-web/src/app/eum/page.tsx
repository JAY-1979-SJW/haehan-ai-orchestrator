"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getMe, type UserInfo } from "@/lib/userAuth";

const API = "/api/proxy/api/v1/eum";

interface Target {
  rank: number;
  grade: string;
  score: number;
  email: string;
  subject: string;
  project_name: string;
  company: string;
  manager: string;
  phone: string;
  branch: string;
  reasons: string[];
  body: string;
}

export default function EumPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false);
  const [stats, setStats] = useState<{ sites: number; selected: number } | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [sending, setSending] = useState<string | null>(null);
  const [sent, setSent] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe().then((u) => {
      if (!u) { router.push("/login"); return; }
      if (u.role !== "owner" && u.role !== "admin") { router.replace("/"); return; }
      setUser(u);
      setLoading(false);
    });
  }, [router]);

  const loadTargets = useCallback(async () => {
    try {
      const r = await fetch(`${API}/sales-mail/targets`);
      const d = await r.json();
      if (d.ok) setTargets(d.targets || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { if (user) loadTargets(); }, [user, loadTargets]);

  const collect = async () => {
    setCollecting(true); setError(null);
    try {
      const r = await fetch(`${API}/sales-mail/collect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_pages: 20 }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "수집 실패");
      setStats({ sites: d.collected_sites, selected: d.selected_targets });
      await loadTargets();
    } catch (e) {
      setError(e instanceof Error ? e.message : "수집 실패");
    } finally {
      setCollecting(false);
    }
  };

  const send = async (t: Target) => {
    if (!confirm(`${t.company} ${t.manager}님(${t.email})에게 영업메일을 하이웍스로 발송할까요?\n\n제목: ${t.subject}`)) return;
    setSending(t.email); setError(null);
    try {
      const r = await fetch(`${API}/sales-mail/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to: t.email, subject: t.subject, body: t.body, confirmed: true }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "발송 실패");
      setSent((s) => ({ ...s, [t.email]: "발송됨" }));
    } catch (e) {
      setError(`발송 실패: ${e instanceof Error ? e.message : ""}`);
    } finally {
      setSending(null);
    }
  };

  if (loading) {
    return <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center"><p className="text-sm text-[#6B7280]">로딩 중...</p></div>;
  }
  if (!user) return null;

  return (
    <div className="min-h-screen bg-[#F9FAFB] px-4 py-8">
      <div className="max-w-4xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#0891B2] flex items-center justify-center text-white font-bold text-xs">E</div>
            <div>
              <h1 className="text-lg font-bold text-[#111827]">EUM 단말기 영업</h1>
              <p className="text-xs text-[#6B7280]">신규현장 발굴 → 영업메일 (하이웍스 발송)</p>
            </div>
          </div>
          <Link href="/" className="text-sm text-[#6B7280] hover:text-[#111827]">← 홈</Link>
        </div>

        {/* 수집 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-bold text-[#111827]">신규현장 수집 + 영업타겟 준비</p>
              <p className="text-xs text-[#6B7280] mt-1">EUM 설치대상(WEBMAN370M00) 전수 수집 후 등급 A 타겟 선별·초안 생성</p>
            </div>
            <button onClick={collect} disabled={collecting}
              className="px-4 py-2.5 rounded-xl bg-[#0891B2] text-white text-sm font-semibold hover:bg-[#0E7490] disabled:opacity-50">
              {collecting ? "수집 중... (1~2분)" : "수집 실행"}
            </button>
          </div>
          {stats && (
            <p className="text-xs text-[#16A34A] mt-3">✓ 신규현장 {stats.sites}개 수집 · 영업타겟 {stats.selected}개 선별</p>
          )}
        </div>

        {error && <div className="rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">{error}</div>}

        {/* 타겟 목록 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-[#E5E7EB] flex items-center justify-between">
            <p className="text-sm font-bold text-[#111827]">영업 타겟 ({targets.length})</p>
            <span className="text-xs text-[#9CA3AF]">발송은 하이웍스로 1건씩 (자동 일괄발송 안 함)</span>
          </div>
          {targets.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm text-[#9CA3AF]">수집을 실행하면 영업 타겟이 표시됩니다.</div>
          ) : (
            <div className="divide-y divide-[#F3F4F6]">
              {targets.map((t) => (
                <div key={t.email + t.rank} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold px-2 py-0.5 rounded bg-[#ECFEFF] text-[#0891B2] border border-[#A5F3FC]">{t.grade} · {t.score}</span>
                        <p className="text-sm font-semibold text-[#111827] truncate">{t.project_name}</p>
                      </div>
                      <p className="text-xs text-[#6B7280] mt-0.5 truncate">{t.company} · {t.manager} · {t.email} · {t.branch}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button onClick={() => setOpen(open === t.rank ? null : t.rank)}
                        className="text-xs text-[#6B7280] hover:text-[#111827] px-2 py-1">초안</button>
                      {sent[t.email] ? (
                        <span className="text-xs font-semibold text-[#16A34A] px-2">✓ 발송됨</span>
                      ) : (
                        <button onClick={() => send(t)} disabled={sending === t.email}
                          className="px-3 py-1.5 rounded-lg bg-[#111827] text-white text-xs font-semibold hover:bg-[#374151] disabled:opacity-50">
                          {sending === t.email ? "발송 중..." : "하이웍스 발송"}
                        </button>
                      )}
                    </div>
                  </div>
                  {open === t.rank && (
                    <div className="mt-3 rounded-xl bg-[#F9FAFB] border border-[#E5E7EB] p-3">
                      <p className="text-xs font-semibold text-[#374151]">제목: {t.subject}</p>
                      <p className="text-xs text-[#9CA3AF] mt-1">사유: {(t.reasons || []).join(", ")}</p>
                      <pre className="text-xs text-[#374151] mt-2 whitespace-pre-wrap font-sans">{t.body}</pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
