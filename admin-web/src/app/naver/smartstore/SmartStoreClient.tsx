"use client";
/** SmartStoreClient — 13개 메뉴 기반 통합 관리 (대시보드/상품/주문·정산/리뷰·문의/액션 카탈로그/제출 이력) */
import { useState, useCallback } from "react";
import AgentCommandBar from "./AgentCommandBar";
import SmartStoreChat from "./SmartStoreChat";
import type { ActionCatalog, ActionItem, CatalogSection, SubmitRecord } from "./page";
import {
  getSmartStoreStatus,
  getSmartStoreHistory,
  getSmartStoreFormFields,
  type SmartStoreStatusResponse,
  type SmartStoreHistoryResponse,
} from "@/lib/assistant/api";
import NotificationPanel from "./NotificationPanel";

type Tab = "chat" | "dashboard" | "products" | "orders" | "reviews" | "catalog" | "history";

// ── 뱃지 스타일 ──
const RISK_BADGE: Record<string, string> = {
  read:     "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]",
  prepare:  "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
  approval: "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]",
  submit:   "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]",
};

const STATUS_BADGE: Record<string, string> = {
  implemented:       "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
  complete_baseline: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
  approval_gated:    "bg-[#FEF3C7] text-[#92400E] border-[#FDE68A]",
  planned:           "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]",
};

// ── 13개 메뉴 카드 색상 ──
const MENU_CARD_COLOR: Record<string, string> = {
  products:   "border-[#BFDBFE] bg-[#EFF6FF] text-[#1D4ED8]",
  orders:     "border-[#BBF7D0] bg-[#F0FDF4] text-[#16A34A]",
  settlement: "border-[#DDD6FE] bg-[#F5F3FF] text-[#7C3AED]",
  reviews:    "border-[#FED7AA] bg-[#FFF7ED] text-[#C2410C]",
};

interface MenuItem {
  key: string;
  label: string;
  features: string[];
  locked?: boolean;
}

// ── 정적 메뉴 정의 (API fallback) ──
const STATIC_MENUS: MenuItem[] = [
  { key: "products",   label: "상품관리",     features: ["상품 목록", "상품 등록", "상품 수정", "카탈로그 가격관리", "배송정보 관리"] },
  { key: "orders",     label: "판매관리",     features: ["주문 목록", "발송 처리", "반품/교환"] },
  { key: "settlement", label: "정산관리",     features: ["정산 내역", "세금계산서"] },
  { key: "reviews",    label: "문의/리뷰관리", features: ["고객 리뷰", "고객 문의", "리뷰 자동응답"] },
  { key: "store",      label: "스토어관리",   features: ["스토어 정보", "공지사항", "구독 관리"] },
  { key: "marketing",  label: "혜택/마케팅",  features: ["쿠폰", "할인", "포인트"] },
  { key: "delivery",   label: "N배송 관리",   features: ["배송 현황", "반품 처리"] },
  { key: "solution",   label: "커머스솔루션", features: ["솔루션 현황"] },
  { key: "stats",      label: "데이터분석",   features: ["매출 통계", "방문 통계", "상품 분석"] },
  { key: "ads",        label: "광고관리",     features: ["광고 현황"], locked: true },
  { key: "promo",      label: "프로모션 관리", features: ["프로모션 목록"] },
  { key: "connect",    label: "쇼핑 커넥트",  features: ["채널 연결"] },
  { key: "seller",     label: "판매자 정보",  features: ["사업자 정보", "정책 관리"] },
];

// ── 상품 등록 5단계 ──
const REGISTER_STEPS = [
  { step: 1, title: "카테고리 선택", desc: "생활/건강 > 조명 > 무드등/취침등", required: true },
  { step: 2, title: "기본 정보",     desc: "상품명, 판매가, 재고 입력", required: true },
  { step: 3, title: "이미지 등록",   desc: "대표이미지(필수), 추가이미지(선택)", required: true },
  { step: 4, title: "상세 설명",     desc: "스마트에디터 또는 HTML 작성", required: false },
  { step: 5, title: "저장",          desc: "임시저장 → 최종 저장(노출설정)", required: true },
];

// ── 서브 컴포넌트 ──

function MenuCard({ menu }: { menu: MenuItem }) {
  const color = MENU_CARD_COLOR[menu.key] ?? "border-[#E5E7EB] bg-[#F9FAFB] text-[#6B7280]";
  return (
    <div className={`border rounded-xl p-3 ${color} relative`}>
      {menu.locked && (
        <span className="absolute top-2 right-2 text-[10px] bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded font-semibold">잠금</span>
      )}
      <p className="text-sm font-bold mb-1.5">{menu.label}</p>
      <ul className="space-y-0.5">
        {menu.features.map((f) => (
          <li key={f} className="text-xs opacity-80 flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-current opacity-50 shrink-0" />
            {f}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ActionCard({ action }: { action: ActionItem }) {
  return (
    <div className="border border-[#E5E7EB] rounded-lg p-3 bg-white hover:bg-[#F9FAFB] transition-colors">
      <div className="flex items-start gap-2 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold ${RISK_BADGE[action.risk] ?? RISK_BADGE.read}`}>
          {action.risk}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_BADGE[action.status] ?? STATUS_BADGE.planned}`}>
          {action.status}
        </span>
        <span className="text-xs font-mono text-[#6B7280] bg-[#F3F4F6] px-1.5 py-0.5 rounded border border-[#E5E7EB]">
          {action.action_id}
        </span>
      </div>
      <p className="mt-1.5 text-sm font-medium text-[#111827]">{action.label}</p>
      <p className="text-xs text-[#9CA3AF] font-mono truncate mt-0.5">{action.module}</p>
      {action.required_fields && action.required_fields.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          <span className="text-xs text-[#6B7280]">필수:</span>
          {action.required_fields.map((f) => (
            <span key={f} className="text-xs bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded">{f}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function SectionBlock({ section }: { section: CatalogSection }) {
  const SECTION_COLOR: Record<string, string> = {
    read:     "border-[#BBF7D0] bg-[#F0FDF4] text-[#16A34A]",
    prepare:  "border-[#FED7AA] bg-[#FFF7ED] text-[#C2410C]",
    approval: "border-[#FECACA] bg-[#FEF2F2] text-[#DC2626]",
    submit:   "border-[#FECACA] bg-[#FEF2F2] text-[#DC2626]",
  };
  const color = SECTION_COLOR[section.name] ?? "border-[#E5E7EB] bg-[#F9FAFB] text-[#6B7280]";
  return (
    <div className="space-y-2">
      <div className={`flex items-center gap-3 px-3 py-2 rounded-lg border ${color}`}>
        <span className="font-bold text-sm uppercase">{section.name}</span>
        <span className="text-xs">총 {section.summary.total}개</span>
        <span className="text-xs">구현 {section.summary.implemented}개</span>
        {section.summary.approval_gated > 0 && (
          <span className="text-xs">승인필요 {section.summary.approval_gated}개</span>
        )}
      </div>
      <div className="grid grid-cols-1 gap-2 pl-2">
        {section.actions.map((a) => (
          <ActionCard key={a.action_id} action={a} />
        ))}
      </div>
    </div>
  );
}

function HistoryRow({ record, index }: { record: Record<string, unknown>; index: number }) {
  const [open, setOpen] = useState(false);
  const ts = (record.generated_at ?? record.timestamp ?? "") as string;
  const wf = (record.workflow ?? "-") as string;
  const pt = (record.product_type ?? "-") as string;
  const dr = record.dry_run === true;
  return (
    <div className="border border-[#E5E7EB] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-2.5 bg-white hover:bg-[#F9FAFB] text-left"
      >
        <span className="text-xs text-[#9CA3AF] w-6 shrink-0">#{index + 1}</span>
        <span className="text-xs font-mono text-[#6B7280] w-40 shrink-0 truncate">{ts}</span>
        <span className="text-xs text-[#111827] font-medium">{wf}</span>
        <span className="text-xs text-[#6B7280]">{pt}</span>
        {dr ? (
          <span className="ml-auto text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-1.5 py-0.5 rounded">dry_run</span>
        ) : (
          <span className="ml-auto text-xs bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded">live</span>
        )}
        <span className="text-xs text-[#9CA3AF] ml-2">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-[#E5E7EB] px-4 py-3 bg-[#F9FAFB] space-y-1">
          {Object.entries(record).map(([k, v]) => (
            <div key={k} className="flex gap-3 text-xs">
              <span className="font-mono text-[#6B7280] w-32 shrink-0">{k}</span>
              <span className="text-[#111827] break-all">{JSON.stringify(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Props ──
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
  const [catalog, setCatalog] = useState<ActionCatalog | null>(initCatalog);
  const [catalogError, setCatalogError] = useState<string | null>(initCatalogError);
  const [catalogLoading, setCatalogLoading] = useState(false);

  // 이력 상태
  const [historyData, setHistoryData] = useState<SmartStoreHistoryResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // 폼 필드 상태
  const [formFields, setFormFields] = useState<{ required: string[]; optional: string[] } | null>(null);
  const [formLoading, setFormLoading] = useState(false);

  const refreshCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError(null);
    try {
      const res = await getSmartStoreStatus();
      if (res.catalog && res.catalog.sections) {
        setCatalog(res.catalog as unknown as ActionCatalog);
      }
    } catch (e) {
      setCatalogError(e instanceof Error ? e.message : String(e));
    } finally {
      setCatalogLoading(false);
    }
  }, []);

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
    { id: "catalog",   label: "액션 카탈로그" },
    { id: "history",   label: "제출 이력" },
  ];

  const historyItems = historyData?.history ?? [];
  const latestSubmit = historyData?.latest ?? (initSubmit as Record<string, unknown> | null);
  const hasHistory = historyItems.length > 0 || (latestSubmit && Object.keys(latestSubmit).length > 0);

  const requiredFields = formFields?.required ?? ["name", "price", "stock", "category"];
  const optionalFields = formFields?.optional ?? ["description", "brand", "manufacturer", "main_image", "model_name", "options"];

  return (
    <div className="space-y-4">
      {tab !== "chat" && <AgentCommandBar />}
      {/* 계약 정책 배너 */}
      {catalog?.contract && (
        <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4">
          <p className="text-xs font-bold text-[#C2410C] mb-2">계약 정책 (읽기 전용)</p>
          <div className="grid grid-cols-1 gap-1">
            {Object.entries(catalog.contract).map(([k, v]) => (
              <div key={k} className="flex gap-2 text-xs">
                <span className="font-mono text-[#92400E] w-24 shrink-0">{k}:</span>
                <span className="text-[#78350F]">{v}</span>
              </div>
            ))}
          </div>
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

        {/* ── AI 채팅 탭 ── */}
        {tab === "chat" && <SmartStoreChat />}

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

        {/* ── 액션 카탈로그 탭 ── */}
        {tab === "catalog" && (
          <div className="space-y-6">
            <div className="flex justify-end">
              <button
                onClick={refreshCatalog}
                disabled={catalogLoading}
                className="text-xs px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-[#6B7280] hover:bg-[#F3F4F6] disabled:opacity-50 transition-colors"
              >
                {catalogLoading ? "갱신 중..." : "실시간 갱신"}
              </button>
            </div>
            {catalogError && (
              <p className="text-xs text-[#DC2626]">카탈로그 로드 오류: {catalogError}</p>
            )}
            {catalog?.sections?.map((s) => (
              <SectionBlock key={s.name} section={s} />
            ))}
          </div>
        )}

        {/* ── 제출 이력 탭 ── */}
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
                        <span className="bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-1.5 py-0.5 rounded text-xs">dry_run</span>
                      ) : v === false ? (
                        <span className="bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded text-xs">live</span>
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
