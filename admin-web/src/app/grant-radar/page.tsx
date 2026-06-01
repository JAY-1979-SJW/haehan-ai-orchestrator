"use client";
import { useState, useCallback, useEffect } from "react";
import { PageShell } from "@/components/ui/PageShell";

const API = "/api/proxy/api/v1/grant-radar";

interface GrantItem {
  title: string;
  url: string;
  portal: string;
  portal_name: string;
  deadline: string | null;
  dday: string | null;
  manager: string | null;
  score: number;
  matched: string[];
  summary?: string;
}

interface Report {
  ok: boolean;
  generated_at?: string;
  profile?: string;
  scanned_at?: string;
  total?: number;
  relevant?: number;
  items?: GrantItem[];
  message?: string;
}

function ddayColor(dday: string | null): string {
  if (!dday) return "#9CA3AF";
  if (dday === "종료") return "#9CA3AF";
  const n = parseInt(dday.replace("D-", ""), 10);
  if (!isNaN(n) && n <= 7) return "#DC2626";
  if (!isNaN(n) && n <= 14) return "#F97316";
  return "#16A34A";
}

export default function GrantRadarPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [onlyRelevant, setOnlyRelevant] = useState(true);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/report`, { cache: "no-store" });
      const data: Report = await r.json();
      setReport(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "보고서 로드 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  const runScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    try {
      const r = await fetch(`${API}/scan`, { method: "POST" });
      const res = await r.json();
      if (!res.ok) {
        setError(res.reason === "already_running" ? "이미 스캔 중입니다." : `스캔 실패 (${res.reason ?? "오류"})`);
      } else {
        await loadReport();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "스캔 실행 실패");
    } finally {
      setScanning(false);
    }
  }, [loadReport]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const items = (report?.items ?? []).filter((it) => (onlyRelevant ? it.score > 0 : true));

  return (
    <PageShell title="정부 지원사업 레이더" description="소방·CAD 물량산출·AI 프로필 기준 적합도 자동 분석">
      <div style={{ padding: "0 4px" }}>
        {/* 컨트롤 바 */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <button
            onClick={runScan}
            disabled={scanning}
            style={{
              padding: "8px 16px", borderRadius: 10, border: "none",
              background: scanning ? "#9CA3AF" : "#F97316", color: "#fff",
              fontWeight: 600, fontSize: 14, cursor: scanning ? "default" : "pointer",
            }}
          >
            {scanning ? "스캔 중… (별도 브라우저)" : "🔄 스캔 새로고침"}
          </button>
          <label style={{ fontSize: 13, color: "#374151", display: "flex", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={onlyRelevant} onChange={(e) => setOnlyRelevant(e.target.checked)} />
            적합 사업만 표시
          </label>
          {report?.generated_at && (
            <span style={{ fontSize: 12, color: "#6B7280" }}>
              생성 {report.generated_at.slice(0, 16).replace("T", " ")} · 적합 {report.relevant ?? 0}/{report.total ?? 0}
            </span>
          )}
        </div>

        {error && (
          <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#DC2626", padding: "10px 14px", borderRadius: 10, marginBottom: 12, fontSize: 13 }}>
            {error}
          </div>
        )}

        {loading && <div style={{ color: "#6B7280", fontSize: 14 }}>불러오는 중…</div>}

        {!loading && report && !report.ok && (
          <div style={{ color: "#6B7280", fontSize: 14, padding: "24px 0" }}>
            {report.message ?? "아직 스캔 전입니다. ‘스캔 새로고침’을 눌러 시작하세요."}
          </div>
        )}

        {!loading && items.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "#6B7280", borderBottom: "2px solid #E5E7EB" }}>
                  <th style={{ padding: "8px 10px" }}>적합도</th>
                  <th style={{ padding: "8px 10px" }}>마감</th>
                  <th style={{ padding: "8px 10px" }}>사업</th>
                  <th style={{ padding: "8px 10px" }}>담당자</th>
                  <th style={{ padding: "8px 10px" }}>키워드</th>
                  <th style={{ padding: "8px 10px" }}>포털</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid #F3F4F6" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: it.score >= 4 ? "#DC2626" : "#374151" }}>{it.score}</td>
                    <td style={{ padding: "8px 10px", fontWeight: 600, color: ddayColor(it.dday) }}>
                      {it.dday ?? it.deadline ?? "-"}
                    </td>
                    <td style={{ padding: "8px 10px", maxWidth: 420 }}>
                      <a href={it.url} target="_blank" rel="noopener noreferrer" style={{ color: "#1D4ED8", textDecoration: "none" }}>
                        {it.title}
                      </a>
                      {it.summary && <div style={{ color: "#6B7280", fontSize: 12, marginTop: 2 }}>{it.summary}</div>}
                    </td>
                    <td style={{ padding: "8px 10px" }}>{it.manager ?? "-"}</td>
                    <td style={{ padding: "8px 10px", color: "#F97316", fontSize: 12 }}>{it.matched.join(", ") || "-"}</td>
                    <td style={{ padding: "8px 10px", color: "#6B7280", fontSize: 12 }}>{it.portal_name || it.portal}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && report?.ok && items.length === 0 && (
          <div style={{ color: "#6B7280", fontSize: 14, padding: "24px 0" }}>표시할 사업이 없습니다.</div>
        )}
      </div>
    </PageShell>
  );
}
