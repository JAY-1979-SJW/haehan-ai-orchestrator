"use client";

import { useState, useCallback } from "react";

// ── 타입 ──────────────────────────────────────────────────────────────────────

interface Room {
  label: string;
  area_m2: number;
  area_net_m2: number;
  wall_thickness_mm: number | null;
  layer: string;
  centroid: [number, number];
  texts: string[];
  blocks: number;
  dims: number;
}

interface RoomsResult {
  project: string;
  drawing_no: string;
  discipline: string;
  room_count: number;
  total_area_m2: number;
  rooms: Room[];
}

interface ParseResult {
  status: string;
  rooms: number;
  named: number;
  area_m2: number;
  ai?: { summary: string; tokens_used: number };
}

const DISCIPLINES = ["건축", "구조", "소방기계", "소방전기", "전기", "통신", "기계설비"];

async function cadFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`/api/proxy/api/v1/cad${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// ── 컴포넌트 ──────────────────────────────────────────────────────────────────

export default function TakeoffPanel() {
  const [project, setProject]       = useState("서부청소년");
  const [discipline, setDiscipline] = useState("건축");
  const [drawingNo, setDrawingNo]   = useState("A-201");
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);

  const [status, setStatus]         = useState<Record<string, unknown> | null>(null);
  const [rooms, setRooms]           = useState<RoomsResult | null>(null);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);

  // ── 파싱 현황 ──
  const fetchStatus = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const data = await cadFetch(`/${project}/status?discipline=${discipline}`);
      setStatus(data);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, [project, discipline]);

  // ── 실 목록 ──
  const fetchRooms = useCallback(async () => {
    if (!drawingNo) { setError("도면번호를 입력하세요"); return; }
    setLoading(true); setError(null);
    try {
      const data = await cadFetch(`/${project}/rooms?discipline=${discipline}&drawing_no=${drawingNo}`);
      setRooms(data);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, [project, discipline, drawingNo]);

  // ── AI 분석 ──
  const runAnalyze = useCallback(async () => {
    if (!drawingNo) { setError("도면번호를 입력하세요"); return; }
    setLoading(true); setError(null);
    try {
      const data = await cadFetch(`/${project}/analyze`, {
        method: "POST",
        body: JSON.stringify({ drawing_no: drawingNo, discipline }),
      });
      setParseResult(data);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, [project, discipline, drawingNo]);

  return (
    <div className="flex flex-col gap-5">

      {/* ── 조건 입력 ── */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-5">
        <h2 className="text-[13px] font-bold text-[#0F172A] mb-4">물량산출 설정</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="text-[11px] text-[#6B7280] mb-1 block">프로젝트</label>
            <input
              className="w-full rounded-[8px] px-3 py-2 text-[12px] border border-[#D1D5DB] outline-none"
              value={project}
              onChange={(e) => setProject(e.target.value)}
              placeholder="서부청소년"
            />
          </div>
          <div>
            <label className="text-[11px] text-[#6B7280] mb-1 block">공종</label>
            <select
              className="w-full rounded-[8px] px-3 py-2 text-[12px] border border-[#D1D5DB] outline-none"
              value={discipline}
              onChange={(e) => setDiscipline(e.target.value)}
            >
              {DISCIPLINES.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[11px] text-[#6B7280] mb-1 block">도면번호</label>
            <input
              className="w-full rounded-[8px] px-3 py-2 text-[12px] border border-[#D1D5DB] outline-none"
              value={drawingNo}
              onChange={(e) => setDrawingNo(e.target.value)}
              placeholder="A-201"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mt-4">
          <button
            onClick={fetchStatus}
            disabled={loading}
            className="px-4 py-2 rounded-[8px] text-[12px] font-medium transition-colors disabled:opacity-40"
            style={{ background: "#F3F4F6", color: "#374151", border: "1px solid #E5E7EB" }}
          >
            📊 파싱 현황
          </button>
          <button
            onClick={fetchRooms}
            disabled={loading}
            className="px-4 py-2 rounded-[8px] text-[12px] font-medium transition-colors disabled:opacity-40"
            style={{ background: "#EFF6FF", color: "#1D4ED8", border: "1px solid #BFDBFE" }}
          >
            🏠 실 목록 조회
          </button>
          <button
            onClick={runAnalyze}
            disabled={loading}
            className="px-4 py-2 rounded-[8px] text-[12px] font-medium transition-colors disabled:opacity-40"
            style={{ background: "#F97316", color: "white" }}
          >
            🤖 AI 분석
          </button>
          {loading && <span className="text-[12px] text-[#9CA3AF] self-center">처리 중...</span>}
        </div>
      </div>

      {/* 오류 */}
      {error && (
        <div className="rounded-[8px] px-4 py-3 text-[12px]"
          style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#991B1B" }}>
          {error}
          <button className="ml-3 underline text-[11px]" onClick={() => setError(null)}>닫기</button>
        </div>
      )}

      {/* ── 파싱 현황 ── */}
      {status && (
        <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-5">
          <h3 className="text-[12px] font-bold text-[#0F172A] mb-3">📊 파싱 현황 — {(status as any).project} / {(status as any).discipline}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "전체 캐시", value: (status as any).cache_count },
              { label: "파싱 완료", value: (status as any).parsed, color: "#22c55e" },
              { label: "실패", value: (status as any).failed, color: "#EF4444" },
              { label: "미처리", value: (status as any).pending, color: "#F97316" },
            ].map(({ label, value, color }) => (
              <div key={label} className="rounded-[8px] p-3 text-center"
                style={{ background: "#F9FAFB", border: "1px solid #F3F4F6" }}>
                <div className="text-[20px] font-bold" style={{ color: color ?? "#0F172A" }}>{value ?? "-"}</div>
                <div className="text-[11px] text-[#9CA3AF] mt-0.5">{label}</div>
              </div>
            ))}
          </div>
          {(status as any).updated_at && (
            <p className="text-[10px] text-[#9CA3AF] mt-2">갱신: {new Date((status as any).updated_at).toLocaleString("ko-KR")}</p>
          )}
        </div>
      )}

      {/* ── AI 분석 결과 ── */}
      {parseResult && (
        <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-5"
          style={{ borderTop: "3px solid #F97316" }}>
          <h3 className="text-[12px] font-bold text-[#0F172A] mb-3">🤖 AI 분석 — {drawingNo}</h3>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="rounded-[8px] p-3 text-center" style={{ background: "#F9FAFB" }}>
              <div className="text-[20px] font-bold text-[#0F172A]">{parseResult.rooms}</div>
              <div className="text-[11px] text-[#9CA3AF]">전체 실</div>
            </div>
            <div className="rounded-[8px] p-3 text-center" style={{ background: "#F9FAFB" }}>
              <div className="text-[20px] font-bold text-[#22c55e]">{parseResult.named}</div>
              <div className="text-[11px] text-[#9CA3AF]">실명 인식</div>
            </div>
            <div className="rounded-[8px] p-3 text-center" style={{ background: "#F9FAFB" }}>
              <div className="text-[20px] font-bold text-[#1D4ED8]">{parseResult.area_m2?.toFixed(1)}</div>
              <div className="text-[11px] text-[#9CA3AF]">총면적 m²</div>
            </div>
          </div>
          {parseResult.ai?.summary && (
            <div className="rounded-[8px] p-4 text-[12px] leading-relaxed"
              style={{ background: "#FFFBEB", border: "1px solid #FDE68A", color: "#92400E" }}>
              {parseResult.ai.summary}
              <span className="ml-2 text-[10px] text-[#9CA3AF]">({parseResult.ai.tokens_used} tokens)</span>
            </div>
          )}
        </div>
      )}

      {/* ── 실 목록 ── */}
      {rooms && (
        <div className="bg-white border border-[#E5E7EB] rounded-[12px] overflow-hidden">
          <div className="px-5 py-3 border-b border-[#F3F4F6] flex items-center gap-3">
            <h3 className="text-[12px] font-bold text-[#0F172A]">🏠 실 목록 — {rooms.drawing_no}</h3>
            <span className="text-[11px] text-[#9CA3AF]">{rooms.room_count}개 / 합계 {rooms.total_area_m2.toFixed(1)}m²</span>
          </div>
          <div className="overflow-auto max-h-[400px]">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="bg-[#F9FAFB] border-b border-[#F3F4F6]">
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-[#6B7280]">실명</th>
                  <th className="text-right px-4 py-2 text-[11px] font-semibold text-[#6B7280]">면적(m²)</th>
                  <th className="text-right px-4 py-2 text-[11px] font-semibold text-[#6B7280]">순면적(m²)</th>
                  <th className="text-right px-4 py-2 text-[11px] font-semibold text-[#6B7280]">벽두께</th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-[#6B7280]">레이어</th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-[#6B7280]">텍스트</th>
                </tr>
              </thead>
              <tbody>
                {rooms.rooms.map((r, i) => (
                  <tr key={i} className="border-b border-[#F9FAFB] hover:bg-[#FFFBEB] transition-colors">
                    <td className="px-4 py-2 font-medium text-[#0F172A]">
                      {r.label || <span className="text-[#9CA3AF]">(무명)</span>}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">{r.area_m2.toFixed(2)}</td>
                    <td className="px-4 py-2 text-right font-mono text-[#6B7280]">{r.area_net_m2.toFixed(2)}</td>
                    <td className="px-4 py-2 text-right text-[#6B7280]">
                      {r.wall_thickness_mm ? `${r.wall_thickness_mm}mm` : "-"}
                    </td>
                    <td className="px-4 py-2">
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-mono"
                        style={{ background: "#F3F4F6", color: "#6B7280" }}>
                        {r.layer}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-[#9CA3AF] text-[11px] truncate max-w-[120px]">
                      {r.texts.slice(0, 3).join(", ") || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
