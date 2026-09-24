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
import { TABS, type Tab } from "./components/tabConstants";
import { findProductIdIndex, extractProductId } from "./components/helpers";
import RegisterTab from "./components/RegisterTab";
import BulkTab from "./components/BulkTab";
import DescTab from "./components/DescTab";
import AutoTab from "./components/AutoTab";
import EditTab from "./components/EditTab";
import ProductListTab from "./components/ProductListTab";

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
  // 템플릿 기반 수정 모드: 불러온 템플릿 HTML 을 베이스로 AI 가 새 상품에 맞게 수정
  const [templateBase, setTemplateBase]        = useState<string | null>(null);
  const [useTemplateBase, setUseTemplateBase]  = useState(true);

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
      if (t.html)   { setDescHtml(t.html); setTemplateBase(t.html); setUseTemplateBase(true); }
      setTmplMsg({ ok: true, text: `"${t.name}" 템플릿 불러옴 — AI 생성 시 이 템플릿 기반으로 수정합니다` });
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
  const [descNotice, setDescNotice] = useState<string | null>(null);

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
  const [gptImages, setGptImages] = useState<string>("");
  const [gptAnalysis, setGptAnalysis] = useState<Record<string, unknown> | null>(null);

  // 2026-09-24: 앱 런타임 AI 생성(GPT/Claude API 직접호출) 제거 — 더 이상 백엔드
  // ai-generate/gpt-generate 엔드포인트를 호출하지 않고 즉시 안내만 표시한다.
  // 실제 상세설명 문구는 Claude Code(MCP)가 작성해 renderDescription/saveTemplate로 저장한다.
  const AI_REMOVED_NOTICE = "앱 내 AI 채팅은 제거되었습니다 — AI 작업은 Claude Code(MCP: haehan-orchestrator)로 합니다.";

  function handleGptGenerate() {
    setDescError(null);
    setGptAnalysis(null);
    setDescHtml(null);
    setDescNotice(AI_REMOVED_NOTICE);
  }

  function handleAiGenerate() {
    setDescError(null);
    setDescHtml(null);
    setDescNotice(AI_REMOVED_NOTICE);
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
        {/* 상위 탭 바 (3개) — 등록 3종·수정은 '상품 등록' 하위로 통합 */}
        <div className="flex gap-1 border-b border-[#E5E7EB] mb-3 overflow-x-auto">
          {[
            { id: "list" as Tab, label: "📋 상품 보기", group: ["list"] },
            { id: "register" as Tab, label: "➕ 상품 등록", group: ["register", "bulk", "auto", "edit"] },
            { id: "desc" as Tab, label: "🎨 상세설명", group: ["desc"] },
          ].map((p) => {
            const active = p.group.includes(tab);
            return (
              <button
                key={p.id}
                onClick={() => setTab(p.id)}
                className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors whitespace-nowrap ${
                  active ? "border-[#F97316] text-[#F97316] font-semibold" : "border-transparent text-[#6B7280] hover:text-[#111827]"
                }`}
              >
                {p.label}
              </button>
            );
          })}
        </div>
        {/* '상품 등록' 하위 탭 */}
        {["register", "bulk", "auto", "edit"].includes(tab) && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {[
              { id: "register" as Tab, label: "단일 등록" },
              { id: "bulk" as Tab, label: "일괄 등록" },
              { id: "auto" as Tab, label: "자동 등록" },
              { id: "edit" as Tab, label: "상품 수정" },
            ].map((s) => (
              <button
                key={s.id}
                onClick={() => setTab(s.id)}
                className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                  tab === s.id ? "bg-[#F97316] text-white border-[#F97316]" : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        )}

        {tab === "list" && (
          <ProductListTab
            data={data}
            loading={loading}
            error={error}
            openingPage={openingPage}
            findProductIdIndex={findProductIdIndex}
            extractProductId={extractProductId}
            onCollect={handleCollect}
            onLoad={handleLoad}
            onOpenSellerCenter={handleOpenSellerCenter}
            onRowClick={(pid) => {
              setDrawerProductId(pid);
              setEditProductId(pid);
            }}
          />
        )}

        {tab === "register" && (
          <RegisterTab
            openingPage={openingPage}
            openMsg={openMsg}
            onOpenSellerCenter={handleOpenSellerCenter}
          />
        )}

        {tab === "bulk" && (
          <BulkTab
            openingPage={openingPage}
            openMsg={openMsg}
            onOpenSellerCenter={handleOpenSellerCenter}
          />
        )}

        {tab === "desc" && (
          <DescTab
            templates={templates}
            tmplLoading={tmplLoading}
            savingTmpl={savingTmpl}
            tmplName={tmplName}
            tmplCategory={tmplCategory}
            tmplMsg={tmplMsg}
            showSaveForm={showSaveForm}
            descSections={descSections}
            selectedSections={selectedSections}
            descData={descData}
            descHtml={descHtml}
            descLoading={descLoading}
            descError={descError}
            descNotice={descNotice}
            aiLoading={aiLoading}
            aiModel={aiModel}
            gptLoading={gptLoading}
            gptModel={gptModel}
            gptImages={gptImages}
            gptAnalysis={gptAnalysis}
            templateBase={templateBase}
            useTemplateBase={useTemplateBase}
            onToggleTemplateBase={setUseTemplateBase}
            onLoadTemplates={loadTemplates}
            onLoadTemplate={handleLoadTemplate}
            onDeleteTemplate={handleDeleteTemplate}
            onSaveTemplate={handleSaveTemplate}
            onToggleSection={toggleSection}
            onSetDescData={setDescData}
            onSetGptImages={setGptImages}
            onSetGptModel={setGptModel}
            onSetAiModel={setAiModel}
            onGptGenerate={handleGptGenerate}
            onAiGenerate={handleAiGenerate}
            onRenderDesc={handleRenderDesc}
            onSetTmplName={setTmplName}
            onSetTmplCategory={setTmplCategory}
            onSetShowSaveForm={setShowSaveForm}
          />
        )}

        {tab === "auto" && (
          <AutoTab
            autoData={autoData}
            autoResult={autoResult}
            autoLoading={autoLoading}
            autoError={autoError}
            pollerInfo={pollerInfo}
            popupLoading={popupLoading}
            popupScanRes={popupScanRes}
            popupHandleRes={popupHandleRes}
            popupStatusRes={popupStatusRes}
            popupMsg={popupMsg}
            catCache={catCache}
            catBuilding={catBuilding}
            catSearch={catSearch}
            catResults={catResults}
            openingPage={openingPage}
            onSetAutoData={setAutoData}
            onAutoRegister={handleAutoRegister}
            onRefreshPollerStatus={refreshPollerStatus}
            onPollerToggle={handlePollerToggle}
            onPopupUnblock={handlePopupUnblock}
            onPopupScan={handlePopupScan}
            onPopupHandle={handlePopupHandle}
            onPopupStatus={handlePopupStatus}
            onBuildCache={handleBuildCache}
            onCatSearch={handleCatSearch}
            onCatResultSelect={(name) => {
              try {
                const d = JSON.parse(autoData);
                d.category = name;
                setAutoData(JSON.stringify(d, null, 2));
                setCatResults([]);
                setCatSearch("");
              } catch {}
            }}
            onOpenSellerCenter={handleOpenSellerCenter}
          />
        )}

        {tab === "edit" && (
          <EditTab
            editProductId={editProductId}
            editFields={editFields}
            editResult={editResult}
            editLoading={editLoading}
            editError={editError}
            onSetEditProductId={setEditProductId}
            onSetEditFields={setEditFields}
            onEdit={handleEdit}
          />
        )}
      </div>
    </div>
  );
}
