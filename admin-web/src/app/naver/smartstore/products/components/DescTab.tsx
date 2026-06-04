"use client";
import type { DescTemplate, DescriptionSection } from "@/lib/assistant/api";

interface DescTabProps {
  templates: DescTemplate[];
  tmplLoading: boolean;
  savingTmpl: boolean;
  tmplName: string;
  tmplCategory: string;
  tmplMsg: { ok: boolean; text: string } | null;
  showSaveForm: boolean;
  descSections: DescriptionSection[];
  selectedSections: string[];
  descData: string;
  descHtml: string | null;
  descLoading: boolean;
  descError: string | null;
  aiLoading: boolean;
  aiModel: "default" | "quality";
  gptLoading: boolean;
  gptModel: "default" | "quality";
  gptImages: string;
  gptAnalysis: Record<string, unknown> | null;
  templateBase: string | null;
  useTemplateBase: boolean;
  onToggleTemplateBase: (v: boolean) => void;
  onLoadTemplates: () => void;
  onLoadTemplate: (id: string) => void;
  onDeleteTemplate: (id: string, name: string) => void;
  onSaveTemplate: () => void;
  onToggleSection: (key: string, required: boolean) => void;
  onSetDescData: (v: string) => void;
  onSetGptImages: (v: string) => void;
  onSetGptModel: (v: "default" | "quality") => void;
  onSetAiModel: (v: "default" | "quality") => void;
  onGptGenerate: () => void;
  onAiGenerate: () => void;
  onRenderDesc: () => void;
  onSetTmplName: (v: string) => void;
  onSetTmplCategory: (v: string) => void;
  onSetShowSaveForm: (fn: (v: boolean) => boolean) => void;
}

export default function DescTab({
  templates, tmplLoading, savingTmpl, tmplName, tmplCategory, tmplMsg, showSaveForm,
  descSections, selectedSections, descData, descHtml, descLoading, descError,
  aiLoading, aiModel, gptLoading, gptModel, gptImages, gptAnalysis,
  templateBase, useTemplateBase, onToggleTemplateBase,
  onLoadTemplates, onLoadTemplate, onDeleteTemplate, onSaveTemplate,
  onToggleSection, onSetDescData, onSetGptImages, onSetGptModel, onSetAiModel,
  onGptGenerate, onAiGenerate, onRenderDesc,
  onSetTmplName, onSetTmplCategory, onSetShowSaveForm,
}: DescTabProps) {
  return (
    <div className="space-y-4">
      {/* 템플릿 선택기 */}
      <div className="border border-[#E5E7EB] rounded-xl p-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-[#111827]">저장된 템플릿</p>
          <button onClick={onLoadTemplates} disabled={tmplLoading}
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
                  onClick={() => onLoadTemplate(t.id)}
                  className="text-xs px-2.5 py-1.5 text-[#1D4ED8] font-medium hover:bg-[#EFF6FF] rounded-lg transition-colors"
                >
                  {t.name}
                  {t.category && <span className="ml-1 text-[#9CA3AF]">({t.category})</span>}
                </button>
                <button onClick={() => onDeleteTemplate(t.id, t.name)}
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
                onClick={() => onToggleSection(s.key, s.required)}
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
          onChange={(e) => onSetDescData(e.target.value)}
          rows={10}
          className="w-full border border-[#E5E7EB] rounded-xl p-3 text-xs font-mono text-[#374151] focus:outline-none focus:ring-1 focus:ring-[#1D4ED8] resize-y"
        />
      </div>

      {/* GPT 생성 섹션 */}
      <div className="border border-[#E5E7EB] rounded-xl p-3 space-y-2">
        <p className="text-xs font-semibold text-[#111827]">GPT로 생성 <span className="text-[#9CA3AF] font-normal">(이미지 Vision 지원)</span></p>
        <textarea
          value={gptImages}
          onChange={(e) => onSetGptImages(e.target.value)}
          rows={3}
          placeholder={"이미지 URL 또는 경로 (한 줄에 하나)\nhttps://example.com/product.jpg\nC:/images/product.png"}
          className="w-full border border-[#E5E7EB] rounded-lg p-2 text-xs font-mono text-[#374151] focus:outline-none focus:ring-1 focus:ring-[#16A34A] resize-none"
        />
        <div className="flex gap-1">
          <button onClick={() => onSetGptModel("default")}
            className={`flex-1 py-1.5 text-xs rounded-lg border font-semibold transition-colors ${gptModel==="default" ? "bg-[#16A34A] text-white border-[#16A34A]" : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]"}` }>
            GPT-4o mini (빠름)
          </button>
          <button onClick={() => onSetGptModel("quality")}
            className={`flex-1 py-1.5 text-xs rounded-lg border font-semibold transition-colors ${gptModel==="quality" ? "bg-[#16A34A] text-white border-[#16A34A]" : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]"}` }>
            GPT-4o (Vision)
          </button>
        </div>
        {templateBase && (
          <label className="flex items-center gap-2 text-xs text-[#374151] bg-[#F0FDF4] border border-[#BBF7D0] rounded-lg px-2.5 py-2 cursor-pointer">
            <input type="checkbox" checked={useTemplateBase} onChange={(e) => onToggleTemplateBase(e.target.checked)} />
            <span>📋 불러온 템플릿 기반으로 수정 <span className="text-[#9CA3AF]">(구조·톤 유지, 문구만 교체)</span></span>
          </label>
        )}
        <button onClick={onGptGenerate} disabled={gptLoading || aiLoading || descLoading}
          className="w-full py-2.5 rounded-xl bg-[#16A34A] text-white text-xs font-semibold hover:bg-[#15803D] disabled:opacity-50 transition-colors">
          {gptLoading ? "GPT 생성 중…" : (templateBase && useTemplateBase) ? "🤖 템플릿 기반 AI 수정" : "🤖 GPT로 자동 생성"}
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
              onClick={() => onSetAiModel("default")}
              className={`flex-1 py-1.5 text-xs rounded-lg border font-semibold transition-colors ${
                aiModel === "default"
                  ? "bg-[#7C3AED] text-white border-[#7C3AED]"
                  : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]"
              }`}
            >
              Haiku (빠름)
            </button>
            <button
              onClick={() => onSetAiModel("quality")}
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
            onClick={onAiGenerate}
            disabled={aiLoading || descLoading}
            className="w-full py-3 rounded-xl bg-[#7C3AED] text-white text-sm font-semibold hover:bg-[#6D28D9] disabled:opacity-50 transition-colors"
          >
            {aiLoading ? "AI 생성 중…" : "✨ AI로 자동 생성"}
          </button>
        </div>
        <button
          onClick={onRenderDesc}
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
                onClick={() => onSetShowSaveForm((v) => !v)}
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

          {showSaveForm && (
            <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-3 space-y-2">
              <p className="text-xs font-semibold text-[#16A34A]">템플릿으로 저장</p>
              <div className="flex gap-2">
                <input
                  value={tmplName}
                  onChange={(e) => onSetTmplName(e.target.value)}
                  placeholder="템플릿 이름 (예: 조명_표준)"
                  className="flex-1 border border-[#E5E7EB] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#16A34A]"
                />
                <input
                  value={tmplCategory}
                  onChange={(e) => onSetTmplCategory(e.target.value)}
                  placeholder="제품군 (예: 조명)"
                  className="w-28 border border-[#E5E7EB] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-[#16A34A]"
                />
                <button
                  onClick={onSaveTemplate}
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
  );
}
