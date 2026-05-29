"use client";
/** ProductsClient — 상품 관리 (목록/등록/일괄 등록/상세설명 빌더/자동등록) — CDP 수집 연동 */
import { useState, useEffect } from "react";
import AgentCommandBar from "../AgentCommandBar";
import {
  getSSProducts,
  collectSSProducts,
  openSellerCenter,
  getDescriptionSections,
  renderDescription,
  aiGenerateDescription,
  gptGenerateDescription,
  autoRegisterProduct,
  editProduct,
  type ProductEditResult,
  popupUnblock,
  popupScan,
  popupHandle,
  popupStatus,
  popupPollerStatus,
  popupPollerStart,
  popupPollerStop,
  getCategoryCacheInfo,
  buildCategoryCache,
  searchCategories,
  listDescTemplates,
  getDescTemplate,
  saveDescTemplate,
  deleteDescTemplate,
  type DescTemplate,
  type SSTableData,
  type SellerCenterPageKey,
  type DescriptionSection,
  type AutoRegisterResult,
  type PopupScanResult,
  type PopupHandleResult,
  type PopupStatusResult,
} from "@/lib/assistant/api";
import ProductDetailDrawer from "./ProductDetailDrawer";

type Tab = "list" | "register" | "bulk" | "desc" | "auto" | "edit";

const REGISTER_STEPS = [
  { step: 1, title: "카테고리 선택", desc: "정확한 카테고리 선택 (판매 수수료 결정)", required: true },
  { step: 2, title: "기본 정보",     desc: "상품명(최대 100자), 판매가(최소 10원), 재고 수량", required: true },
  { step: 3, title: "이미지 등록",   desc: "대표이미지 필수(최대 10MB), 추가이미지 선택", required: true },
  { step: 4, title: "상세 설명",     desc: "스마트에디터 또는 HTML 직접 작성", required: false },
  { step: 5, title: "저장 및 노출",  desc: "임시저장 → 최종 저장 → 노출 설정 확인", required: true },
];

// 상품 목록 헤더에서 product_id 컬럼 인덱스 탐색
function findProductIdIndex(headers: string[]): number {
  const keys = ["상품번호", "productNo", "상품 번호", "번호"];
  return headers.findIndex(h => keys.some(k => h.includes(k)));
}

// 행 데이터에서 product_id 추출 (링크 href 또는 텍스트)
function extractProductId(row: string[], pidIdx: number): string | null {
  const cell = pidIdx >= 0 ? row[pidIdx] : row[0];
  if (!cell) return null;
  const m = cell.match(/\d{8,}/);
  return m ? m[0] : null;
}

export default function ProductsClient() {
  const [tab, setTab] = useState<Tab>("list");
  const [data, setData] = useState<SSTableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawerProductId, setDrawerProductId] = useState<string | null>(null);
  const [openingPage, setOpeningPage] = useState<SellerCenterPageKey | null>(null);
  const [openMsg, setOpenMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // 템플릿 상태
  const [templates, setTemplates]             = useState<DescTemplate[]>([]);
  const [tmplLoading, setTmplLoading]         = useState(false);
  const [savingTmpl, setSavingTmpl]           = useState(false);
  const [tmplName, setTmplName]               = useState("");
  const [tmplCategory, setTmplCategory]       = useState("");
  const [tmplMsg, setTmplMsg]                 = useState<{ ok: boolean; text: string } | null>(null);
  const [showSaveForm, setShowSaveForm]        = useState(false);

  async function loadTemplates() {
    setTmplLoading(true);
    try {
      const res = await listDescTemplates();
      if (res.ok) setTemplates(res.templates);
    } catch { /* ignore */ }
    finally { setTmplLoading(false); }
  }

  async function handleLoadTemplate(id: string) {
    try {
      const t = await getDescTemplate(id);
      if (!t.ok) return;
      if (t.sections) setSelectedSections(t.sections);
      if (t.data)     setDescData(JSON.stringify(t.data, null, 2));
      if (t.html)     setDescHtml(t.html);
      setTmplMsg({ ok: true, text: `"${t.name}" 템플릿 불러옴` });
      setTimeout(() => setTmplMsg(null), 3000);
    } catch (e) { setTmplMsg({ ok: false, text: String(e) }); }
  }

  async function handleSaveTemplate() {
    if (!tmplName.trim()) { setTmplMsg({ ok: false, text: "템플릿 이름을 입력하세요" }); return; }
    if (!descHtml)        { setTmplMsg({ ok: false, text: "먼저 상세설명을 생성하세요" }); return; }
    setSavingTmpl(true);
    try {
      const data = JSON.parse(descData);
      const res  = await saveDescTemplate({
        name: tmplName.trim(), category: tmplCategory.trim(),
        sections: selectedSections, data, html: descHtml,
        source: aiLoading ? "ai" : gptLoading ? "gpt" : "manual",
      });
      if (res.ok) {
        setTmplMsg({ ok: true, text: `"${res.name}" 저장 완료` });
        setShowSaveForm(false); setTmplName(""); setTmplCategory("");
        await loadTemplates();
      }
    } catch (e) { setTmplMsg({ ok: false, text: String(e) }); }
    finally { setSavingTmpl(false); setTimeout(() => setTmplMsg(null), 3000); }
  }

  async function handleDeleteTemplate(id: string, name: string) {
    if (!confirm(`"${name}" 템플릿을 삭제할까요?`)) return;
    try {
      await deleteDescTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch { /* ignore */ }
  }

  // 상세설명 빌더 상태
  const [descSections, setDescSections] = useState<DescriptionSection[]>([]);
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  const [descData, setDescData] = useState<string>(
    JSON.stringify(
      { name: "상품명", price: 29800, hero_tag: "전국 공식 총판", sub: "서브 카피 문구",
        features: [{ icon: "✅", title: "특징 1", desc: "설명" }],
        as_warranty: "1년", as_contact: "스마트스토어 문의",
        specs: { 크기: "–", 소재: "–" } },
      null, 2,
    ),
  );
  const [descHtml, setDescHtml] = useState<string | null>(null);
  const [descLoading, setDescLoading] = useState(false);
  const [descError, setDescError] = useState<string | null>(null);

  useEffect(() => {
    if (tab !== "desc") return;
    if (descSections.length === 0) {
      getDescriptionSections().then((res) => {
        if (res.ok) { setDescSections(res.sections); setSelectedSections(res.default_sections); }
      }).catch(() => {});
    }
    if (templates.length === 0) loadTemplates();
  }, [tab]);  // eslint-disable-line react-hooks/exhaustive-deps

  function toggleSection(key: string, required: boolean) {
    if (required) return;
    setSelectedSections((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  // AI 생성 상태 (Claude)
  const [aiLoading, setAiLoading] = useState(false);
  const [aiModel, setAiModel] = useState<"default" | "quality">("default");

  // GPT 생성 상태
  const [gptLoading, setGptLoading] = useState(false);
  const [gptModel, setGptModel] = useState<"default" | "quality">("default");
  const [gptImages, setGptImages] = useState<string>("");   // 줄 구분 URL/경로
  const [gptAnalysis, setGptAnalysis] = useState<Record<string, unknown> | null>(null);

  async function handleGptGenerate() {
    setGptLoading(true);
    setDescError(null);
    setDescHtml(null);
    setGptAnalysis(null);
    try {
      const data = JSON.parse(descData);
      const images = gptImages.split("\n").map(s => s.trim()).filter(Boolean);
      const res = await gptGenerateDescription(data, images, gptModel === "quality" ? "quality" : undefined);
      if (res.ok && res.html) {
        setDescHtml(res.html);
        if (res.image_analysis) setGptAnalysis(res.image_analysis);
      } else {
        const msgs = res.errors ?? (res.error ? [res.error] : ["GPT 생성 실패"]);
        setDescError(msgs.join("\n"));
      }
    } catch (e) {
      setDescError(String(e));
    } finally {
      setGptLoading(false);
    }
  }

  async function handleAiGenerate() {
    setAiLoading(true);
    setDescError(null);
    setDescHtml(null);
    try {
      const data = JSON.parse(descData);
      const res = await aiGenerateDescription(data, aiModel === "quality" ? "quality" : undefined);
      if (res.ok && res.html) {
        setDescHtml(res.html);
      } else {
        const msgs = res.errors ?? (res.error ? [res.error] : ["AI 생성 실패"]);
        setDescError(msgs.join("\n"));
      }
    } catch (e) {
      setDescError(String(e));
    } finally {
      setAiLoading(false);
    }
  }

  // 자동 등록 상태
  const [autoData, setAutoData] = useState<string>(
    JSON.stringify(
      { name: "상품명", price: 29800, stock: 100, category: "생활/주방 > 조명",
        brand: "", origin: "", keywords: [], description: "" },
      null, 2,
    ),
  );
  const [autoResult, setAutoResult] = useState<AutoRegisterResult | null>(null);
  const [autoLoading, setAutoLoading] = useState(false);
  const [autoError, setAutoError] = useState<string | null>(null);

  // 팝업 폴러 상태
  const [pollerInfo, setPollerInfo] = useState<{ running?: boolean; poll_count?: number; interval?: number } | null>(null);

  async function refreshPollerStatus() {
    try { setPollerInfo(await popupPollerStatus()); } catch { /* ignore */ }
  }

  async function handlePollerToggle() {
    if (pollerInfo?.running) {
      await popupPollerStop();
    } else {
      await popupPollerStart(5);
    }
    await refreshPollerStatus();
  }

  // 상품 수정 상태
  const [editProductId, setEditProductId] = useState("");
  const [editFields, setEditFields] = useState(JSON.stringify(
    { name: "", price: 0, stock: 0, description: "", keywords: [], brand: "", origin: "" },
    null, 2,
  ));
  const [editResult, setEditResult] = useState<ProductEditResult | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  async function handleEdit() {
    if (!editProductId.trim()) { setEditError("상품번호를 입력하세요"); return; }
    setEditLoading(true); setEditError(null); setEditResult(null);
    try {
      const fields = JSON.parse(editFields);
      // 빈 값 제거
      const cleaned = Object.fromEntries(
        Object.entries(fields).filter(([, v]) => v !== "" && v !== 0 && !(Array.isArray(v) && v.length === 0))
      );
      if (Object.keys(cleaned).length === 0) { setEditError("수정할 필드를 하나 이상 입력하세요"); setEditLoading(false); return; }
      const res = await editProduct(editProductId.trim(), cleaned, true);
      setEditResult(res);
      if (!res.ok) setEditError(res.error ?? res.errors?.join("\n") ?? "수정 실패");
    } catch (e) { setEditError(String(e)); }
    finally { setEditLoading(false); }
  }

  // 팝업 관리 상태
  const [popupLoading, setPopupLoading] = useState<string | null>(null);
  const [popupScanRes, setPopupScanRes] = useState<PopupScanResult | null>(null);
  const [popupHandleRes, setPopupHandleRes] = useState<PopupHandleResult | null>(null);
  const [popupStatusRes, setPopupStatusRes] = useState<PopupStatusResult | null>(null);
  const [popupMsg, setPopupMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function handlePopupUnblock() {
    setPopupLoading("unblock");
    setPopupMsg(null);
    try {
      const res = await popupUnblock();
      setPopupMsg({ ok: res.ok, text: res.ok ? `차단 해제 완료 (${res.methods?.join(", ")})` : (res.error ?? "실패") });
    } catch (e) { setPopupMsg({ ok: false, text: String(e) }); }
    finally { setPopupLoading(null); }
  }

  async function handlePopupScan() {
    setPopupLoading("scan");
    setPopupScanRes(null);
    try { setPopupScanRes(await popupScan()); }
    catch (e) { setPopupScanRes({ ok: false, error: String(e) }); }
    finally { setPopupLoading(null); }
  }

  async function handlePopupHandle() {
    setPopupLoading("handle");
    setPopupHandleRes(null);
    try { setPopupHandleRes(await popupHandle()); }
    catch (e) { setPopupHandleRes({ ok: false, error: String(e) }); }
    finally { setPopupLoading(null); }
  }

  async function handlePopupStatus() {
    setPopupLoading("status");
    try { setPopupStatusRes(await popupStatus()); }
    catch (e) { setPopupStatusRes({ ok: false, error: String(e) } as PopupStatusResult); }
    finally { setPopupLoading(null); }
  }

  // 카테고리 캐시 상태
  const [catCache, setCatCache] = useState<{ exists?: boolean; count?: number; built_at?: string } | null>(null);
  const [catBuilding, setCatBuilding] = useState(false);
  const [catSearch, setCatSearch] = useState("");
  const [catResults, setCatResults] = useState<{ id: string; name: string; path: string }[]>([]);

  useEffect(() => {
    if (tab !== "auto") return;
    getCategoryCacheInfo().then(res => { if (res.ok) setCatCache(res); }).catch(() => {});
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleBuildCache() {
    setCatBuilding(true);
    try {
      const res = await buildCategoryCache();
      if (res.ok) setCatCache({ exists: true, count: res.count, built_at: new Date().toLocaleTimeString() });
      else setAutoError(res.error ?? "캐시 구축 실패");
    } catch (e) { setAutoError(String(e)); }
    finally { setCatBuilding(false); }
  }

  async function handleCatSearch(q: string) {
    setCatSearch(q);
    if (!q || q.length < 1) { setCatResults([]); return; }
    try {
      const res = await searchCategories(q);
      setCatResults(res.results ?? []);
    } catch { setCatResults([]); }
  }

  async function handleAutoRegister() {
    setAutoLoading(true);
    setAutoError(null);
    setAutoResult(null);
    try {
      const data = JSON.parse(autoData);
      const res = await autoRegisterProduct(data, true);
      setAutoResult(res);
      if (!res.ok) setAutoError(res.error ?? res.errors?.join("\n") ?? "자동 등록 실패");
    } catch (e) {
      setAutoError(String(e));
    } finally {
      setAutoLoading(false);
    }
  }

  async function handleRenderDesc() {
    setDescLoading(true);
    setDescError(null);
    setDescHtml(null);
    try {
      const data = JSON.parse(descData);
      const res = await renderDescription(selectedSections, data);
      if (res.ok && res.html) setDescHtml(res.html);
      else setDescError(res.error ?? "렌더링 실패");
    } catch (e) {
      setDescError(String(e));
    } finally {
      setDescLoading(false);
    }
  }

  async function handleOpenSellerCenter(pageKey: SellerCenterPageKey) {
    setOpeningPage(pageKey);
    setOpenMsg(null);
    try {
      const res = await openSellerCenter(pageKey);
      setOpenMsg({ ok: res.ok, text: res.message ?? res.error ?? "" });
    } catch (e) {
      setOpenMsg({ ok: false, text: String(e) });
    } finally {
      setOpeningPage(null);
      setTimeout(() => setOpenMsg(null), 4000);
    }
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: "list",     label: "상품 목록" },
    { id: "register", label: "상품 등록" },
    { id: "bulk",     label: "일괄 등록" },
    { id: "desc",     label: "상세설명 빌더" },
    { id: "auto",     label: "자동 등록" },
    { id: "edit",     label: "상품 수정" },
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
      <AgentCommandBar />
      <ProductDetailDrawer
        productId={drawerProductId}
        onClose={() => setDrawerProductId(null)}
      />
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
                    {data.rows.map((row, i) => {
                      const pidIdx = findProductIdIndex(data.headers!);
                      const pid = extractProductId(row, pidIdx);
                      return (
                        <tr
                          key={i}
                          onClick={() => {
                            if (pid) {
                              setDrawerProductId(pid);
                              setEditProductId(pid);
                            }
                          }}
                          className={`${i % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"} ${pid ? "cursor-pointer hover:bg-[#FFF7ED] transition-colors" : ""}`}
                        >
                          {row.map((cell, j) => (
                            <td key={j} className="px-3 py-2 text-[#374151] whitespace-nowrap">{cell}</td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p className="text-xs text-[#9CA3AF] px-3 py-2 border-t border-[#E5E7EB]">
                  행을 클릭하면 상품 상세를 확인할 수 있습니다.
                </p>
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

            {/* 셀러센터 열기 */}
            <div className="flex justify-end">
              <button
                onClick={() => handleOpenSellerCenter("list")}
                disabled={openingPage === "list"}
                className="text-xs px-3 py-1.5 rounded-lg border border-[#03C75A] text-[#03C75A] hover:bg-[#F0FDF4] disabled:opacity-50 transition-colors"
              >
                {openingPage === "list" ? "이동 중…" : "셀러센터 상품 목록 열기 →"}
              </button>
            </div>
          </div>
        )}

        {/* ── 상품 등록 탭 ── */}
        {tab === "register" && (
          <div className="space-y-4">
            {/* CDP 열기 버튼 */}
            <div className="border border-[#03C75A]/30 bg-[#F0FDF4] rounded-xl p-5 space-y-3">
              <div>
                <p className="text-sm font-semibold text-[#111827]">셀러센터에서 직접 등록</p>
                <p className="text-xs text-[#6B7280] mt-1">
                  로그인된 CDP 브라우저를 상품 등록 페이지로 이동합니다. 브라우저에서 직접 작성하세요.
                </p>
              </div>
              <button
                onClick={() => handleOpenSellerCenter("register")}
                disabled={openingPage === "register"}
                className="w-full py-3 rounded-xl bg-[#03C75A] text-white text-sm font-semibold hover:bg-[#02A84A] disabled:opacity-50 transition-colors"
              >
                {openingPage === "register" ? "브라우저 이동 중…" : "셀러센터 상품 등록 페이지 열기"}
              </button>
              {openMsg && (
                <p className={`text-xs text-center ${openMsg.ok ? "text-green-700" : "text-red-600"}`}>
                  {openMsg.ok ? "✓ " : "✗ "}{openMsg.text}
                </p>
              )}
            </div>

            {/* 5단계 체크리스트 */}
            <p className="text-xs text-[#6B7280]">등록 전 아래 항목을 순서대로 완료하세요.</p>
            <div className="space-y-2">
              {REGISTER_STEPS.map((s) => (
                <div key={s.step} className="flex gap-3 items-start border border-[#E5E7EB] rounded-xl p-3 bg-white">
                  <span className={`text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center shrink-0 ${
                    s.required ? "bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA]" : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]"
                  }`}>
                    {s.step}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-[#111827]">
                      {s.title}{s.required && <span className="ml-1 text-[#DC2626]">*</span>}
                    </p>
                    <p className="text-xs text-[#6B7280] mt-0.5">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── 상세설명 빌더 탭 ── */}
        {tab === "desc" && (
          <div className="space-y-4">
            {/* 템플릿 선택기 */}
            <div className="border border-[#E5E7EB] rounded-xl p-3 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-[#111827]">저장된 템플릿</p>
                <button onClick={loadTemplates} disabled={tmplLoading}
                  className="text-xs text-[#6B7280] hover:text-[#374151] disabled:opacity-40">
                  {tmplLoading ? "로딩…" : "새로고침"}
                </button>
              </div>
              {templates.length === 0 && !tmplLoading && (
                <p className="text-xs text-[#9CA3AF]">저장된 템플릿 없음 — 상세설명 생성 후 [템플릿 저장] 버튼으로 추가하세요.</p>
              )}
              {templates.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {templates.map((t) => (
                    <div key={t.id} className="flex items-center gap-1 border border-[#E5E7EB] rounded-lg bg-[#F9FAFB] pr-1">
                      <button
                        onClick={() => handleLoadTemplate(t.id)}
                        className="text-xs px-2.5 py-1.5 text-[#1D4ED8] font-medium hover:bg-[#EFF6FF] rounded-lg transition-colors"
                      >
                        {t.name}
                        {t.category && <span className="ml-1 text-[#9CA3AF]">({t.category})</span>}
                      </button>
                      <button onClick={() => handleDeleteTemplate(t.id, t.name)}
                        className="text-[#9CA3AF] hover:text-[#DC2626] text-xs px-1">✕</button>
                    </div>
                  ))}
                </div>
              )}
              {tmplMsg && (
                <p className={`text-xs ${tmplMsg.ok ? "text-[#16A34A]" : "text-[#DC2626]"}`}>
                  {tmplMsg.ok ? "✓ " : "✗ "}{tmplMsg.text}
                </p>
              )}
            </div>

            {/* 섹션 선택 */}
            <div>
              <p className="text-sm font-semibold text-[#111827] mb-2">섹션 선택</p>
              <p className="text-xs text-[#9CA3AF] mb-3">필수 섹션(Hero, 배송)은 항상 포함됩니다.</p>
              <div className="grid grid-cols-2 gap-2">
                {descSections.map((s) => {
                  const active = selectedSections.includes(s.key);
                  return (
                    <button
                      key={s.key}
                      onClick={() => toggleSection(s.key, s.required)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-left text-xs transition-colors ${
                        s.required
                          ? "bg-[#F0FDF4] border-[#03C75A] text-[#065F46] cursor-default"
                          : active
                          ? "bg-[#EFF6FF] border-[#1D4ED8] text-[#1D4ED8]"
                          : "bg-white border-[#E5E7EB] text-[#6B7280] hover:bg-[#F9FAFB]"
                      }`}
                    >
                      <span className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 text-[10px] font-bold ${
                        active || s.required
                          ? "bg-[#03C75A] border-[#03C75A] text-white"
                          : "border-[#D1D5DB]"
                      }`}>
                        {(active || s.required) ? "✓" : ""}
                      </span>
                      <span className="font-medium">{s.label}</span>
                      {s.required && <span className="ml-auto text-[10px] text-[#03C75A] font-semibold">필수</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* 상품 데이터 입력 */}
            <div>
              <p className="text-sm font-semibold text-[#111827] mb-2">상품 데이터 (JSON)</p>
              <textarea
                value={descData}
                onChange={(e) => setDescData(e.target.value)}
                rows={10}
                className="w-full border border-[#E5E7EB] rounded-xl p-3 text-xs font-mono text-[#374151] focus:outline-none focus:ring-1 focus:ring-[#1D4ED8] resize-y"
              />
            </div>

            {/* GPT 생성 섹션 */}
            <div className="border border-[#E5E7EB] rounded-xl p-3 space-y-2">
              <p className="text-xs font-semibold text-[#111827]">GPT로 생성 <span className="text-[#9CA3AF] font-normal">(이미지 Vision 지원)</span></p>
              <textarea
                value={gptImages}
                onChange={(e) => setGptImages(e.target.value)}
                rows={3}
                placeholder={"이미지 URL 또는 경로 (한 줄에 하나)\nhttps://example.com/product.jpg\nC:/images/product.png"}
                className="w-full border border-[#E5E7EB] rounded-lg p-2 text-xs font-mono text-[#374151] focus:outline-none focus:ring-1 focus:ring-[#16A34A] resize-none"
              />
              <div className="flex gap-1">
                <button onClick={() => setGptModel("default")}
                  className={`flex-1 py-1.5 text-xs rounded-lg border font-semibold transition-colors ${gptModel==="default" ? "bg-[#16A34A] text-white border-[#16A34A]" : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]"}`}>
                  GPT-4o mini (빠름)
                </button>
                <button onClick={() => setGptModel("quality")}
                  className={`flex-1 py-1.5 text-xs rounded-lg border font-semibold transition-colors ${gptModel==="quality" ? "bg-[#16A34A] text-white border-[#16A34A]" : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]"}`}>
                  GPT-4o (Vision)
                </button>
              </div>
              <button onClick={handleGptGenerate} disabled={gptLoading || aiLoading || descLoading}
                className="w-full py-2.5 rounded-xl bg-[#16A34A] text-white text-xs font-semibold hover:bg-[#15803D] disabled:opacity-50 transition-colors">
                {gptLoading ? "GPT 생성 중…" : "🤖 GPT로 자동 생성"}
              </button>
              {gptAnalysis && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-[#6B7280] hover:text-[#374151]">이미지 분석 결과 보기</summary>
                  <pre className="mt-1 p-2 bg-[#F9FAFB] rounded border border-[#E5E7EB] overflow-x-auto text-[10px]">
                    {JSON.stringify(gptAnalysis, null, 2)}
                  </pre>
                </details>
              )}
            </div>

            {/* AI 생성 + 섹션 렌더링 버튼 */}
            <div className="flex gap-2">
              <div className="flex-1 space-y-1">
                <div className="flex gap-1">
                  <button
                    onClick={() => setAiModel("default")}
                    className={`flex-1 py-1.5 text-xs rounded-lg border font-semibold transition-colors ${
                      aiModel === "default"
                        ? "bg-[#7C3AED] text-white border-[#7C3AED]"
                        : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]"
                    }`}
                  >
                    Haiku (빠름)
                  </button>
                  <button
                    onClick={() => setAiModel("quality")}
                    className={`flex-1 py-1.5 text-xs rounded-lg border font-semibold transition-colors ${
                      aiModel === "quality"
                        ? "bg-[#7C3AED] text-white border-[#7C3AED]"
                        : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]"
                    }`}
                  >
                    Sonnet (고품질)
                  </button>
                </div>
                <button
                  onClick={handleAiGenerate}
                  disabled={aiLoading || descLoading}
                  className="w-full py-3 rounded-xl bg-[#7C3AED] text-white text-sm font-semibold hover:bg-[#6D28D9] disabled:opacity-50 transition-colors"
                >
                  {aiLoading ? "AI 생성 중…" : "✨ AI로 자동 생성"}
                </button>
              </div>
              <button
                onClick={handleRenderDesc}
                disabled={descLoading || aiLoading || selectedSections.length === 0}
                className="flex-1 py-3 rounded-xl bg-[#1D4ED8] text-white text-sm font-semibold hover:bg-[#1E40AF] disabled:opacity-50 transition-colors"
              >
                {descLoading ? "렌더링 중…" : `섹션 빌더 (${selectedSections.length}개)`}
              </button>
            </div>

            {/* 오류 */}
            {descError && (
              <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3">
                <p className="text-sm text-[#DC2626]">{descError}</p>
              </div>
            )}

            {/* 미리보기 + 템플릿 저장 */}
            {descHtml && (
              <div className="space-y-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <p className="text-sm font-semibold text-[#111827]">미리보기</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setShowSaveForm((v) => !v)}
                      className="text-xs px-3 py-1 rounded-lg border border-[#16A34A] text-[#16A34A] hover:bg-[#F0FDF4] transition-colors font-semibold"
                    >
                      {showSaveForm ? "저장 취소" : "템플릿 저장"}
                    </button>
                    <button
                      onClick={() => {
                        const blob = new Blob([descHtml], { type: "text/html" });
                        const url = URL.createObjectURL(blob);
                        window.open(url, "_blank");
                      }}
                      className="text-xs px-3 py-1 rounded-lg border border-[#1D4ED8] text-[#1D4ED8] hover:bg-[#EFF6FF] transition-colors"
                    >
                      새 탭에서 열기 →
                    </button>
                  </div>
                </div>

                {/* 템플릿 저장 폼 */}
                {showSaveForm && (
                  <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-3 space-y-2">
                    <p className="text-xs font-semibold text-[#16A34A]">템플릿으로 저장</p>
                    <div className="flex gap-2">
                      <input
                        value={tmplName}
                        onChange={(e) => setTmplName(e.target.value)}
                        placeholder="템플릿 이름 (예: 조명_표준)"
                        className="flex-1 border border-[#E5E7EB] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#16A34A]"
                      />
                      <input
                        value={tmplCategory}
                        onChange={(e) => setTmplCategory(e.target.value)}
                        placeholder="제품군 (예: 조명)"
                        className="w-28 border border-[#E5E7EB] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#16A34A]"
                      />
                      <button
                        onClick={handleSaveTemplate}
                        disabled={savingTmpl || !tmplName.trim()}
                        className="px-3 py-1.5 rounded-lg bg-[#16A34A] text-white text-xs font-semibold hover:bg-[#15803D] disabled:opacity-50 transition-colors shrink-0"
                      >
                        {savingTmpl ? "저장 중…" : "저장"}
                      </button>
                    </div>
                    <p className="text-[10px] text-[#6B7280]">
                      현재 섹션 구성({selectedSections.length}개)과 상품 데이터, HTML을 함께 저장합니다.
                    </p>
                  </div>
                )}

                <iframe
                  srcDoc={descHtml}
                  className="w-full border border-[#E5E7EB] rounded-xl"
                  style={{ height: 600 }}
                  sandbox="allow-same-origin"
                  title="상품 상세설명 미리보기"
                />
              </div>
            )}
          </div>
        )}

        {/* ── 자동 등록 탭 ── */}
        {tab === "auto" && (
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
                <button onClick={handleBuildCache} disabled={catBuilding}
                  className="px-3 py-1.5 rounded-lg bg-[#1D4ED8] text-white text-xs font-semibold hover:bg-[#1E40AF] disabled:opacity-50 transition-colors shrink-0">
                  {catBuilding ? "구축 중…" : catCache?.exists ? "재구축" : "캐시 구축"}
                </button>
                <input value={catSearch} onChange={e => handleCatSearch(e.target.value)}
                  placeholder="카테고리 검색 (예: 조명, 가구)"
                  className="flex-1 border border-[#E5E7EB] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#1D4ED8]" />
              </div>
              {catResults.length > 0 && (
                <div className="max-h-32 overflow-y-auto border border-[#E5E7EB] rounded-lg">
                  {catResults.map(c => (
                    <button key={c.id} onClick={() => {
                      try {
                        const d = JSON.parse(autoData);
                        d.category = c.name;
                        setAutoData(JSON.stringify(d, null, 2));
                        setCatResults([]); setCatSearch("");
                      } catch {}
                    }}
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

            {/* 상품 데이터 입력 */}
            <div>
              <p className="text-sm font-semibold text-[#111827] mb-2">상품 데이터 (JSON)</p>
              <p className="text-xs text-[#9CA3AF] mb-2">필수: name, price, stock, category</p>
              <textarea
                value={autoData}
                onChange={(e) => setAutoData(e.target.value)}
                rows={12}
                className="w-full border border-[#E5E7EB] rounded-xl p-3 text-xs font-mono text-[#374151] focus:outline-none focus:ring-1 focus:ring-[#F97316] resize-y"
              />
            </div>

            {/* 팝업 관리 패널 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-[#111827]">팝업 관리</p>
                {/* 폴러 상태 */}
                <div className="flex items-center gap-2">
                  {pollerInfo === null && (
                    <button onClick={refreshPollerStatus} className="text-xs text-[#9CA3AF] hover:text-[#6B7280]">
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
                        onClick={handlePollerToggle}
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
                  onClick={handlePopupUnblock}
                  disabled={popupLoading !== null}
                  className="py-2 rounded-lg border border-[#7C3AED] text-[#7C3AED] text-xs font-semibold hover:bg-[#F5F3FF] disabled:opacity-50 transition-colors"
                >
                  {popupLoading === "unblock" ? "처리 중…" : "🔓 차단 해제"}
                </button>
                <button
                  onClick={handlePopupScan}
                  disabled={popupLoading !== null}
                  className="py-2 rounded-lg border border-[#1D4ED8] text-[#1D4ED8] text-xs font-semibold hover:bg-[#EFF6FF] disabled:opacity-50 transition-colors"
                >
                  {popupLoading === "scan" ? "스캔 중…" : "🔍 팝업 스캔"}
                </button>
                <button
                  onClick={handlePopupHandle}
                  disabled={popupLoading !== null}
                  className="py-2 rounded-lg border border-[#03C75A] text-[#03C75A] text-xs font-semibold hover:bg-[#F0FDF4] disabled:opacity-50 transition-colors"
                >
                  {popupLoading === "handle" ? "처리 중…" : "✓ 팝업 자동 닫기"}
                </button>
                <button
                  onClick={handlePopupStatus}
                  disabled={popupLoading !== null}
                  className="py-2 rounded-lg border border-[#E5E7EB] text-[#6B7280] text-xs font-semibold hover:bg-[#F9FAFB] disabled:opacity-50 transition-colors"
                >
                  {popupLoading === "status" ? "조회 중…" : "📋 감지 이력"}
                </button>
              </div>

              {/* 차단 해제 결과 */}
              {popupMsg && (
                <p className={`text-xs ${popupMsg.ok ? "text-[#16A34A]" : "text-[#DC2626]"}`}>
                  {popupMsg.ok ? "✓ " : "✗ "}{popupMsg.text}
                </p>
              )}

              {/* 스캔 결과 */}
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

              {/* 처리 결과 */}
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

              {/* 감지 이력 */}
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
              onClick={handleAutoRegister}
              disabled={autoLoading}
              className="w-full py-3 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-50 transition-colors"
            >
              {autoLoading ? "폼 자동 입력 중…" : "CDP 자동 등록 (임시저장)"}
            </button>

            {/* 오류 */}
            {autoError && (
              <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3">
                <p className="text-sm text-[#DC2626] whitespace-pre-wrap">{autoError}</p>
              </div>
            )}

            {/* 결과 */}
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
                        {!r.ok && r.error && (
                          <span className="text-[#DC2626] truncate">{String(r.error)}</span>
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

            {/* CDP 상태 확인 */}
            <div className="flex justify-end">
              <button
                onClick={() => handleOpenSellerCenter("register")}
                disabled={openingPage === "register"}
                className="text-xs px-3 py-1.5 rounded-lg border border-[#03C75A] text-[#03C75A] hover:bg-[#F0FDF4] disabled:opacity-50 transition-colors"
              >
                {openingPage === "register" ? "이동 중…" : "셀러센터 등록 페이지 열기 →"}
              </button>
            </div>
          </div>
        )}

        {/* ── 상품 수정 탭 ── */}
        {tab === "edit" && (
          <div className="space-y-4">
            {/* 안내 */}
            <div className="border border-[#DDD6FE] bg-[#F5F3FF] rounded-xl p-4 space-y-1">
              <p className="text-sm font-semibold text-[#7C3AED]">CDP 상품 수정 (임시저장 전용)</p>
              <p className="text-xs text-[#6D28D9]">
                수정할 필드만 입력하세요. 빈 값은 변경하지 않습니다.
                최종 저장은 브라우저에서 직접 확인 후 눌러주세요.
              </p>
            </div>

            {/* 상품번호 입력 */}
            <div>
              <p className="text-sm font-semibold text-[#111827] mb-1.5">상품번호</p>
              <div className="flex gap-2">
                <input
                  value={editProductId}
                  onChange={e => setEditProductId(e.target.value)}
                  placeholder="예: 1234567890"
                  className="flex-1 border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[#7C3AED]"
                />
                <button
                  onClick={() => {
                    if (editProductId) {
                      window.open(`https://sell.smartstore.naver.com/#/products/${editProductId}/edit`, "_blank");
                    }
                  }}
                  disabled={!editProductId}
                  className="px-3 py-2 text-xs border border-[#7C3AED] text-[#7C3AED] rounded-xl hover:bg-[#F5F3FF] disabled:opacity-40"
                >
                  브라우저 열기
                </button>
              </div>
              <p className="text-[10px] text-[#9CA3AF] mt-1">
                상품 목록 탭에서 행을 클릭하면 상품번호가 자동 입력됩니다.
              </p>
            </div>

            {/* 수정 필드 */}
            <div>
              <p className="text-sm font-semibold text-[#111827] mb-1.5">수정 필드 (JSON)</p>
              <p className="text-xs text-[#9CA3AF] mb-2">
                수정할 항목만 값 입력 · 수정 안 할 항목은 빈 문자열/0으로 두면 건너뜁니다
              </p>
              <textarea
                value={editFields}
                onChange={e => setEditFields(e.target.value)}
                rows={10}
                className="w-full border border-[#E5E7EB] rounded-xl p-3 text-xs font-mono text-[#374151] focus:outline-none focus:ring-1 focus:ring-[#7C3AED] resize-y"
              />
            </div>

            {/* 수정 버튼 */}
            <button
              onClick={handleEdit}
              disabled={editLoading || !editProductId.trim()}
              className="w-full py-3 rounded-xl bg-[#7C3AED] text-white text-sm font-semibold hover:bg-[#6D28D9] disabled:opacity-50 transition-colors"
            >
              {editLoading ? "수정 중…" : "CDP 상품 수정 (임시저장)"}
            </button>

            {/* 오류 */}
            {editError && (
              <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3">
                <p className="text-sm text-[#DC2626] whitespace-pre-wrap">{editError}</p>
              </div>
            )}

            {/* 결과 */}
            {editResult && (
              <div className={`border rounded-xl p-4 space-y-3 ${
                editResult.ok ? "border-[#BBF7D0] bg-[#F0FDF4]" : "border-[#FECACA] bg-[#FEF2F2]"
              }`}>
                <p className={`text-sm font-semibold ${editResult.ok ? "text-[#16A34A]" : "text-[#DC2626]"}`}>
                  {editResult.ok ? `✓ 상품 ${editResult.product_id} 임시저장 완료` : "✗ 수정 실패"}
                </p>
                {editResult.steps && (
                  <div className="space-y-1">
                    {Object.entries(editResult.steps).map(([step, r]) => (
                      <div key={step} className="flex items-center gap-2 text-xs">
                        <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
                          r.ok ? "bg-[#03C75A] text-white" : "bg-[#DC2626] text-white"
                        }`}>{r.ok ? "✓" : "✗"}</span>
                        <span className="font-mono text-[#6B7280] w-24 shrink-0">{step}</span>
                        {!r.ok && r.error && <span className="text-[#DC2626] truncate">{String(r.error)}</span>}
                        {r.ok && r.selector && <span className="text-[#9CA3AF] truncate">{String(r.selector)}</span>}
                      </div>
                    ))}
                  </div>
                )}
                {editResult.hint && <p className="text-xs text-[#92400E]">{editResult.hint}</p>}
              </div>
            )}
          </div>
        )}

        {/* ── 일괄 등록 탭 ── */}
        {tab === "bulk" && (
          <div className="space-y-4">
            {/* CDP 열기 버튼 */}
            <div className="border border-[#03C75A]/30 bg-[#F0FDF4] rounded-xl p-5 space-y-3">
              <div>
                <p className="text-sm font-semibold text-[#111827]">셀러센터에서 직접 일괄 등록</p>
                <p className="text-xs text-[#6B7280] mt-1">
                  로그인된 CDP 브라우저를 일괄 등록 페이지로 이동합니다.
                </p>
              </div>
              <button
                onClick={() => handleOpenSellerCenter("list")}
                disabled={openingPage === "list"}
                className="w-full py-3 rounded-xl bg-[#03C75A] text-white text-sm font-semibold hover:bg-[#02A84A] disabled:opacity-50 transition-colors"
              >
                {openingPage === "list" ? "브라우저 이동 중…" : "셀러센터 상품 관리 열기"}
              </button>
              {openMsg && (
                <p className={`text-xs text-center ${openMsg.ok ? "text-green-700" : "text-red-600"}`}>
                  {openMsg.ok ? "✓ " : "✗ "}{openMsg.text}
                </p>
              )}
            </div>

            {/* 안내 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 bg-white space-y-3">
              <p className="text-sm font-semibold text-[#111827]">CSV 일괄 등록 순서</p>
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
          </div>
        )}
      </div>
    </div>
  );
}
