"use client";

import { useCallback, useEffect, useState } from "react";

interface Site { id: string; name: string; url: string; note?: string; added_at?: string }
interface Opportunity { idea: string; why?: string }
interface Topic { name: string; share?: string }
interface Report {
  ok: boolean; error?: string; analyzed_count?: number;
  summary?: string; trends?: string[]; opportunities?: Opportunity[];
  topics?: Topic[]; actions?: string[]; source_method?: string;
}

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const t = window.localStorage.getItem("haehan_ai_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}
const J = { "Content-Type": "application/json" };

export function CommunityClient() {
  const [sites, setSites] = useState<Site[]>([]);
  const [newUrl, setNewUrl] = useState("");
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [analyzingUrl, setAnalyzingUrl] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [reportFor, setReportFor] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [autoReports, setAutoReports] = useState<{ generated_at?: string; reason?: string; site_count?: number; ok_count?: number; reports?: (Report & { site?: string })[] }[]>([]);
  const [scheduleState, setScheduleState] = useState<{ last_run?: string | null } | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const [notify, setNotify] = useState<{ enabled?: boolean; token_set?: boolean; token_masked?: string; chat_id?: string } | null>(null);
  const [tgToken, setTgToken] = useState("");
  const [notifyMsg, setNotifyMsg] = useState<string>("");

  const loadSites = useCallback(async () => {
    try {
      const r = await fetch("/api/proxy/api/v1/community/sites", { headers: authHeader() });
      const d = await r.json();
      setSites(d.sites || []);
    } catch (e) { setError(String(e)); }
  }, []);

  const loadReports = useCallback(async () => {
    try {
      const r = await fetch("/api/proxy/api/v1/community/reports?limit=5", { headers: authHeader() });
      const d = await r.json();
      setAutoReports(d.reports || []);
      setScheduleState(d.state || null);
    } catch { /* ignore */ }
  }, []);

  const loadNotify = useCallback(async () => {
    try {
      const r = await fetch("/api/proxy/api/v1/community/notify/config", { headers: authHeader() });
      setNotify(await r.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadSites(); loadReports(); loadNotify(); }, [loadSites, loadReports, loadNotify]);

  async function setupTelegram() {
    if (!tgToken.trim()) return;
    setNotifyMsg("연결 중…");
    try {
      const r = await fetch("/api/proxy/api/v1/community/notify/telegram", {
        method: "POST", headers: { ...J, ...authHeader() }, body: JSON.stringify({ token: tgToken.trim() }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "설정 실패");
      setTgToken("");
      setNotifyMsg(d.detected ? `✅ 연결됨 (chat_id 감지: ${d.chat_id})` : "⚠️ 토큰 저장됨 — 텔레그램에서 봇에게 메시지를 한 번 보낸 뒤 다시 [연결]을 누르세요");
      await loadNotify();
    } catch (e) { setNotifyMsg("오류: " + String(e)); }
  }
  async function testNotify() {
    setNotifyMsg("테스트 발송 중…");
    try {
      const r = await fetch("/api/proxy/api/v1/community/notify/test", { method: "POST", headers: authHeader() });
      const d = await r.json();
      setNotifyMsg(r.ok ? "✅ 테스트 발송 성공 — 텔레그램을 확인하세요" : "발송 실패: " + (d.detail || ""));
    } catch (e) { setNotifyMsg("오류: " + String(e)); }
  }
  async function toggleNotify(enabled: boolean) {
    await fetch("/api/proxy/api/v1/community/notify/toggle", {
      method: "POST", headers: { ...J, ...authHeader() }, body: JSON.stringify({ enabled }),
    });
    await loadNotify();
  }

  async function runAll() {
    setRunningAll(true); setError(null);
    try {
      const r = await fetch("/api/proxy/api/v1/community/run-now", { method: "POST", headers: authHeader() });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "실행 실패");
      await loadReports();
    } catch (e) { setError(String(e)); } finally { setRunningAll(false); }
  }

  async function addSite() {
    if (!newUrl.trim()) return;
    setAdding(true); setError(null);
    try {
      const r = await fetch("/api/proxy/api/v1/community/sites", {
        method: "POST", headers: { ...J, ...authHeader() },
        body: JSON.stringify({ url: newUrl.trim(), name: newName.trim() }),
      });
      const d = await r.json();
      if (!r.ok || d.ok === false) throw new Error(d.detail || "등록 실패");
      setNewUrl(""); setNewName(""); await loadSites();
    } catch (e) { setError(String(e)); } finally { setAdding(false); }
  }

  async function removeSite(id: string) {
    await fetch(`/api/proxy/api/v1/community/sites/${id}`, { method: "DELETE", headers: authHeader() });
    await loadSites();
  }

  async function analyze(url: string, label: string) {
    setAnalyzingUrl(url); setError(null); setReport(null); setReportFor(label);
    try {
      const r = await fetch("/api/proxy/api/v1/community/analyze", {
        method: "POST", headers: { ...J, ...authHeader() },
        body: JSON.stringify({ url, max_posts: 40 }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "분석 실패");
      setReport(d);
    } catch (e) { setError(String(e)); } finally { setAnalyzingUrl(null); }
  }

  return (
    <div className="space-y-4 max-w-5xl">
      {/* 사이트 등록 */}
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
              <button onClick={() => analyze(s.url, s.name)} disabled={analyzingUrl === s.url}
                className="px-3 py-1.5 rounded-lg bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] text-xs font-semibold hover:bg-[#FED7AA] disabled:opacity-40 shrink-0">
                {analyzingUrl === s.url ? "분석 중…" : "🔍 수집·분석"}
              </button>
              <button onClick={() => removeSite(s.id)}
                className="text-[#9CA3AF] hover:text-[#DC2626] text-sm px-1 shrink-0">✕</button>
            </div>
          ))}
        </div>
      </div>

      {/* 알림(텔레그램) 설정 */}
      <div className="border border-[#E5E7EB] rounded-2xl bg-white p-4 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-bold text-[#111827]">📨 텔레그램 알림</p>
          {notify?.token_set && notify?.chat_id && (
            <label className="flex items-center gap-1.5 text-xs text-[#6B7280] cursor-pointer">
              <input type="checkbox" checked={!!notify.enabled} onChange={(e) => toggleNotify(e.target.checked)} />
              자동 발송 {notify.enabled ? "켜짐" : "꺼짐"}
            </label>
          )}
        </div>
        {notify?.token_set && notify?.chat_id ? (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-[#16A34A]">✅ 연결됨 (chat {notify.chat_id})</span>
            <button onClick={testNotify} className="px-2.5 py-1 rounded-lg border border-[#E5E7EB] text-xs text-[#6B7280] hover:bg-[#F9FAFB]">테스트 발송</button>
            <button onClick={() => { setTgToken(""); setNotify({ ...notify, token_set: false }); }} className="text-xs text-[#9CA3AF] hover:text-[#DC2626]">토큰 변경</button>
          </div>
        ) : (
          <div className="space-y-1.5">
            <p className="text-[11px] text-[#9CA3AF]">① 텔레그램 @BotFather 에서 봇 생성 → 토큰 복사 ② 만든 봇에게 아무 메시지 전송 ③ 아래에 토큰 붙여넣고 [연결]</p>
            <div className="flex gap-2">
              <input value={tgToken} onChange={(e) => setTgToken(e.target.value)} placeholder="봇 토큰 (예: 123456:ABC-...)"
                className="flex-1 border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#F97316]" />
              <button onClick={setupTelegram} disabled={!tgToken.trim()}
                className="px-4 py-2 rounded-xl bg-[#229ED9] text-white text-sm font-semibold hover:bg-[#1c8ec2] disabled:opacity-40">연결</button>
            </div>
          </div>
        )}
        {notifyMsg && <p className="text-xs text-[#6B7280]">{notifyMsg}</p>}
      </div>

      {/* 자율 분석 리포트 (주간 자동 + 수동 실행) */}
      <div className="border border-[#E5E7EB] rounded-2xl bg-white p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <p className="text-sm font-bold text-[#111827]">자율 분석 리포트</p>
            <p className="text-[11px] text-[#9CA3AF]">
              등록 사이트를 주기(주 1회)마다 자동 수집·분석합니다.
              {scheduleState?.last_run ? ` 최근 실행: ${scheduleState.last_run}` : " 아직 실행 기록 없음"}
            </p>
          </div>
          <button onClick={runAll} disabled={runningAll || sites.length === 0}
            className="px-3 py-1.5 rounded-lg bg-[#7C3AED] text-white text-xs font-semibold hover:bg-[#6D28D9] disabled:opacity-40">
            {runningAll ? "전체 분석 중…" : "▶ 지금 전체 실행"}
          </button>
        </div>
        {autoReports.length === 0 && <p className="text-sm text-[#9CA3AF]">저장된 리포트가 없습니다. 사이트를 등록하고 실행하세요.</p>}
        {autoReports.map((batch, bi) => (
          <div key={bi} className="border border-[#F3F4F6] rounded-xl p-3 bg-[#FAFAFA]">
            <p className="text-xs text-[#6B7280] mb-1.5">{batch.generated_at} · {batch.reason === "scheduled" ? "자동" : "수동"} · {batch.ok_count}/{batch.site_count} 성공</p>
            <div className="space-y-1.5">
              {(batch.reports || []).map((r, ri) => (
                <div key={ri} className="text-sm">
                  <span className="font-semibold text-[#111827]">{r.site}</span>
                  {r.summary ? <span className="text-[#374151]"> — {r.summary}</span> : <span className="text-[#DC2626]"> — {r.error || "실패"}</span>}
                  {!!r.opportunities?.length && (
                    <span className="text-xs text-[#16A34A]"> · 💰 {r.opportunities[0]?.idea}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {error && <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3 text-sm text-[#DC2626]">오류: {error}</div>}
      {analyzingUrl && <p className="text-sm text-[#6B7280]">게시글 수집 + AI 분석 중… (10~30초)</p>}

      {/* 리포트 */}
      {report && report.ok && (
        <div className="border border-[#E5E7EB] rounded-2xl bg-white p-5 space-y-4">
          <div>
            <p className="text-xs text-[#9CA3AF]">{reportFor} · {report.analyzed_count}건 분석 · {report.source_method}</p>
            <p className="text-base font-bold text-[#111827] mt-1">{report.summary}</p>
          </div>

          {!!report.trends?.length && (
            <div>
              <p className="text-sm font-bold text-[#C2410C] mb-1">🔥 지금 흐름</p>
              <ul className="list-disc pl-5 space-y-0.5 text-sm text-[#374151]">
                {report.trends.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            </div>
          )}
          {!!report.opportunities?.length && (
            <div>
              <p className="text-sm font-bold text-[#16A34A] mb-1">💰 수익 기회</p>
              <div className="space-y-2">
                {report.opportunities.map((o, i) => (
                  <div key={i} className="bg-[#F0FDF4] border border-[#BBF7D0] rounded-lg p-2.5">
                    <p className="text-sm font-semibold text-[#166534]">{o.idea}</p>
                    {o.why && <p className="text-xs text-[#15803D] mt-0.5">{o.why}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {!!report.topics?.length && (
            <div>
              <p className="text-sm font-bold text-[#1D4ED8] mb-1">📊 토픽 분포</p>
              <div className="flex flex-wrap gap-1.5">
                {report.topics.map((t, i) => (
                  <span key={i} className="text-xs bg-[#EFF6FF] border border-[#BFDBFE] text-[#1D4ED8] px-2 py-1 rounded-full">
                    {t.name}{t.share ? ` · ${t.share}` : ""}
                  </span>
                ))}
              </div>
            </div>
          )}
          {!!report.actions?.length && (
            <div>
              <p className="text-sm font-bold text-[#7C3AED] mb-1">🎯 액션 제안</p>
              <ul className="list-disc pl-5 space-y-0.5 text-sm text-[#374151]">
                {report.actions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
      {report && report.ok === false && (
        <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3 text-sm text-[#DC2626]">분석 실패: {report.error}</div>
      )}
    </div>
  );
}
