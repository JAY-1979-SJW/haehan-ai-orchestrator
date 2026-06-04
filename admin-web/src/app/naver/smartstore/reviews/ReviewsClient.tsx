"use client";
/** ReviewsClient — 리뷰/문의 (고객 리뷰/고객 문의/자동응답 설정) — CDP 수집 연동 */
import { useState } from "react";
import {
  getSSReviews,
  collectSSReviews,
  type SSTableData,
} from "@/lib/assistant/api";

type Tab = "reviews" | "inquiries" | "autorespond";

const INQUIRY_TYPES = [
  { type: "배송 문의",  desc: "배송 예정일, 운송장 조회 등", sla: "12시간 내" },
  { type: "상품 문의",  desc: "스펙, 재질, 사용법 등",       sla: "24시간 내" },
  { type: "환불 문의",  desc: "교환/반품/취소 요청",         sla: "24시간 내" },
];

const AUTO_TEMPLATES = [
  { label: "5점 리뷰",       template: "소중한 리뷰 감사드립니다! 항상 최선을 다하겠습니다." },
  { label: "4점 리뷰",       template: "리뷰 감사드립니다. 더 나은 서비스를 위해 노력하겠습니다." },
  { label: "3점 이하 리뷰",  template: "불편을 드려 죄송합니다. 문의사항은 채팅으로 연락 부탁드립니다." },
];

export default function ReviewsClient() {
  const [tab, setTab] = useState<Tab>("reviews");
  const [data, setData] = useState<SSTableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const TABS: { id: Tab; label: string }[] = [
    { id: "reviews",     label: "고객 리뷰" },
    { id: "inquiries",   label: "고객 문의" },
    { id: "autorespond", label: "자동응답 설정" },
  ];

  async function handleCollect() {
    setLoading(true);
    setError(null);
    try {
      setData(await collectSSReviews(30));
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
      setData(await getSSReviews());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

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
                  ? "border-[#F97316] text-[#F97316] font-semibold"
                  : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 고객 리뷰 탭 ── */}
        {tab === "reviews" && (
          <div className="space-y-4">
            {/* 수집/조회 버튼 */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={handleCollect}
                disabled={loading}
                className="px-4 py-2 bg-[#1D4ED8] text-white text-sm rounded-lg hover:bg-[#1E40AF] disabled:opacity-50 transition-colors font-semibold"
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

            {/* 오류 표시 */}
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

            {/* 테이블 */}
            {data?.ok && data.headers && data.rows && (
              <div className="overflow-x-auto border border-[#E5E7EB] rounded-xl">
                <table className="w-full text-xs">
                  <thead className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
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

            {/* 미수집 안내 */}
            {!data && !error && (
              <div className="border border-[#E5E7EB] rounded-xl p-8 text-center space-y-2">
                <p className="text-sm text-[#6B7280]">아직 수집된 데이터가 없습니다.</p>
                <p className="text-xs text-[#9CA3AF]">[수집] 버튼을 눌러 셀러센터에서 데이터를 가져오세요.</p>
                <button
                  onClick={handleCollect}
                  disabled={loading}
                  className="mt-2 px-4 py-2 bg-[#1D4ED8] text-white text-xs rounded-lg hover:bg-[#1E40AF] disabled:opacity-50 transition-colors"
                >
                  수집 시작
                </button>
              </div>
            )}

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/reviews"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 리뷰 관리 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 고객 문의 탭 ── */}
        {tab === "inquiries" && (
          <div className="space-y-4">
            <div className="space-y-2">
              {INQUIRY_TYPES.map((item) => (
                <div key={item.type} className="border border-[#E5E7EB] rounded-xl p-4 bg-white flex items-start gap-4">
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-[#111827]">{item.type}</p>
                    <p className="text-xs text-[#6B7280] mt-0.5">{item.desc}</p>
                  </div>
                  <span className="text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-2 py-0.5 rounded font-semibold shrink-0">
                    {item.sla}
                  </span>
                </div>
              ))}
            </div>

            <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4">
              <p className="text-xs font-semibold text-[#C2410C] mb-1">응답 SLA</p>
              <p className="text-xs text-[#92400E]">
                네이버 셀러 평가 기준: <strong>24시간 내</strong> 미답변 시 응답률 하락. 응답률 90% 미만 시 노출 불이익 발생 가능.
              </p>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/inquiries"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 문의 관리 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 자동응답 설정 탭 ── */}
        {tab === "autorespond" && (
          <div className="space-y-4">
            <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-[#16A34A]">ReviewAutoResponder</p>
                <span className="text-xs bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-2 py-0.5 rounded">구현됨</span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">자동응답 모듈</span>
                  <span className="text-[#111827] font-mono">SmartStore.reviews.auto_responder</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">트리거 조건</span>
                  <span className="text-[#111827]">신규 리뷰 등록 후 1시간 이내 자동 응답</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">승인 상태</span>
                  <span className="text-[#111827]">조회 전용 (답변 발행은 승인 후 실행)</span>
                </div>
              </div>
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">응답 템플릿</p>
              <div className="space-y-2">
                {AUTO_TEMPLATES.map((tmpl) => (
                  <div key={tmpl.label} className="border border-[#E5E7EB] rounded-lg p-3 bg-[#F9FAFB]">
                    <p className="text-xs font-semibold text-[#374151] mb-1">{tmpl.label}</p>
                    <p className="text-xs text-[#6B7280] italic">&ldquo;{tmpl.template}&rdquo;</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
