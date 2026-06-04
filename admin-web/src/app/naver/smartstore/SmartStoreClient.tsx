"use client";
/** SmartStoreClient — 13개 메뉴 기반 통합 관리 (대시보드/상품/주문·정산/리뷰·문의/액션 카탈로그/제출 이력) */
import { useState, useCallback } from "react";
import SmartStoreChat from "./SmartStoreChat";
import type { ActionCatalog, SubmitRecord } from "./page";
import {
  getSmartStoreStatus,
  getSmartStoreHistory,
  getSmartStoreFormFields,
  type SmartStoreHistoryResponse,
} from "@/lib/assistant/api";
import NotificationPanel from "./NotificationPanel";
import { MenuCard } from "./components/MenuCard";
import { ActionCard } from "./components/ActionCard";
import { HistoryRow } from "./components/HistoryRow";
import { STATIC_MENUS, REGISTER_STEPS } from "./components/constants";

type Tab = "chat" | "dashboard" | "products" | "orders" | "reviews" | "catalog" | "history";

interface Props {
  catalog: ActionCatalog | null;
  catalogError: string | null;
  submit: SubmitRecord | null;
  submitError: string | null;
}

export default function SmartStoreClient({
  catalog: initCatalog,
  catalogError: initCatalogError,
  submit: initSubmit,
  submitError: initSubmitError,
}: Props) {
  const [tab, setTab] = useState<Tab>("chat");

  // 카탈로그 상태
  const [catalog] = useState<ActionCatalog | null>(initCatalog);

  // 이력 상태
  const [historyData, setHistoryData] = useState<SmartStoreHistoryResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // 폼 필드 상태
  const [formFields, setFormFields] = useState<{ required: string[]; optional: string[] } | null>(null);
  const [formLoading, setFormLoading] = useState(false);


  const loadHistory = useCallback(async () => {
    if (historyData) return;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const res = await getSmartStoreHistory();
      setHistoryData(res);
    } catch (e) {
      setHistoryError(e instanceof Error ? e.message : String(e));
    } finally {
      setHistoryLoading(false);
    }
  }, [historyData]);

  const loadFormFields = useCallback(async () => {
    if (formFields) return;
    setFormLoading(true);
    try {
      const res = await getSmartStoreFormFields();
      setFormFields(res);
    } catch {
      // 기본값 사용
    } finally {
      setFormLoading(false);
    }
  }, [formFields]);

  const handleTabChange = (t: Tab) => {
    setTab(t);
    if (t === "history") loadHistory();
    if (t === "products") loadFormFields();
  };

  const TABS: { id: Tab; label: string }[] = [
    { id: "chat",      label: "AI 채팅" },
    { id: "dashboard", label: "대시보드" },
    { id: "products",  label: "상품 관리" },
    { id: "orders",    label: "주문/정산" },
    { id: "reviews",   label: "리뷰/문의" },
    { id: "history",   label: "처리 이력" },
  ];

  const historyItems = historyData?.history ?? [];
  const latestSubmit = historyData?.latest ?? (initSubmit as Record<string, unknown> | null);
  const hasHistory = historyItems.length > 0 || (latestSubmit && Object.keys(latestSubmit).length > 0);

  const requiredFields = formFields?.required ?? ["name", "price", "stock", "category"];
  const optionalFields = formFields?.optional ?? ["description", "brand", "manufacturer", "main_image", "model_name", "options"];

  // 채팅 탭: 전체 높이 고정 레이아웃 (스크롤 없음)
  if (tab === "chat") {
    return (
      <div className="flex flex-col h-full gap-4">
        <div className="bg-white rounded-xl border border-[#E5E7EB] p-3 shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-base font-bold text-[#111827]">스마트스토어</span>
            <div className="flex gap-1 overflow-x-auto">
              {TABS.map((t) => (
                <button key={t.id} onClick={() => handleTabChange(t.id)}
                  className={`text-sm px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap ${
                    t.id === "chat"
                      ? "bg-[#F97316] text-white font-semibold"
                      : "text-[#6B7280] hover:bg-[#F3F4F6]"
                  }`}>
                  {t.label}
                </button>
              ))}
            </div>
            <div className="ml-auto shrink-0"><NotificationPanel /></div>
          </div>
        </div>
        <div className="flex-1 min-h-0">
          <SmartStoreChat />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 안전 안내 — 조회는 자유, 저장은 승인 후에만 */}
      {catalog?.contract && (
        <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-3">
          <p className="text-xs text-[#92400E]">
            🔒 <span className="font-semibold">안전 모드</span> · 상품·주문 <b>조회</b>는 자유롭게 가능하고,
            상품 <b>등록·수정 등 저장</b> 작업은 <b>승인을 누른 뒤에만</b> 실행됩니다.
          </p>
        </div>
      )}

      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-bold text-[#111827]">스마트스토어</span>
          <span className="text-xs bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0] px-2 py-0.5 rounded font-semibold">13개 메뉴</span>
          {catalog?.generated_at && (
            <span className="text-xs text-[#9CA3AF]">{catalog.generated_at}</span>
          )}
          <div className="ml-auto">
            <NotificationPanel />
          </div>
        </div>

        {/* 탭 바 */}
        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => handleTabChange(t.id)}
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

        {/* ── 대시보드 탭 ── */}
        {tab === "dashboard" && (
          <div className="space-y-4">
            <p className="text-xs text-[#6B7280]">스마트스토어 셀러센터 13개 메뉴 구성입니다. 각 메뉴의 주요 기능을 확인하세요.</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {STATIC_MENUS.map((menu) => (
                <MenuCard key={menu.key} menu={menu} />
              ))}
            </div>
            <div className="border border-[#E5E7EB] rounded-xl p-3 bg-[#F9FAFB]">
              <p className="text-xs font-semibold text-[#6B7280] mb-1">셀러센터 바로가기</p>
              <a
                href="https://sell.smartstore.naver.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-[#1D4ED8] underline"
              >
                https://sell.smartstore.naver.com
              </a>
            </div>
          </div>
        )}

        {/* ── 상품 관리 탭 ── */}
        {tab === "products" && (
          <div className="space-y-5">
            {/* 5단계 등록 가이드 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">상품 등록 5단계</p>
              <div className="space-y-2">
                {REGISTER_STEPS.map((s) => (
                  <div key={s.step} className="flex gap-3 items-start">
                    <span
                      className={`text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center shrink-0 ${
                        s.required
                          ? "bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA]"
                          : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]"
                      }`}
                    >
                      {s.step}
                    </span>
                    <div>
                      <p className="text-xs font-semibold text-[#111827]">
                        {s.title}
                        {s.required && <span className="ml-1 text-[#DC2626]">*</span>}
                      </p>
                      <p className="text-xs text-[#6B7280]">{s.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 필드 체크리스트 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">등록 필드 체크리스트</p>
              {formLoading && <p className="text-xs text-[#6B7280]">필드 정보 로드 중...</p>}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold text-[#DC2626] mb-1.5">필수 필드</p>
                  <div className="flex flex-wrap gap-1.5">
                    {requiredFields.map((f) => (
                      <span key={f} className="text-xs bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-2 py-0.5 rounded font-mono">{f}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-semibold text-[#6B7280] mb-1.5">선택 필드</p>
                  <div className="flex flex-wrap gap-1.5">
                    {optionalFields.map((f) => (
                      <span key={f} className="text-xs bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB] px-2 py-0.5 rounded font-mono">{f}</span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="mt-2 border-t border-[#E5E7EB] pt-2">
                <p className="text-xs text-[#6B7280] font-semibold mb-1">제한 사항</p>
                <div className="flex flex-wrap gap-3 text-xs text-[#6B7280]">
                  <span>상품명 최대 <strong>100자</strong></span>
                  <span>판매가 최소 <strong>10원</strong></span>
                  <span>재고 최대 <strong>9,999,999</strong></span>
                  <span>이미지 최대 <strong>10MB</strong></span>
                </div>
              </div>
            </div>

            {/* 임시저장 상태 */}
            {initSubmit && Object.keys(initSubmit).length > 0 && (
              <div className="border border-[#DDD6FE] bg-[#F5F3FF] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#7C3AED] mb-2">현재 임시저장 상태</p>
                {Object.entries(initSubmit).slice(0, 5).map(([k, v]) => (
                  <div key={k} className="flex gap-3 text-xs">
                    <span className="font-mono text-[#6B7280] w-28 shrink-0">{k}</span>
                    <span className="text-[#111827]">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* 셀러센터 바로가기 */}
            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/products/new"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#1D4ED8] text-[#1D4ED8] hover:bg-[#EFF6FF] transition-colors"
              >
                셀러센터 상품등록 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 주문/정산 탭 ── */}
        {tab === "orders" && (
          <div className="space-y-5">
            {/* 주문 처리 흐름 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">주문 처리 흐름</p>
              <div className="flex items-center gap-2 flex-wrap">
                {["결제완료", "배송준비", "배송중", "배송완료"].map((step, i, arr) => (
                  <div key={step} className="flex items-center gap-2">
                    <span className="text-xs px-3 py-1.5 rounded-full bg-[#F0FDF4] border border-[#BBF7D0] text-[#16A34A] font-semibold">
                      {step}
                    </span>
                    {i < arr.length - 1 && <span className="text-[#9CA3AF] text-sm">→</span>}
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                {[
                  { label: "주문 목록", desc: "판매관리 > 주문 목록에서 전체 주문 확인" },
                  { label: "발송 처리", desc: "송장번호 입력 후 배송 상태 자동 업데이트" },
                  { label: "반품/교환", desc: "고객 요청 수락 → 회수 완료 → 환불 처리" },
                ].map((item) => (
                  <div key={item.label} className="flex gap-3 text-xs">
                    <span className="font-semibold text-[#111827] w-20 shrink-0">{item.label}</span>
                    <span className="text-[#6B7280]">{item.desc}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 정산 안내 */}
            <div className="border border-[#DDD6FE] bg-[#F5F3FF] rounded-xl p-4 space-y-2">
              <p className="text-sm font-semibold text-[#7C3AED]">정산 주기 안내</p>
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-24 shrink-0">정산 주기</span>
                  <span className="text-[#111827]">구매 확정일 기준 영업일 +2일</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-24 shrink-0">정산 내역</span>
                  <span className="text-[#111827]">정산관리 &gt; 정산 내역에서 확인</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-24 shrink-0">세금계산서</span>
                  <span className="text-[#111827]">월별 세금계산서 자동 발행</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── 리뷰/문의 탭 ── */}
        {tab === "reviews" && (
          <div className="space-y-5">
            {/* 리뷰 자동응답 */}
            <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-[#16A34A]">리뷰 자동응답</p>
                <span className="text-xs bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-2 py-0.5 rounded">구현됨</span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">자동응답 모듈</span>
                  <span className="text-[#111827] font-mono">SmartStore.reviews</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">평균 별점 목표</span>
                  <span className="text-[#111827]">4.5점 이상 유지</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">응답 기준</span>
                  <span className="text-[#111827]">3점 이하 리뷰 24시간 내 수동 응답 권장</span>
                </div>
              </div>
            </div>

            {/* 고객 문의 처리 안내 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-sm font-semibold text-[#111827]">문의 처리 안내</p>
              <div className="space-y-2 text-xs">
                {[
                  { step: "1", label: "문의 확인",    desc: "문의/리뷰관리 > 고객 문의에서 미답변 목록 확인" },
                  { step: "2", label: "답변 작성",    desc: "24시간 내 답변 권장 (네이버 셀러 평가 기준)" },
                  { step: "3", label: "CS 케이스 분류", desc: "환불/교환/배송 문의는 판매관리 연계 처리" },
                ].map((item) => (
                  <div key={item.step} className="flex gap-3">
                    <span className="text-xs font-bold text-[#F97316] bg-[#FFF7ED] border border-[#FED7AA] rounded-full w-6 h-6 flex items-center justify-center shrink-0">
                      {item.step}
                    </span>
                    <div>
                      <p className="font-semibold text-[#111827]">{item.label}</p>
                      <p className="text-[#6B7280]">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── 처리 이력 탭 ── */}
        {tab === "history" && (
          <div className="space-y-3">
            {historyLoading && <p className="text-xs text-[#6B7280]">이력 로드 중...</p>}
            {historyError && <p className="text-xs text-[#DC2626]">이력 로드 오류: {historyError}</p>}
            {!historyLoading && !hasHistory && !historyError && !initSubmitError && (
              <div className="border border-[#E5E7EB] rounded-xl p-8 bg-white text-center">
                <p className="text-sm text-[#6B7280]">제출 이력 없음</p>
                <p className="text-xs text-[#9CA3AF] mt-1">아직 제출된 워크플로우가 없습니다.</p>
              </div>
            )}
            {initSubmitError && !historyData && (
              <p className="text-xs text-[#DC2626]">제출 이력 로드 오류: {initSubmitError}</p>
            )}
            {latestSubmit && Object.keys(latestSubmit).length > 0 && historyItems.length === 0 && (
              <div className="border border-[#E5E7EB] rounded-xl p-4 bg-white space-y-2">
                <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wide">최근 제출 기록</p>
                {Object.entries(latestSubmit).map(([k, v]) => (
                  <div key={k} className="flex gap-3 text-sm">
                    <span className="font-mono text-xs text-[#6B7280] w-32 shrink-0">{k}</span>
                    <span className="text-[#111827] text-xs">
                      {v === true ? (
                        <span className="bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-1.5 py-0.5 rounded text-xs">테스트(미저장)</span>
                      ) : v === false ? (
                        <span className="bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded text-xs">실제 실행</span>
                      ) : (
                        String(v)
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {historyItems.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs text-[#6B7280] font-semibold">총 {historyItems.length}건</p>
                {historyItems.map((r, i) => (
                  <HistoryRow key={i} record={r} index={i} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
