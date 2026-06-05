"use client";
/** 카페 탭 — 내 카페 목록 (수집 + 기간 선택) */
import { useState, useEffect, useCallback } from "react";
import { getMyCafes, type MyCafe } from "@/lib/assistant/api";
import { apiPost } from "../cafeShared";

export function MyCafesTab() {
  const [cafes, setCafes] = useState<MyCafe[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [collectingCafes, setCollectingCafes] = useState(false);
  const [collectingUrl, setCollectingUrl] = useState<string | null>(null);
  const [collectMsg, setCollectMsg] = useState<string | null>(null);
  const [collectDays, setCollectDays] = useState(90); // 수집 기간(일). 3650=전체

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { const r = await getMyCafes(); setCafes(r.cafes); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCollectMyCafes = async () => {
    setCollectingCafes(true); setCollectMsg(null); setError(null);
    try {
      const d = await apiPost("/api/v1/naver-cafe/collect-my-cafes", {});
      if (d.ok) { setCafes(d.cafes || []); setCollectMsg(`내 카페 ${d.count}개 수집 완료`); }
      else setError(d.detail || d.error || "수집 실패");
    } catch (e) { setError(e instanceof Error ? e.message : "수집 실패"); }
    finally { setCollectingCafes(false); }
  };

  const handleCollectArticles = async (cafe: MyCafe) => {
    const url = cafe.href || `https://cafe.naver.com/${cafe.cafe_id}`;
    setCollectingUrl(cafe.cafe_id); setCollectMsg(`${cafe.cafe_name || cafe.cafe_id} 수집 중… (1~2분)`);
    try {
      const d = await apiPost("/api/v1/naver-cafe/collect", { cafe_url: url, days: collectDays });
      if (d.ok) setCollectMsg(`${cafe.cafe_name || cafe.cafe_id} — 게시글 ${d.collected}건 수집 완료`);
      else setCollectMsg(`수집 실패: ${d.detail || d.error || ""}`);
    } catch (e) { setCollectMsg(`수집 실패: ${e instanceof Error ? e.message : ""}`); }
    finally { setCollectingUrl(null); }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={handleCollectMyCafes} disabled={collectingCafes}
          className="px-3 py-1.5 bg-[#03C75A] text-white text-xs rounded-lg font-semibold disabled:opacity-50">
          {collectingCafes ? "수집 중…" : "📥 내 카페 수집"}
        </button>
        <button onClick={load} disabled={loading}
          className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
          {loading ? "불러오는 중…" : "새로고침"}
        </button>
        <div className="flex items-center gap-1.5 ml-auto">
          <span className="text-[11px] text-[#6B7280]">수집 기간</span>
          <select value={collectDays} onChange={(e) => setCollectDays(Number(e.target.value))}
            className="border border-[#E5E7EB] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-[#1D4ED8]">
            <option value={7}>최근 1주</option>
            <option value={30}>최근 1개월</option>
            <option value={90}>최근 3개월</option>
            <option value={180}>최근 6개월</option>
            <option value={365}>최근 1년</option>
            <option value={3650}>전체 기간</option>
          </select>
        </div>
      </div>
      <p className="text-[11px] text-[#9CA3AF]">[내 카페 수집]으로 가입 카페를 가져온 뒤, 각 카페의 [게시글 수집]을 누르세요. 수집 기간을 먼저 고르세요(게시판 구분 없이 전체글 수집). (네이버 로그인 필요)</p>
      {collectMsg && <p className="text-xs text-[#16A34A]">{collectMsg}</p>}
      {error && <p className="text-xs text-[#DC2626]">오류: {error}</p>}
      <div className="divide-y divide-[#E5E7EB]">
        {cafes.map((c, i) => (
          <div key={c.cafe_id} className="flex items-center gap-3 py-2">
            <span className="text-xs text-[#9CA3AF] w-6 text-right">{i + 1}</span>
            <a href={c.href} target="_blank" rel="noopener noreferrer"
              className="flex-1 text-sm text-[#1D4ED8] hover:underline font-medium truncate">
              {c.cafe_name || c.cafe_id}
            </a>
            {c.member_count > 0 && <span className="text-xs text-[#6B7280]">{c.member_count.toLocaleString()}명</span>}
            <button onClick={() => handleCollectArticles(c)} disabled={collectingUrl === c.cafe_id}
              className="px-2.5 py-1 rounded-lg border border-[#03C75A] text-[#03C75A] text-[11px] font-semibold hover:bg-[#F0FDF4] disabled:opacity-40 shrink-0">
              {collectingUrl === c.cafe_id ? "수집 중…" : "게시글 수집"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
