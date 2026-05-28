"use client";
/** BlogClient — 블로그 현황 / 글쓰기 요청 / 발행 이력 탭 */
import { useState } from "react";

type Tab = "status" | "write" | "history";

const BLOG_FEATURES = [
  {
    key: "blog_write",
    label: "글쓰기",
    description: "블로그 포스트 초안 작성 및 dry-run 저장. 실제 발행은 승인 게이트 통과 후 진행됩니다.",
    status: "implemented",
  },
  {
    key: "blog_assets",
    label: "에셋 관리",
    description: "이미지·첨부파일 업로드 및 블로그 에셋 목록 조회.",
    status: "implemented",
  },
  {
    key: "blog_analytics",
    label: "통계 조회",
    description: "블로그 방문자 수, 조회수, 공감 수 등 통계 데이터 수집.",
    status: "planned",
  },
  {
    key: "blog_seo",
    label: "SEO 최적화",
    description: "태그·카테고리 자동 추천, 제목 최적화 제안.",
    status: "planned",
  },
];

const STATUS_BADGE: Record<string, string> = {
  implemented: "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]",
  planned:     "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]",
  paused:      "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
};

const CATEGORIES = ["일반", "건설·시공", "공사관리", "노무·안전", "장비·자재", "계약·하도급", "기타"];

interface WriteForm {
  title: string;
  body: string;
  category: string;
}

export default function BlogClient() {
  const [tab, setTab] = useState<Tab>("status");

  const [form, setForm] = useState<WriteForm>({ title: "", body: "", category: "" });
  const [dryRunResult, setDryRunResult] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const TABS: { id: Tab; label: string }[] = [
    { id: "status",  label: "블로그 현황" },
    { id: "write",   label: "글쓰기 요청" },
    { id: "history", label: "발행 이력" },
  ];

  const handleDryRun = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    setDryRunResult(null);
    // placeholder: 실제 API 엔드포인트 구현 전 mock 응답
    await new Promise((r) => setTimeout(r, 600));
    setDryRunResult(
      JSON.stringify(
        { status: "dry_run_saved", title: form.title, category: form.category || "일반", body_length: form.body.length },
        null,
        2,
      ),
    );
    setSaving(false);
  };

  return (
    <div className="space-y-4">
      {/* 승인 후 발행 안내 배너 */}
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

      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-lg font-bold text-[#111827]">네이버 블로그</span>
          <span className="text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-2 py-0.5 rounded font-semibold">승인 필요</span>
        </div>

        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors ${
                tab === t.id
                  ? "border-[#F97316] text-[#F97316] font-semibold"
                  : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 블로그 현황 ── */}
        {tab === "status" && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {BLOG_FEATURES.map((f) => (
              <div key={f.key} className="border border-[#E5E7EB] rounded-xl p-4 bg-white">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-sm font-bold text-[#111827]">{f.label}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_BADGE[f.status] ?? STATUS_BADGE.planned}`}>
                    {f.status}
                  </span>
                </div>
                <p className="text-xs text-[#6B7280]">{f.description}</p>
                <p className="text-xs font-mono text-[#9CA3AF] mt-1.5">{f.key}</p>
              </div>
            ))}
          </div>
        )}

        {/* ── 글쓰기 요청 ── */}
        {tab === "write" && (
          <div className="space-y-4 max-w-2xl">
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-[#374151] mb-1">제목 *</label>
                <input
                  type="text"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="블로그 포스트 제목을 입력하세요"
                  className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827] placeholder-[#9CA3AF]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#374151] mb-1">카테고리</label>
                <select
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827]">
                  <option value="">카테고리 선택 (선택사항)</option>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#374151] mb-1">본문</label>
                <textarea
                  value={form.body}
                  onChange={(e) => setForm({ ...form, body: e.target.value })}
                  placeholder="블로그 본문 내용을 입력하세요"
                  rows={8}
                  className="w-full border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827] placeholder-[#9CA3AF] resize-y"
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleDryRun}
                disabled={saving || !form.title.trim()}
                className="px-4 py-2 bg-[#F97316] text-white text-sm font-semibold rounded-lg hover:bg-[#EA6C0A] disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                {saving ? "저장 중…" : "초안 저장 (dry-run)"}
              </button>
              <p className="text-xs text-[#6B7280]">실제 발행은 승인 후 별도 진행됩니다.</p>
            </div>

            {dryRunResult && (
              <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4">
                <p className="text-xs font-semibold text-[#16A34A] mb-2">초안 저장 완료 (dry-run)</p>
                <pre className="text-xs text-[#166534] font-mono whitespace-pre-wrap">{dryRunResult}</pre>
              </div>
            )}
          </div>
        )}

        {/* ── 발행 이력 ── */}
        {tab === "history" && (
          <div className="border border-[#E5E7EB] rounded-xl p-8 bg-white text-center">
            <p className="text-sm font-medium text-[#6B7280]">발행 이력 없음</p>
            <p className="text-xs text-[#9CA3AF] mt-1">승인 후 발행된 블로그 포스트가 여기에 표시됩니다.</p>
          </div>
        )}
      </div>
    </div>
  );
}
