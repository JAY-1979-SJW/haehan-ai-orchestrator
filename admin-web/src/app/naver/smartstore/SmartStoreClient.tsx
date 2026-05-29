"use client";
/** SmartStoreClient — 액션 카탈로그 / 제출 이력 / 상품 등록 가이드 탭 */
import { useState, useCallback } from "react";
import type { ActionCatalog, ActionItem, CatalogSection, SubmitRecord } from "./page";
import {
  getSmartStoreStatus,
  getSmartStoreHistory,
  getSmartStoreFormFields,
  type SmartStoreStatusResponse,
  type SmartStoreHistoryResponse,
} from "@/lib/assistant/api";

type Tab = "catalog" | "history" | "guide";

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

// ── 이력 행 컴포넌트 ──
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

// ── 상품 등록 가이드 ──
const REGISTER_STEPS = [
  { step: 1, title: "카탈로그 확인", desc: "액션 카탈로그 탭에서 product.general.prepare 또는 product.group.prepare 액션 확인" },
  { step: 2, title: "상품 데이터 준비", desc: "필수 필드(name, price, stock, category) 값을 준비. JSON 형식 권장" },
  { step: 3, title: "prepare 실행", desc: "scripts/naver/smartstore/general_product.py 의 register_product(data, save_after=False) 로 dry-run 검증" },
  { step: 4, title: "승인 토큰 발급", desc: "save_after=True + require_confirm=True 로 실행 시 SMARTSTORE_APPROVED_SUBMIT 컨펌 필요" },
  { step: 5, title: "일괄 등록", desc: "복수 상품은 BulkRegister.register_all(products, product_type='general') 사용" },
];

interface Props {
  catalog: ActionCatalog | null;
  catalogError: string | null;
  submit: SubmitRecord | null;
  submitError: string | null;
}

export default function SmartStoreClient({ catalog: initCatalog, catalogError: initCatalogError, submit: initSubmit, submitError: initSubmitError }: Props) {
  const [tab, setTab] = useState<Tab>("catalog");

  // 실시간 API 상태
  const [catalog, setCatalog] = useState<ActionCatalog | null>(initCatalog);
  const [catalogError, setCatalogError] = useState<string | null>(initCatalogError);
  const [catalogLoading, setCatalogLoading] = useState(false);

  const [historyData, setHistoryData] = useState<SmartStoreHistoryResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

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
    if (t === "guide") loadFormFields();
  };

  const TABS: { id: Tab; label: string }[] = [
    { id: "catalog", label: "액션 카탈로그" },
    { id: "history", label: "제출 이력" },
    { id: "guide", label: "상품 등록 가이드" },
  ];

  // 이력 — submit prop도 fallback으로 사용
  const historyItems = historyData?.history ?? [];
  const latestSubmit = historyData?.latest ?? (initSubmit as Record<string, unknown> | null);
  const hasHistory = historyItems.length > 0 || (latestSubmit && Object.keys(latestSubmit).length > 0);

  return (
    <div className="space-y-4">
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
          <span className="text-xs bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0] px-2 py-0.5 rounded font-semibold">조회 전용</span>
          {catalog?.generated_at && (
            <span className="text-xs text-[#9CA3AF] ml-auto">{catalog.generated_at}</span>
          )}
        </div>

        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => handleTabChange(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors ${
                tab === t.id
                  ? "border-[#F97316] text-[#F97316] font-semibold"
                  : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 액션 카탈로그 ── */}
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

        {/* ── 제출 이력 ── */}
        {tab === "history" && (
          <div className="space-y-3">
            {historyLoading && (
              <p className="text-xs text-[#6B7280]">이력 로드 중...</p>
            )}
            {historyError && (
              <p className="text-xs text-[#DC2626]">이력 로드 오류: {historyError}</p>
            )}
            {!historyLoading && !hasHistory && !historyError && !initSubmitError && (
              <div className="border border-[#E5E7EB] rounded-xl p-8 bg-white text-center">
                <p className="text-sm text-[#6B7280]">제출 이력 없음</p>
                <p className="text-xs text-[#9CA3AF] mt-1">아직 제출된 워크플로우가 없습니다.</p>
              </div>
            )}
            {initSubmitError && !historyData && (
              <p className="text-xs text-[#DC2626]">제출 이력 로드 오류: {initSubmitError}</p>
            )}
            {/* 최근 제출 (latest) */}
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
            {/* 이력 목록 */}
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

        {/* ── 상품 등록 가이드 ── */}
        {tab === "guide" && (
          <div className="space-y-6">
            {/* 필수/선택 필드 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">상품 등록 필드</p>
              {formLoading && <p className="text-xs text-[#6B7280]">필드 정보 로드 중...</p>}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold text-[#DC2626] mb-1.5">필수 필드</p>
                  <div className="flex flex-wrap gap-1.5">
                    {(formFields?.required ?? ["name", "price", "stock", "category"]).map((f) => (
                      <span key={f} className="text-xs bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-2 py-0.5 rounded font-mono">{f}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-semibold text-[#6B7280] mb-1.5">선택 필드</p>
                  <div className="flex flex-wrap gap-1.5">
                    {(formFields?.optional ?? ["description", "brand", "manufacturer", "main_image", "model_name"]).map((f) => (
                      <span key={f} className="text-xs bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB] px-2 py-0.5 rounded font-mono">{f}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* 빠른 등록 절차 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">빠른 등록 절차</p>
              <div className="space-y-2">
                {REGISTER_STEPS.map((s) => (
                  <div key={s.step} className="flex gap-3">
                    <span className="text-xs font-bold text-[#F97316] bg-[#FFF7ED] border border-[#FED7AA] rounded-full w-6 h-6 flex items-center justify-center shrink-0">
                      {s.step}
                    </span>
                    <div>
                      <p className="text-xs font-semibold text-[#111827]">{s.title}</p>
                      <p className="text-xs text-[#6B7280]">{s.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 코드 예시 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4">
              <p className="text-xs font-semibold text-[#111827] mb-2">Python 예시</p>
              <pre className="text-xs font-mono bg-[#F9FAFB] border border-[#E5E7EB] rounded-lg p-3 overflow-x-auto text-[#374151]">{`# 일반 상품 등록 (dry-run)
from scripts.naver.smartstore import NaverSmartStore

data = {
    "name": "상품명",
    "price": 10000,
    "stock": 100,
    "category": "카테고리",
    "description": "상품 설명",
}

store = NaverSmartStore(page)
store.open_dashboard()
result = store.register_general_product(
    data,
    save_after=False,      # dry-run
    require_confirm=True,  # 저장 전 컨펌
)`}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
