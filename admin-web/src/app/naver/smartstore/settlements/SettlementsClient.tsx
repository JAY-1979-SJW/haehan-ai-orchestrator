"use client";
/** SettlementsClient — 정산 전용 (요약 카드 / 정산 내역 / 세금계산서 안내) */
import { useState, useEffect } from "react";
import {
  getSSSettlements,
  collectSSSettlements,
  getSettlementsSummary,
  type SSTableData,
} from "@/lib/assistant/api";

type Tab = "summary" | "history" | "tax";

interface SummaryData {
  ok: boolean;
  total_rows?: number;
  total_amount?: number;
  total_amount_str?: string;
  collected_at?: string;
  headers?: string[];
  error?: string;
}

const TAX_GUIDE = [
  { step: "1", label: "세금계산서 발행 기준", desc: "월별 정산 완료 후 익월 10일 이내 자동 발행" },
  { step: "2", label: "발행 대상",           desc: "사업자 등록 판매자 (개인 간이과세자 포함)" },
  { step: "3", label: "확인 경로",           desc: "셀러센터 > 정산관리 > 세금계산서 내역" },
  { step: "4", label: "수정 발행",           desc: "오류 발생 시 셀러센터 문의 (수정세금계산서 요청)" },
];

export default function SettlementsClient() {
  const [tab, setTab] = useState<Tab>("summary");

  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const [data, setData] = useState<SSTableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (tab === "summary" && !summary) loadSummary();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadSummary() {
    setSummaryLoading(true);
    try {
      const res = await getSettlementsSummary();
      setSummary(res);
    } catch {
      setSummary({ ok: false, error: "요약 정보를 불러올 수 없습니다." });
    } finally {
      setSummaryLoading(false);
    }
  }

  async function handleCollect() {
    setLoading(true);
    setError(null);
    try {
      setData(await collectSSSettlements(30));
      setSummary(null); // 수집 후 요약 갱신 유도
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleLoad() {
    setLoading(true);
    setError(null);
    try {
      setData(await getSSSettlements());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: "summary", label: "정산 요약" },
    { id: "history", label: "정산 내역" },
    { id: "tax",     label: "세금계산서" },
  ];

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        {/* 탭 바 */}
        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors whitespace-nowrap ${
                tab === t.id
                  ? "border-[#7C3AED] text-[#7C3AED] font-semibold"
                  : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 정산 요약 탭 ── */}
        {tab === "summary" && (
          <div className="space-y-4">
            {summaryLoading && (
              <p className="text-xs text-[#9CA3AF]">요약 정보 로드 중…</p>
            )}

            {summary?.ok && (
              <div className="grid grid-cols-2 gap-3">
                <div className="border border-[#DDD6FE] bg-[#F5F3FF] rounded-xl p-4">
                  <p className="text-xs text-[#7C3AED] font-semibold mb-1">총 정산 건수</p>
                  <p className="text-2xl font-black text-[#111827]">
                    {(summary.total_rows ?? 0).toLocaleString()}
                    <span className="text-sm font-normal text-[#6B7280] ml-1">건</span>
                  </p>
                </div>
                <div className="border border-[#DDD6FE] bg-[#F5F3FF] rounded-xl p-4">
                  <p className="text-xs text-[#7C3AED] font-semibold mb-1">합산 정산금액</p>
                  <p className="text-2xl font-black text-[#111827]">
                    {summary.total_amount_str ?? "–"}
                  </p>
                </div>
              </div>
            )}

            {summary?.ok === false && (
              <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-sm text-[#DC2626]">{summary.error}</p>
                <p className="text-xs text-[#9CA3AF] mt-1">[정산 내역] 탭에서 수집 후 다시 확인하세요.</p>
              </div>
            )}

            {/* 정산 주기 안내 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">정산 주기 안내</p>
              <div className="space-y-2">
                {[
                  { label: "정산 기준일",   value: "구매 확정일 기준 영업일 +2일" },
                  { label: "정산 주기",     value: "일별 정산 (주말·공휴일 제외)" },
                  { label: "입금 시간",     value: "익영업일 오전 중 판매자 계좌로 입금" },
                  { label: "수수료 공제",   value: "판매 수수료·PG 수수료·프로모션 비용 자동 공제" },
                  { label: "정산 조회",     value: "셀러센터 > 정산관리 > 정산 내역" },
                ].map((item) => (
                  <div key={item.label} className="flex gap-3 text-xs">
                    <span className="font-semibold text-[#6B7280] w-24 shrink-0">{item.label}</span>
                    <span className="text-[#374151]">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <button
                onClick={loadSummary}
                disabled={summaryLoading}
                className="text-xs px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-[#6B7280] hover:bg-[#F9FAFB] disabled:opacity-50 transition-colors"
              >
                요약 갱신
              </button>
              <a
                href="https://sell.smartstore.naver.com/#/settlement"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#7C3AED] text-[#7C3AED] hover:bg-[#F5F3FF] transition-colors"
              >
                셀러센터 정산 관리 →
              </a>
            </div>
          </div>
        )}

        {/* ── 정산 내역 탭 ── */}
        {tab === "history" && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={handleCollect}
                disabled={loading}
                className="px-4 py-2 bg-[#7C3AED] text-white text-sm rounded-lg hover:bg-[#6D28D9] disabled:opacity-50 transition-colors font-semibold"
              >
                {loading ? "수집 중…" : "수집"}
              </button>
              <button
                onClick={handleLoad}
                disabled={loading}
                className="px-4 py-2 border border-[#E5E7EB] text-sm rounded-lg hover:bg-[#F9FAFB] disabled:opacity-50 transition-colors"
              >
                조회
              </button>
              {data?.collected_at && (
                <span className="text-xs text-[#9CA3AF]">
                  수집: {data.collected_at}
                  {data.duration_ms !== undefined && ` (${data.duration_ms}ms)`}
                </span>
              )}
            </div>

            {error && (
              <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-sm text-[#DC2626]">{error}</p>
              </div>
            )}
            {data?.error && (
              <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-4">
                <p className="text-sm text-[#DC2626]">{data.error}</p>
                {data.hint && <p className="text-xs text-[#9CA3AF] mt-1">{data.hint}</p>}
              </div>
            )}

            {data?.ok && data.headers && data.rows && (
              <div className="overflow-x-auto border border-[#E5E7EB] rounded-xl">
                <table className="w-full text-xs">
                  <thead className="bg-[#F5F3FF] border-b border-[#E5E7EB]">
                    <tr>
                      {data.headers.map((h) => (
                        <th key={h} className="text-left px-3 py-2.5 text-[#6B7280] font-semibold whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row, i) => (
                      <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"}>
                        {row.map((cell, j) => (
                          <td key={j} className="px-3 py-2 text-[#374151] whitespace-nowrap">{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!data && !error && (
              <div className="border border-[#E5E7EB] rounded-xl p-8 text-center space-y-2">
                <p className="text-sm text-[#6B7280]">아직 수집된 데이터가 없습니다.</p>
                <button
                  onClick={handleCollect}
                  disabled={loading}
                  className="mt-2 px-4 py-2 bg-[#7C3AED] text-white text-xs rounded-lg hover:bg-[#6D28D9] disabled:opacity-50 transition-colors"
                >
                  수집 시작
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── 세금계산서 탭 ── */}
        {tab === "tax" && (
          <div className="space-y-4">
            <div className="border border-[#DDD6FE] bg-[#F5F3FF] rounded-xl p-4 space-y-1">
              <p className="text-sm font-semibold text-[#7C3AED]">전자세금계산서 자동 발행</p>
              <p className="text-xs text-[#6D28D9]">
                네이버 스마트스토어는 사업자 판매자에게 월별 세금계산서를 자동 발행합니다.
              </p>
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">세금계산서 처리 절차</p>
              <div className="space-y-3">
                {TAX_GUIDE.map((item) => (
                  <div key={item.step} className="flex gap-3">
                    <span className="text-xs font-bold text-[#7C3AED] bg-[#F5F3FF] border border-[#DDD6FE] rounded-full w-6 h-6 flex items-center justify-center shrink-0">
                      {item.step}
                    </span>
                    <div>
                      <p className="text-xs font-semibold text-[#111827]">{item.label}</p>
                      <p className="text-xs text-[#6B7280]">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-[#111827]">부가세 신고 참고 사항</p>
              <div className="space-y-1.5 text-xs text-[#6B7280]">
                <p>• 일반과세자: 1·7월 신고 (1기 1~6월, 2기 7~12월)</p>
                <p>• 간이과세자: 1월 연 1회 신고</p>
                <p>• 네이버 정산 내역서가 공급가액 증빙으로 사용 가능</p>
                <p>• 수수료는 네이버 발행 세금계산서로 매입세액 공제 가능</p>
              </div>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/settlement/tax"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#7C3AED] text-[#7C3AED] hover:bg-[#F5F3FF] transition-colors"
              >
                셀러센터 세금계산서 바로가기 →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
