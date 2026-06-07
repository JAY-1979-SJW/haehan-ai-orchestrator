"use client";
import type {
  AutoRegisterResult,
  PopupScanResult,
  PopupHandleResult,
  PopupStatusResult,
  SellerCenterPageKey,
} from "@/lib/assistant/api";
import { ProductForm } from "./ProductForm";

interface AutoTabProps {
  autoData: string;
  autoResult: AutoRegisterResult | null;
  autoLoading: boolean;
  autoError: string | null;
  pollerInfo: { running?: boolean; poll_count?: number; interval?: number } | null;
  popupLoading: string | null;
  popupScanRes: PopupScanResult | null;
  popupHandleRes: PopupHandleResult | null;
  popupStatusRes: PopupStatusResult | null;
  popupMsg: { ok: boolean; text: string } | null;
  catCache: { exists?: boolean; count?: number; built_at?: string } | null;
  catBuilding: boolean;
  catSearch: string;
  catResults: { id: string; name: string; path: string }[];
  openingPage: SellerCenterPageKey | null;
  onSetAutoData: (v: string) => void;
  onAutoRegister: () => void;
  onRefreshPollerStatus: () => void;
  onPollerToggle: () => void;
  onPopupUnblock: () => void;
  onPopupScan: () => void;
  onPopupHandle: () => void;
  onPopupStatus: () => void;
  onBuildCache: () => void;
  onCatSearch: (q: string) => void;
  onCatResultSelect: (name: string) => void;
  onOpenSellerCenter: (pageKey: SellerCenterPageKey) => void;
}

export default function AutoTab({
  autoData, autoResult, autoLoading, autoError,
  pollerInfo, popupLoading, popupScanRes, popupHandleRes, popupStatusRes, popupMsg,
  catCache, catBuilding, catSearch, catResults,
  openingPage,
  onSetAutoData, onAutoRegister,
  onRefreshPollerStatus, onPollerToggle,
  onPopupUnblock, onPopupScan, onPopupHandle, onPopupStatus,
  onBuildCache, onCatSearch, onCatResultSelect,
  onOpenSellerCenter,
}: AutoTabProps) {
  return (
    <div className="space-y-4">
      {/* 안내 배너 */}
      <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4 space-y-1">
        <p className="text-sm font-semibold text-[#C2410C]">CDP 자동 등록 (임시저장 전용)</p>
        <p className="text-xs text-[#92400E]">
          CDP 브라우저가 실행 중이어야 합니다. 폼을 자동으로 채운 뒤 <strong>임시저장</strong>까지만 진행합니다.
          최종 저장은 브라우저에서 직접 확인 후 눌러주세요.
        </p>
      </div>

      {/* 카테고리 캐시 패널 */}
      <div className="border border-[#E5E7EB] rounded-xl p-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-[#111827]">카테고리 캐시</p>
          {catCache?.exists ? (
            <span className="text-[10px] text-[#16A34A] font-semibold">
              ✓ {(catCache.count ?? 0).toLocaleString()}개 캐시됨 {catCache.built_at ? `(${catCache.built_at})` : ""}
            </span>
          ) : (
            <span className="text-[10px] text-[#DC2626]">캐시 없음 — 매번 검색 필요</span>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={onBuildCache} disabled={catBuilding}
            className="px-3 py-1.5 rounded-lg bg-[#1D4ED8] text-white text-xs font-semibold hover:bg-[#1E40AF] disabled:opacity-50 transition-colors shrink-0">
            {catBuilding ? "구축 중…" : catCache?.exists ? "재구축" : "캐시 구축"}
          </button>
          <input value={catSearch} onChange={e => onCatSearch(e.target.value)}
            placeholder="카테고리 검색 (예: 조명, 가구)"
            className="flex-1 border border-[#E5E7EB] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#1D4ED8]" />
        </div>
        {catResults.length > 0 && (
          <div className="max-h-32 overflow-y-auto border border-[#E5E7EB] rounded-lg">
            {catResults.map(c => (
              <button key={c.id} onClick={() => onCatResultSelect(c.name)}
                className="w-full text-left px-3 py-1.5 text-xs hover:bg-[#F9FAFB] border-b border-[#F3F4F6] last:border-0">
                <span className="text-[#6B7280]">{c.path}</span>
              </button>
            ))}
          </div>
        )}
        {catCache?.exists === false && (
          <p className="text-[10px] text-[#9CA3AF]">
            캐시 구축 후 카테고리 이름으로 즉시 선택 가능 (검색 3~4초 생략)
          </p>
        )}
      </div>

      {/* 상품 정보 입력 — 폼 (코드 대신 입력칸) */}
      <div>
        <p className="text-sm font-semibold text-[#111827] mb-2">상품 정보</p>
        <p className="text-xs text-[#9CA3AF] mb-2">필수: 상품명 · 판매가 · 재고 · 카테고리</p>
        <ProductForm value={autoData} onChange={onSetAutoData} />
      </div>

      {/* 팝업 관리 패널 */}
      <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-[#111827]">팝업 관리</p>
          <div className="flex items-center gap-2">
            {pollerInfo === null && (
              <button onClick={onRefreshPollerStatus} className="text-xs text-[#9CA3AF] hover:text-[#6B7280]">
                상태 확인
              </button>
            )}
            {pollerInfo !== null && (
              <>
                <span className={`text-xs px-2 py-0.5 rounded-full font-semibold border ${
                  pollerInfo.running
                    ? "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]"
                    : "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]"
                }`}>
                  {pollerInfo.running ? `🟢 감시 중 (${pollerInfo.poll_count}회)` : "⚪ 감시 중지"}
                </span>
                <button
                  onClick={onPollerToggle}
                  className="text-xs px-2 py-0.5 rounded border border-[#E5E7EB] text-[#6B7280] hover:bg-[#F9FAFB]"
                >
                  {pollerInfo.running ? "정지" : "시작"}
                </button>
              </>
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={onPopupUnblock}
            disabled={popupLoading !== null}
            className="py-2 rounded-lg border border-[#7C3AED] text-[#7C3AED] text-xs font-semibold hover:bg-[#F5F3FF] disabled:opacity-50 transition-colors"
          >
            {popupLoading === "unblock" ? "처리 중…" : "🔓 차단 해제"}
          </button>
          <button
            onClick={onPopupScan}
            disabled={popupLoading !== null}
            className="py-2 rounded-lg border border-[#1D4ED8] text-[#1D4ED8] text-xs font-semibold hover:bg-[#EFF6FF] disabled:opacity-50 transition-colors"
          >
            {popupLoading === "scan" ? "스캔 중…" : "🔍 팝업 스캔"}
          </button>
          <button
            onClick={onPopupHandle}
            disabled={popupLoading !== null}
            className="py-2 rounded-lg border border-[#03C75A] text-[#03C75A] text-xs font-semibold hover:bg-[#F0FDF4] disabled:opacity-50 transition-colors"
          >
            {popupLoading === "handle" ? "처리 중…" : "✓ 팝업 자동 닫기"}
          </button>
          <button
            onClick={onPopupStatus}
            disabled={popupLoading !== null}
            className="py-2 rounded-lg border border-[#E5E7EB] text-[#6B7280] text-xs font-semibold hover:bg-[#F9FAFB] disabled:opacity-50 transition-colors"
          >
            {popupLoading === "status" ? "조회 중…" : "📋 감지 이력"}
          </button>
        </div>

        {popupMsg && (
          <p className={`text-xs ${popupMsg.ok ? "text-[#16A34A]" : "text-[#DC2626]"}`}>
            {popupMsg.ok ? "✓ " : "✗ "}{popupMsg.text}
          </p>
        )}

        {popupScanRes && (
          <div className={`rounded-lg p-3 text-xs space-y-1 ${popupScanRes.ok ? "bg-[#F9FAFB] border border-[#E5E7EB]" : "bg-[#FEF2F2] border border-[#FECACA]"}`}>
            {popupScanRes.ok ? (
              <>
                <p className="font-semibold text-[#111827]">감지된 팝업: {popupScanRes.found ?? 0}개</p>
                {(popupScanRes.popups ?? []).map((p, i) => (
                  <div key={i} className="flex gap-2 text-[#6B7280]">
                    <span className="font-mono shrink-0">{p.selector.slice(0, 30)}</span>
                    <span className="truncate">{p.text || "(텍스트 없음)"}</span>
                  </div>
                ))}
                {(popupScanRes.found ?? 0) === 0 && <p className="text-[#9CA3AF]">팝업 없음 — 페이지 깨끗</p>}
              </>
            ) : (
              <p className="text-[#DC2626]">{popupScanRes.error}</p>
            )}
          </div>
        )}

        {popupHandleRes && (
          <div className={`rounded-lg p-3 text-xs space-y-1 ${popupHandleRes.ok && popupHandleRes.page_clean ? "bg-[#F0FDF4] border border-[#BBF7D0]" : "bg-[#F9FAFB] border border-[#E5E7EB]"}`}>
            {popupHandleRes.ok ? (
              <>
                <p className="font-semibold text-[#111827]">
                  닫은 팝업: {popupHandleRes.closed ?? 0}개
                  {popupHandleRes.page_clean ? " ✓ 페이지 깨끗" : " ⚠ 잔여 팝업 있음"}
                </p>
                <p className="text-[#6B7280]">처리 전 {popupHandleRes.popups_before ?? 0}개 → 처리 후 {popupHandleRes.popups_after ?? 0}개</p>
              </>
            ) : (
              <p className="text-[#DC2626]">{popupHandleRes.error}</p>
            )}
          </div>
        )}

        {popupStatusRes?.ok && (
          <div className="rounded-lg p-3 text-xs space-y-2 bg-[#F9FAFB] border border-[#E5E7EB]">
            <div className="flex gap-4 text-[#6B7280]">
              <span>새 탭: <strong className="text-[#111827]">{popupStatusRes.new_tab_count ?? 0}</strong></span>
              <span>새 창: <strong className="text-[#111827]">{popupStatusRes.new_window_count ?? 0}</strong></span>
              <span>레이어: <strong className="text-[#111827]">{popupStatusRes.layer_count ?? 0}</strong></span>
            </div>
            {(popupStatusRes.recent_events ?? []).slice(-5).map((ev, i) => (
              <div key={i} className="flex gap-2 text-[#9CA3AF]">
                <span className="font-mono">{ev.ts}</span>
                <span className={`px-1.5 rounded text-[10px] font-semibold ${ev.kind === "new_window" ? "bg-[#FEF2F2] text-[#DC2626]" : ev.kind === "layer" ? "bg-[#EFF6FF] text-[#1D4ED8]" : "bg-[#F3F4F6] text-[#6B7280]"}`}>{ev.kind}</span>
                <span className="truncate">{String((ev as Record<string, unknown>).url ?? (ev as Record<string, unknown>).before ?? "")}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 실행 버튼 */}
      <button
        onClick={onAutoRegister}
        disabled={autoLoading}
        className="w-full py-3 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-50 transition-colors"
      >
        {autoLoading ? "폼 자동 입력 중…" : "CDP 자동 등록 (임시저장)"}
      </button>

      {autoError && (
        <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3">
          <p className="text-sm text-[#DC2626] whitespace-pre-wrap">{autoError}</p>
        </div>
      )}

      {autoResult && (
        <div className={`border rounded-xl p-4 space-y-3 ${
          autoResult.ok ? "border-[#BBF7D0] bg-[#F0FDF4]" : "border-[#FECACA] bg-[#FEF2F2]"
        }`}>
          <p className={`text-sm font-semibold ${autoResult.ok ? "text-[#16A34A]" : "text-[#DC2626]"}`}>
            {autoResult.ok ? "✓ 임시저장 완료" : "✗ 등록 실패"}
          </p>
          {autoResult.steps && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-[#6B7280] uppercase tracking-wide">단계별 결과</p>
              {Object.entries(autoResult.steps).map(([step, r]) => (
                <div key={step} className="flex items-center gap-2 text-xs">
                  <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
                    r.ok ? "bg-[#03C75A] text-white" : "bg-[#DC2626] text-white"
                  }`}>
                    {r.ok ? "✓" : "✗"}
                  </span>
                  <span className="font-mono text-[#6B7280] w-24 shrink-0">{step}</span>
                  {!r.ok && r.error != null && (
                    <span className="text-[#DC2626] truncate">{String(r.error as unknown)}</span>
                  )}
                </div>
              ))}
            </div>
          )}
          {autoResult.hint && (
            <p className="text-xs text-[#92400E]">{autoResult.hint}</p>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => onOpenSellerCenter("register")}
          disabled={openingPage === "register"}
          className="text-xs px-3 py-1.5 rounded-lg border border-[#03C75A] text-[#03C75A] hover:bg-[#F0FDF4] disabled:opacity-50 transition-colors"
        >
          {openingPage === "register" ? "이동 중…" : "셀러센터 등록 페이지 열기 →"}
        </button>
      </div>
    </div>
  );
}
