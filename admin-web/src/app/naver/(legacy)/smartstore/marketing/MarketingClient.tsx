"use client";
/** MarketingClient — 마케팅/혜택 (쿠폰·할인/프로모션/SEO 최적화) — CDP 수집 연동 */
import { useState } from "react";
import {
  getSSMarketing,
  collectSSMarketing,
  type SSTableData,
} from "@/lib/assistant/api";

type Tab = "coupons" | "promotions" | "seo";

import { COUPON_TYPES, SEO_TIPS } from "./marketingData";
export default function MarketingClient() {
  const [tab, setTab] = useState<Tab>("coupons");
  const [data, setData] = useState<SSTableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const TABS: { id: Tab; label: string }[] = [
    { id: "coupons",    label: "쿠폰/할인" },
    { id: "promotions", label: "프로모션" },
    { id: "seo",        label: "SEO 최적화" },
  ];

  async function handleCollect() {
    setLoading(true);
    setError(null);
    try {
      setData(await collectSSMarketing());
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
      setData(await getSSMarketing());
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

        {/* ── 쿠폰/할인 탭 ── */}
        {tab === "coupons" && (
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

            {/* 수집 결과 테이블 */}
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

            {/* 미수집 — 정적 안내 표시 */}
            {(!data || (!data.ok && !data.error)) && !error && (
              <div className="space-y-3">
                {COUPON_TYPES.map((coupon) => (
                  <div key={coupon.label} className={`border rounded-xl p-4 ${coupon.badge}`}>
                    <p className="text-sm font-semibold mb-1">{coupon.label}</p>
                    <p className="text-xs opacity-80">{coupon.desc}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-[#6B7280]">쿠폰 발급 주의사항</p>
              <ul className="space-y-1">
                {[
                  "최소 할인율 3%, 최소 금액 할인 100원 이상",
                  "쿠폰 유효기간 최대 90일",
                  "발급 수량 제한 또는 무제한 선택 가능",
                  "발급 후 취소 불가 — 신중히 설정",
                ].map((note, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#374151]">
                    <span className="text-[#F97316] shrink-0">·</span>
                    {note}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/marketing/coupon"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 쿠폰 관리 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 프로모션 탭 ── */}
        {tab === "promotions" && (
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
                <span className="text-xs text-[#9CA3AF]">수집: {data.collected_at}</span>
              )}
            </div>

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

            {!data && !error && (
              <div className="border border-[#E5E7EB] rounded-xl p-8 text-center space-y-2">
                <p className="text-sm text-[#6B7280]">아직 수집된 데이터가 없습니다.</p>
                <p className="text-xs text-[#9CA3AF]">[수집] 버튼을 눌러 셀러센터에서 데이터를 가져오세요.</p>
              </div>
            )}

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-[#6B7280]">프로모션 참여 방법</p>
              <ol className="space-y-1.5">
                {[
                  "셀러센터 > 혜택/마케팅 > 프로모션 관리 접속",
                  "진행 중인 프로모션 목록에서 참여 가능 항목 확인",
                  "조건 확인 후 참여 신청 (일부 프로모션은 초대 필요)",
                ].map((step, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#374151]">
                    <span className="text-[#F97316] font-bold shrink-0">{i + 1}.</span>
                    {step}
                  </li>
                ))}
              </ol>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/marketing/promotion"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 프로모션 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── SEO 최적화 탭 ── */}
        {tab === "seo" && (
          <div className="space-y-4">
            <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-[#16A34A]">SEOOptimizer</p>
                <span className="text-xs bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-2 py-0.5 rounded">구현됨</span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">최적화 모듈</span>
                  <span className="text-[#111827] font-mono">SmartStore.seo_optimizer</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">주요 기능</span>
                  <span className="text-[#111827]">상품명 키워드 분석, 태그 추천, 카테고리 최적화</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">승인 상태</span>
                  <span className="text-[#111827]">조회·분석은 자유롭게, 변경은 승인 후 실행</span>
                </div>
              </div>
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">상품명 최적화 팁</p>
              <ul className="space-y-2">
                {SEO_TIPS.map((tip, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#374151]">
                    <span className="text-[#F97316] font-bold shrink-0">{i + 1}.</span>
                    {tip}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/store/info"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 스토어 설정 바로가기 →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
