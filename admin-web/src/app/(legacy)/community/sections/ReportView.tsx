"use client";
/** 커뮤니티 레이더 — 분석 리포트 렌더 (바로분석/사이트분석 공용) */
import { type Report } from "../communityShared";

export function ReportView({ report, reportFor }: { report: Report; reportFor: string }) {
  if (report.ok === false) {
    return (
      <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3 text-sm text-[#DC2626]">분석 실패: {report.error}</div>
    );
  }
  return (
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
  );
}
