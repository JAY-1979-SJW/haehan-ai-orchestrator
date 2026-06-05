"use client";
/** BlogClient — 블로그 초안 작성 / 초안 목록 / SEO 분석 */
import { useState, useEffect, useCallback } from "react";
import { API_BASE } from "@/lib/assistant/api";

type Tab = "write" | "drafts" | "seo";

const CATEGORIES = ["일반", "건설·시공", "공사관리", "노무·안전", "장비·자재", "계약·하도급", "기타"];

interface Draft {
  id: string;
  title: string;
  category: string;
  tags: string[];
  body_length: number;
  status: string;
  created_at: string;
  published_url: string | null;
}

interface SeoResult {
  ok: boolean;
  fallback?: boolean;
  title: Record<string, unknown>;
  body: Record<string, unknown>;
  suggested_tags: string[];
}

export default function BlogClient() {
  const [tab, setTab] = useState<Tab>("write");

  // 글쓰기
  const [title, setTitle] = useState("");
  const [body, setBody]   = useState("");
  const [category, setCat] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{ ok: boolean; msg: string } | null>(null);

  // 사진·동영상 첨부
  const [media, setMedia] = useState<{ name: string; kind: string; preview: string }[]>([]);
  const [uploading, setUploading] = useState(false);

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
    for (const file of Array.from(files)) {
      try {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch(`${API_BASE}/api/v1/naver/blog/upload`, {
          method: "POST",
          headers: { ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
          body: fd,
        });
        const d = await r.json();
        if (r.ok && d.ok) {
          setMedia(prev => [...prev, { name: d.name, kind: d.kind, preview: URL.createObjectURL(file) }]);
        } else {
          setSaveResult({ ok: false, msg: d.detail || d.error || "업로드 실패" });
        }
      } catch (e) {
        setSaveResult({ ok: false, msg: `업로드 오류: ${String(e)}` });
      }
    }
    setUploading(false);
  };

  const removeMedia = (name: string) => setMedia(prev => prev.filter(m => m.name !== name));

  // AI 글 생성
  const [aiTopic, setAiTopic] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const handleAiGenerate = async () => {
    if (!aiTopic.trim()) { setAiError("주제를 입력하세요"); return; }
    setAiLoading(true); setAiError(null);
    try {
      const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
      const r = await fetch(`${API_BASE}/api/v1/naver/blog/ai-generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
        body: JSON.stringify({ topic: aiTopic.trim() }),
      });
      const d = await r.json();
      if (!r.ok || !d.ok) { setAiError(d.error || d.detail || "생성 실패"); return; }
      setTitle(d.title || "");
      setBody(d.body || "");
      if (Array.isArray(d.tags)) setTagInput(d.tags.join(", "));
    } catch (e) {
      setAiError(e instanceof Error ? e.message : "생성 실패");
    } finally {
      setAiLoading(false);
    }
  };

  // 초안 목록
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [draftsLoading, setDraftsLoading] = useState(false);
  const [draftsTotal, setDraftsTotal] = useState(0);

  // SEO
  const [seoTitle, setSeoTitle] = useState("");
  const [seoBody,  setSeoBody]  = useState("");
  const [seoResult, setSeoResult] = useState<SeoResult | null>(null);
  const [seoLoading, setSeoLoading] = useState(false);
  const [seoError, setSeoError] = useState<string | null>(null);

  const loadDrafts = useCallback(async () => {
    setDraftsLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/naver/blog/drafts?limit=30`);
      const d = await r.json();
      setDrafts(d.items ?? []);
      setDraftsTotal(d.total ?? 0);
    } catch { /* ignore */ }
    finally { setDraftsLoading(false); }
  }, []);

  useEffect(() => {
    if (tab === "drafts") loadDrafts();
  }, [tab, loadDrafts]);

  const handleSave = async () => {
    if (!title.trim()) return;
    setSaving(true); setSaveResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/v1/naver/blog/compose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          body,
          category: category || "일반",
          tags: tagInput.split(",").map(t => t.trim()).filter(Boolean),
          media: media.map(m => m.name),
          dry_run: true,
        }),
      });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.detail || "저장 실패");
      setSaveResult({ ok: true, msg: `초안 저장 완료 (${d.draft_id})${media.length ? ` · 미디어 ${media.length}개` : ""}` });
      setTitle(""); setBody(""); setCat(""); setTagInput(""); setMedia([]);
    } catch (e) {
      setSaveResult({ ok: false, msg: String(e) });
    } finally {
      setSaving(false);
    }
  };

  const handleSeo = async () => {
    if (!seoTitle.trim() && !seoBody.trim()) return;
    setSeoLoading(true); setSeoError(null); setSeoResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/v1/naver/blog/seo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: seoTitle, body: seoBody }),
      });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.detail || "분석 실패");
      setSeoResult(d);
    } catch (e) {
      setSeoError(String(e));
    } finally {
      setSeoLoading(false);
    }
  };

  const TABS: { id: Tab; label: string }[] = [
    { id: "write",  label: "글쓰기 요청" },
    { id: "drafts", label: `초안 목록${draftsTotal ? ` (${draftsTotal})` : ""}` },
    { id: "seo",    label: "SEO 분석" },
  ];

  return (
    <div className="space-y-4">
      {/* 안내 배너 */}
      <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl px-4 py-3 flex items-start gap-3">
        <span className="text-[#F97316] text-base mt-0.5">!</span>
        <div>
          <p className="text-xs font-bold text-[#C2410C]">승인 후 발행 정책</p>
          <p className="text-xs text-[#78350F] mt-0.5">
            블로그 글은 초안 저장(dry-run)까지만 자동으로 진행됩니다.
            실제 발행은 승인 게이트 통과 후 별도로 실행됩니다.
          </p>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-[#E5E7EB] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-bold text-[#111827]">네이버 블로그</span>
          <span className="text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-2 py-0.5 rounded font-semibold">승인 필요</span>
        </div>

        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors ${
                tab === t.id ? "border-[#F97316] text-[#F97316] font-semibold" : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 글쓰기 요청 ── */}
        {tab === "write" && (
          <div className="space-y-3 max-w-2xl">
            {/* AI 글 생성 */}
            <div className="rounded-xl border border-[#FED7AA] bg-[#FFF7ED] p-3 space-y-2">
              <p className="text-xs font-semibold text-[#9A3412]">✨ 주제만 입력하면 AI가 제목·본문·태그를 써줍니다</p>
              <div className="flex gap-2">
                <input value={aiTopic} onChange={e => setAiTopic(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && !aiLoading) handleAiGenerate(); }}
                  placeholder="예: LED 간접조명 셀프 시공 후기, 캠핑 초보 장비 추천…"
                  className="flex-1 border border-[#FDBA74] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]" />
                <button onClick={handleAiGenerate} disabled={aiLoading}
                  className="px-4 py-2 rounded-lg bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-50 whitespace-nowrap">
                  {aiLoading ? "작성 중…" : "✨ AI 글 생성"}
                </button>
              </div>
              {aiError && <p className="text-xs text-[#DC2626]">{aiError}</p>}
              <p className="text-[11px] text-[#C2410C]">생성 후 아래 제목·본문·태그가 자동으로 채워집니다. 검토·수정 후 [초안 저장]하세요.</p>
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#374151] mb-1">제목 *</label>
              <input value={title} onChange={e => setTitle(e.target.value)}
                placeholder="블로그 포스트 제목"
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#374151] mb-1">카테고리</label>
              <select value={category} onChange={e => setCat(e.target.value)}
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] bg-white">
                <option value="">카테고리 선택 (선택사항)</option>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#374151] mb-1">태그 (쉼표 구분)</label>
              <input value={tagInput} onChange={e => setTagInput(e.target.value)}
                placeholder="태그1, 태그2, ..."
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#374151] mb-1">본문</label>
              <textarea value={body} onChange={e => setBody(e.target.value)}
                placeholder="블로그 본문 내용을 입력하세요"
                rows={8}
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] resize-y" />
              <p className="text-xs text-[#9CA3AF] mt-1">{body.length}자</p>
            </div>

            {/* 사진·동영상 첨부 */}
            <div>
              <label className="block text-xs font-semibold text-[#374151] mb-1">사진·동영상 첨부</label>
              <label className="inline-flex items-center gap-2 px-3 py-2 border border-dashed border-[#FDBA74] rounded-lg text-sm text-[#C2410C] bg-[#FFF7ED] cursor-pointer hover:bg-[#FFEDD5] transition-colors">
                <span>📎 {uploading ? "업로드 중…" : "이미지·동영상 선택"}</span>
                <input type="file" accept="image/*,video/*" multiple className="hidden"
                  disabled={uploading}
                  onChange={e => { handleUpload(e.target.files); e.currentTarget.value = ""; }} />
              </label>
              <p className="text-[11px] text-[#9CA3AF] mt-1">JPG·PNG·GIF·MP4·MOV 등 (개당 최대 200MB)</p>
              {media.length > 0 && (
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mt-2">
                  {media.map(m => (
                    <div key={m.name} className="relative group border border-[#E5E7EB] rounded-lg overflow-hidden bg-[#F9FAFB]">
                      {m.kind === "video"
                        ? <video src={m.preview} className="w-full h-20 object-cover" muted />
                        : <img src={m.preview} alt="" className="w-full h-20 object-cover" />}
                      <span className="absolute bottom-0 left-0 text-[9px] px-1 bg-black/50 text-white">{m.kind === "video" ? "동영상" : "사진"}</span>
                      <button onClick={() => removeMedia(m.name)} type="button"
                        className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-white text-xs leading-none hover:bg-[#DC2626]">×</button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex items-center gap-3">
              <button onClick={handleSave} disabled={saving || !title.trim()}
                className="px-4 py-2 bg-[#F97316] text-white text-sm font-semibold rounded-lg hover:bg-[#EA6C0A] disabled:opacity-50 transition-colors">
                {saving ? "저장 중…" : "초안 저장 (dry-run)"}
              </button>
              <p className="text-xs text-[#6B7280]">실제 발행은 승인 후 별도 진행됩니다.</p>
            </div>
            {saveResult && (
              <div className={`rounded-xl p-3 text-xs ${saveResult.ok ? "bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0]" : "bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA]"}`}>
                {saveResult.msg}
              </div>
            )}
          </div>
        )}

        {/* ── 초안 목록 ── */}
        {tab === "drafts" && (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <button onClick={loadDrafts} disabled={draftsLoading}
                className="px-3 py-1.5 border border-[#E5E7EB] text-xs rounded-lg text-[#6B7280] disabled:opacity-50">
                {draftsLoading ? "불러오는 중…" : "새로고침"}
              </button>
              <span className="text-xs text-[#9CA3AF]">총 {draftsTotal}건</span>
            </div>
            {drafts.length === 0 && !draftsLoading && (
              <div className="border border-[#E5E7EB] rounded-xl p-8 text-center">
                <p className="text-sm text-[#6B7280]">저장된 초안이 없습니다.</p>
              </div>
            )}
            <div className="space-y-2">
              {drafts.map(d => (
                <div key={d.id} className="border border-[#E5E7EB] rounded-xl p-3 flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-[#111827] truncate">{d.title}</p>
                    <div className="flex gap-2 mt-1 flex-wrap">
                      {d.category && <span className="text-xs bg-[#F3F4F6] text-[#374151] px-2 py-0.5 rounded">{d.category}</span>}
                      {d.tags.map(t => <span key={t} className="text-xs bg-[#EFF6FF] text-[#1D4ED8] px-2 py-0.5 rounded">{t}</span>)}
                    </div>
                    <div className="flex gap-3 mt-1 text-xs text-[#9CA3AF]">
                      <span>{d.body_length.toLocaleString()}자</span>
                      <span>{new Date(d.created_at).toLocaleString("ko-KR")}</span>
                    </div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${
                    d.status === "published" ? "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]" : "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]"
                  }`}>{d.status}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── SEO 분석 ── */}
        {tab === "seo" && (
          <div className="space-y-3 max-w-2xl">
            <div>
              <label className="block text-xs font-semibold text-[#374151] mb-1">제목</label>
              <input value={seoTitle} onChange={e => setSeoTitle(e.target.value)}
                placeholder="분석할 블로그 제목"
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#374151] mb-1">본문</label>
              <textarea value={seoBody} onChange={e => setSeoBody(e.target.value)}
                placeholder="분석할 본문 내용"
                rows={5}
                className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] resize-y" />
            </div>
            <button onClick={handleSeo} disabled={seoLoading || (!seoTitle.trim() && !seoBody.trim())}
              className="px-4 py-2 bg-[#F97316] text-white text-sm font-semibold rounded-lg hover:bg-[#EA580C] disabled:opacity-50">
              {seoLoading ? "분석 중…" : "SEO 분석"}
            </button>
            {seoError && <p className="text-xs text-[#DC2626]">오류: {seoError}</p>}
            {seoResult && (
              <div className="space-y-3">
                {/* 제목 분석 */}
                <div className="border border-[#E5E7EB] rounded-xl p-3">
                  <p className="text-xs font-semibold text-[#374151] mb-2">제목 분석</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(seoResult.title).map(([k, v]) => (
                      <div key={k} className="text-xs bg-[#F3F4F6] px-2 py-1 rounded">
                        <span className="text-[#6B7280]">{k}: </span>
                        <span className="font-medium text-[#111827]">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {/* 본문 분석 */}
                <div className="border border-[#E5E7EB] rounded-xl p-3">
                  <p className="text-xs font-semibold text-[#374151] mb-2">본문 분석</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(seoResult.body).map(([k, v]) => (
                      <div key={k} className="text-xs bg-[#F3F4F6] px-2 py-1 rounded">
                        <span className="text-[#6B7280]">{k}: </span>
                        <span className="font-medium text-[#111827]">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {/* 태그 추천 */}
                {seoResult.suggested_tags.length > 0 && (
                  <div className="border border-[#E5E7EB] rounded-xl p-3">
                    <p className="text-xs font-semibold text-[#374151] mb-2">추천 태그</p>
                    <div className="flex flex-wrap gap-1.5">
                      {seoResult.suggested_tags.map(t => (
                        <span key={t} className="text-xs bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-2 py-0.5 rounded-full">{t}</span>
                      ))}
                    </div>
                    {seoResult.fallback && <p className="text-xs text-[#9CA3AF] mt-1">* 기본 분석 모드 (브라우저 미연결)</p>}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
