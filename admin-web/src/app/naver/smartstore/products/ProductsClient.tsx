"use client";
/** ProductsClient — 상품 관리 (목록/등록/일괄 등록) — CDP 수집 연동 */
import { useState } from "react";
import {
  getSSProducts,
  collectSSProducts,
  type SSTableData,
} from "@/lib/assistant/api";

type Tab = "list" | "register" | "bulk";

const REGISTER_STEPS = [
  { step: 1, title: "카테고리 선택", desc: "정확한 카테고리 선택 (판매 수수료 결정)", required: true },
  { step: 2, title: "기본 정보",     desc: "상품명(최대 100자), 판매가(최소 10원), 재고 수량", required: true },
  { step: 3, title: "이미지 등록",   desc: "대표이미지 필수(최대 10MB), 추가이미지 선택", required: true },
  { step: 4, title: "상세 설명",     desc: "스마트에디터 또는 HTML 직접 작성", required: false },
  { step: 5, title: "저장 및 노출",  desc: "임시저장 → 최종 저장 → 노출 설정 확인", required: true },
];

export default function ProductsClient() {
  const [tab, setTab] = useState<Tab>("list");
  const [data, setData] = useState<SSTableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const TABS: { id: Tab; label: string }[] = [
    { id: "list",     label: "상품 목록" },
    { id: "register", label: "상품 등록" },
    { id: "bulk",     label: "일괄 등록" },
  ];

  async function handleCollect() {
    setLoading(true);
    setError(null);
    try {
      const result = await collectSSProducts(50);
      setData(result);
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
      const result = await getSSProducts();
      setData(result);
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

        {/* ── 상품 목록 탭 ── */}
        {tab === "list" && (
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

            {/* 테이블 동적 렌더링 */}
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

            {/* 셀러센터 바로가기 */}
            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/products/list"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 상품 목록 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 상품 등록 탭 ── */}
        {tab === "register" && (
          <div className="space-y-4">
            <p className="text-xs text-[#6B7280]">상품 등록은 5단계로 진행됩니다. 필수(*) 항목을 반드시 완료하세요.</p>
            <div className="space-y-3">
              {REGISTER_STEPS.map((s) => (
                <div key={s.step} className="flex gap-3 items-start border border-[#E5E7EB] rounded-xl p-4 bg-white">
                  <span
                    className={`text-xs font-bold rounded-full w-7 h-7 flex items-center justify-center shrink-0 ${
                      s.required
                        ? "bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA]"
                        : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]"
                    }`}
                  >
                    {s.step}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-[#111827]">
                      {s.title}
                      {s.required && <span className="ml-1 text-[#DC2626]">*</span>}
                    </p>
                    <p className="text-xs text-[#6B7280] mt-0.5">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/products/new"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-4 py-2 rounded-lg bg-[#F97316] text-white hover:bg-[#EA6D0E] transition-colors font-semibold"
              >
                셀러센터에서 상품 등록 →
              </a>
            </div>
          </div>
        )}

        {/* ── 일괄 등록 탭 ── */}
        {tab === "bulk" && (
          <div className="space-y-4">
            <div className="border border-[#E5E7EB] rounded-xl p-4 bg-white space-y-3">
              <p className="text-sm font-semibold text-[#111827]">CSV 일괄 등록 안내</p>
              <ol className="space-y-2">
                {[
                  "셀러센터 > 상품관리 > 상품 일괄 등록 접속",
                  "엑셀 양식(xlsx) 다운로드 후 상품 정보 입력",
                  "필수 컬럼: 카테고리ID, 상품명, 판매가, 재고, 대표이미지URL",
                  "파일 업로드 후 오류 항목 확인 및 수정",
                  "최종 등록 완료 후 노출 여부 설정",
                ].map((step, i) => (
                  <li key={i} className="flex gap-3 text-xs">
                    <span className="text-[#F97316] font-bold shrink-0">{i + 1}.</span>
                    <span className="text-[#374151]">{step}</span>
                  </li>
                ))}
              </ol>
            </div>
            <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4">
              <p className="text-xs font-semibold text-[#C2410C] mb-1">BulkRegister 모듈</p>
              <p className="text-xs text-[#92400E]">
                자동화 모듈 <span className="font-mono">SmartStore.bulk_register</span>를 통해 CSV 생성 및 업로드를 지원합니다.
                현재 <span className="font-semibold">approval_gated</span> 상태로 승인 후 실행 가능합니다.
              </p>
            </div>
            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/products/bulk"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 일괄 등록 바로가기 →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
