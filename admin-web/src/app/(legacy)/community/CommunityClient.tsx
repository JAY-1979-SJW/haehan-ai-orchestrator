"use client";
/** /community — 커뮤니티 레이더 (섹션별 모듈 셸)
 *
 * 섹션은 독립 모듈(sections/*). 공유되는 analyze()·report·sites 만 셸이 보유하고
 * 나머지(텔레그램·자율리포트·등록폼)는 각 섹션이 자체 state 로 관리.
 * 섹션 추가/수정은 해당 섹션 파일만 건드리면 됨.
 */
import { useCallback, useEffect, useState } from "react";
import { type Site, type Report, authHeader, J } from "./communityShared";
import { InstantAnalyze } from "./sections/InstantAnalyze";
import { MonitoredSites } from "./sections/MonitoredSites";
import { TelegramNotify } from "./sections/TelegramNotify";
import { AutoReports } from "./sections/AutoReports";
import { ReportView } from "./sections/ReportView";

export function CommunityClient() {
  const [sites, setSites] = useState<Site[]>([]);
  const [analyzingUrl, setAnalyzingUrl] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [reportFor, setReportFor] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const loadSites = useCallback(async () => {
    try {
      const r = await fetch("/api/proxy/api/v1/community/sites", { headers: authHeader() });
      const d = await r.json();
      setSites(d.sites || []);
    } catch (e) { setError(String(e)); }
  }, []);

  useEffect(() => { loadSites(); }, [loadSites]);

  const analyze = useCallback(async (url: string, label: string) => {
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
  }, []);

  return (
    <div className="space-y-4 max-w-5xl">
      <InstantAnalyze onAnalyze={analyze} analyzingUrl={analyzingUrl} />
      <MonitoredSites sites={sites} analyzingUrl={analyzingUrl} onAnalyze={analyze} onChanged={loadSites} onError={setError} />
      <TelegramNotify />
      <AutoReports siteCount={sites.length} onError={setError} />

      {error && <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3 text-sm text-[#DC2626]">오류: {error}</div>}
      {analyzingUrl && <p className="text-sm text-[#6B7280]">게시글 수집 + AI 분석 중… (10~30초)</p>}
      {report && <ReportView report={report} reportFor={reportFor} />}
    </div>
  );
}
