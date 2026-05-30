"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";

const AUTH = typeof btoa !== "undefined"
  ? `Basic ${btoa("owner:haehan2024!")}`
  : "";

interface OAuthStatus {
  ok: boolean;
  status: string;
  scopes: string[];
  has_upload_scope: boolean;
  channel?: { title: string; id: string };
  error?: string;
}

const SCOPE_LABELS: Record<string, string> = {
  "https://www.googleapis.com/auth/youtube.force-ssl": "YouTube 읽기/기본",
  "https://www.googleapis.com/auth/youtube.upload":    "YouTube 업로드 ✅",
  "https://www.googleapis.com/auth/youtube.readonly":  "YouTube 읽기 전용",
  "https://www.googleapis.com/auth/userinfo.email":    "이메일 확인",
  "https://www.googleapis.com/auth/userinfo.profile":  "프로필 확인",
  "openid":                                            "OpenID",
};

// ── 업로드 카드 ───────────────────────────────────────────────────────────────
function UploadCard({ hasUpload }: { hasUpload: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile]           = useState<File | null>(null);
  const [title, setTitle]         = useState("");
  const [desc, setDesc]           = useState("");
  const [privacy, setPrivacy]     = useState("public");
  const [tags, setTags]           = useState("");
  const [publishAt, setPublishAt] = useState("");   // ISO 8601 예약 게시 시각
  const [scheduled, setScheduled] = useState(false);
  const [plan, setPlan]           = useState<Record<string, unknown> | null>(null);
  const [planPath, setPlanPath]   = useState("");
  const [step, setStep]           = useState<"form"|"review"|"done">("form");
  const [loading, setLoading]     = useState(false);
  const [result, setResult]       = useState<{ ok: boolean; msg: string; videoId?: string } | null>(null);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, ""));
  };

  const handlePrepare = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title || file.name.replace(/\.[^.]+$/, ""));
      fd.append("description", desc);
      fd.append("privacy", scheduled ? "private" : privacy);
      fd.append("tags", tags);
      if (scheduled && publishAt) fd.append("publish_at", new Date(publishAt).toISOString());
      const r = await fetch(`${API_BASE}/api/v1/youtube/upload/prepare`, {
        method: "POST",
        headers: { Authorization: AUTH },
        body: fd,
      });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.detail || d.error || "플랜 생성 실패");
      setPlan(d.plan);
      setPlanPath(d.plan_path);
      setStep("review");
    } catch (e) {
      setResult({ ok: false, msg: String(e) });
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = async () => {
    setLoading(true);
    setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/v1/youtube/upload/execute`, {
        method: "POST",
        headers: { Authorization: AUTH, "Content-Type": "application/json" },
        body: JSON.stringify({ plan_path: planPath, confirm: "YOUTUBE_APPROVED_UPLOAD", dry_run: false }),
      });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.detail || d.result?.reason || "업로드 실패");
      const vid = d.result?.video_id || "";
      setResult({ ok: true, msg: "업로드 완료!", videoId: vid });
      setStep("done");
    } catch (e) {
      setResult({ ok: false, msg: String(e) });
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setFile(null); setTitle(""); setDesc(""); setPrivacy("public"); setTags(""); setPublishAt(""); setScheduled(false);
    setPlan(null); setPlanPath(""); setStep("form"); setResult(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const meta = plan ? (plan.metadata as Record<string, unknown>) : null;
  const PRIVACY_LABEL: Record<string, string> = { public: "공개", private: "비공개", unlisted: "미등록" };

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 space-y-4">
      <p className="text-sm font-bold text-[#111827]">영상 업로드</p>

      {!hasUpload && (
        <div className="bg-[#FFF7ED] border border-[#FED7AA] rounded-xl p-3 text-xs text-[#92400E]">
          ⚠ 업로드 권한(youtube.upload)이 없습니다. 먼저 OAuth 재인증이 필요합니다.
        </div>
      )}

      {/* STEP 1: 파일 선택 폼 */}
      {step === "form" && (
        <div className="space-y-3">
          {/* 파일 드롭존 */}
          <div
            onClick={() => fileRef.current?.click()}
            className="border-2 border-dashed border-[#E5E7EB] rounded-xl p-6 text-center cursor-pointer hover:border-[#F97316] transition-colors"
          >
            {file ? (
              <div>
                <p className="text-sm font-semibold text-[#111827]">{file.name}</p>
                <p className="text-xs text-[#9CA3AF] mt-1">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
              </div>
            ) : (
              <div>
                <p className="text-sm text-[#6B7280]">영상 파일을 클릭해서 선택</p>
                <p className="text-xs text-[#9CA3AF] mt-1">mp4, mov, mkv, webm, avi</p>
              </div>
            )}
          </div>
          <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,.webm,.avi" className="hidden" onChange={handleFile} />

          {/* 메타데이터 */}
          <input
            value={title} onChange={e => setTitle(e.target.value)}
            placeholder="제목"
            className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]"
          />
          <textarea
            value={desc} onChange={e => setDesc(e.target.value)}
            placeholder="설명 (선택)"
            rows={2}
            className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] resize-none"
          />
          <input
            value={tags} onChange={e => setTags(e.target.value)}
            placeholder="태그 (쉼표 구분, 선택)"
            className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-[#F97316]"
          />
          {/* 예약 게시 토글 */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <div
              onClick={() => setScheduled(v => !v)}
              className={`w-10 h-5 rounded-full transition-colors relative ${scheduled ? "bg-[#F97316]" : "bg-[#E5E7EB]"}`}
            >
              <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${scheduled ? "translate-x-5" : "translate-x-0.5"}`} />
            </div>
            <span className="text-sm text-[#374151]">예약 게시</span>
          </label>

          {scheduled ? (
            <div className="space-y-1">
              <input
                type="datetime-local"
                value={publishAt}
                onChange={e => setPublishAt(e.target.value)}
                min={new Date(Date.now() + 15 * 60 * 1000).toISOString().slice(0, 16)}
                className="w-full border border-[#F97316] rounded-xl px-3 py-2 text-sm focus:outline-none bg-white"
              />
              <p className="text-xs text-[#9CA3AF]">예약 게시 시 비공개로 업로드 후 지정 시각에 자동 공개됩니다.</p>
            </div>
          ) : (
            <select
              value={privacy} onChange={e => setPrivacy(e.target.value)}
              className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] bg-white"
            >
              <option value="public">공개</option>
              <option value="unlisted">미등록</option>
              <option value="private">비공개</option>
            </select>
          )}

          <button
            onClick={handlePrepare}
            disabled={!file || !hasUpload || loading}
            className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-colors ${
              !file || !hasUpload || loading
                ? "bg-[#E5E7EB] text-[#9CA3AF] cursor-not-allowed"
                : "bg-[#F97316] text-white hover:bg-[#EA580C]"
            }`}
          >
            {loading ? "플랜 생성 중..." : "업로드 준비"}
          </button>

          {result && !result.ok && (
            <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl p-3 text-xs text-[#DC2626]">{result.msg}</div>
          )}
        </div>
      )}

      {/* STEP 2: 플랜 검토 및 최종 승인 */}
      {step === "review" && meta && (
        <div className="space-y-3">
          <div className="bg-[#F0FDF4] border border-[#BBF7D0] rounded-xl p-4 space-y-2">
            <p className="text-xs font-bold text-[#16A34A]">업로드 플랜 확인</p>
            {[
              ["제목", String(meta.title ?? "")],
              ["공개 설정", String(meta.publish_at) ? `예약 (${new Date(String(meta.publish_at)).toLocaleString("ko-KR")})` : (PRIVACY_LABEL[String(meta.privacy_status)] ?? String(meta.privacy_status))],
              ["설명", String(meta.description || "(없음)")],
              ["태그", (meta.tags as string[])?.join(", ") || "(없음)"],
            ].map(([k, v]) => (
              <div key={k} className="flex gap-2 text-xs">
                <span className="text-[#6B7280] w-20 shrink-0">{k}</span>
                <span className="text-[#111827] font-medium">{v}</span>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button onClick={reset} className="py-2.5 rounded-xl border border-[#E5E7EB] text-sm text-[#6B7280] hover:bg-[#F3F4F6]">
              취소
            </button>
            <button
              onClick={handleExecute}
              disabled={loading}
              className={`py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                loading ? "bg-[#E5E7EB] text-[#9CA3AF] cursor-not-allowed" : "bg-[#F97316] text-white hover:bg-[#EA580C]"
              }`}
            >
              {loading ? "업로드 중..." : "최종 승인 · 업로드"}
            </button>
          </div>

          {result && !result.ok && (
            <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl p-3 text-xs text-[#DC2626]">{result.msg}</div>
          )}
        </div>
      )}

      {/* STEP 3: 완료 */}
      {step === "done" && result?.ok && (
        <div className="space-y-3">
          <div className="bg-[#F0FDF4] border border-[#BBF7D0] rounded-xl p-4 text-center space-y-2">
            <p className="text-sm font-bold text-[#16A34A]">✓ 업로드 완료</p>
            {result.videoId && (
              <a
                href={`https://studio.youtube.com/video/${result.videoId}/edit`}
                target="_blank" rel="noopener noreferrer"
                className="block text-xs text-[#1D4ED8] hover:underline"
              >
                YouTube Studio에서 확인 →
              </a>
            )}
          </div>
          <button onClick={reset} className="w-full py-2.5 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C]">
            새 영상 업로드
          </button>
        </div>
      )}
    </div>
  );
}

export default function YouTubePage() {
  const [status, setStatus]     = useState<OAuthStatus | null>(null);
  const [loading, setLoading]   = useState(false);
  const [authUrl, setAuthUrl]   = useState("");
  const [urlLoading, setUrlLoading] = useState(false);
  const [copied, setCopied]     = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/oauth/youtube/status`,
        { headers: { Authorization: AUTH } });
      setStatus(await r.json());
    } catch { setStatus({ ok: false, status: "error", scopes: [], has_upload_scope: false }); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const getAuthUrl = async () => {
    setUrlLoading(true);
    setAuthUrl("");
    try {
      const r = await fetch(
        `${API_BASE}/api/v1/oauth/youtube/auth-url?scope=force-ssl+upload`,
        { headers: { Authorization: AUTH } });
      const d = await r.json();
      setAuthUrl(d.auth_url || "");
    } finally { setUrlLoading(false); }
  };

  const copy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const hasUpload = status?.has_upload_scope;
  const channel   = status?.channel;

  return (
    <PageShell title="YouTube 관리" description="OAuth 인증 · 업로드 · 시장 조사" chatDomain="youtube">
      <div className="space-y-6">

        {/* 채널 상태 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-bold text-[#111827]">YouTube OAuth 상태</p>
            <button onClick={loadStatus} disabled={loading}
              className="text-xs text-[#9CA3AF] hover:text-[#6B7280] disabled:opacity-40">
              {loading ? "확인 중..." : "새로고침"}
            </button>
          </div>

          {status ? (
            <div className="space-y-3">
              {/* 채널 정보 */}
              <div className="flex items-center gap-3">
                {status.ok ? (
                  <span className="text-xs font-semibold px-3 py-1.5 rounded-full bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0]">
                    ✓ 인증됨
                  </span>
                ) : (
                  <span className="text-xs font-semibold px-3 py-1.5 rounded-full bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA]">
                    ✗ 미인증
                  </span>
                )}
                {channel && (
                  <div>
                    <span className="text-sm font-bold text-[#111827]">{channel.title}</span>
                    <span className="text-xs text-[#9CA3AF] ml-2">{channel.id}</span>
                  </div>
                )}
              </div>

              {/* 스코프 목록 */}
              {status.scopes.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold text-[#374151]">인증된 권한</p>
                  {status.scopes.map(s => (
                    <div key={s} className="flex items-center gap-2 text-xs">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${
                        s.includes("upload") ? "bg-[#16A34A]" : "bg-[#9CA3AF]"
                      }`} />
                      <span className={s.includes("upload") ? "text-[#16A34A] font-semibold" : "text-[#6B7280]"}>
                        {SCOPE_LABELS[s] ?? s.split("/").pop()}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* 업로드 스코프 경고 */}
              {status.ok && !hasUpload && (
                <div className="bg-[#FFF7ED] border border-[#FED7AA] rounded-xl p-3">
                  <p className="text-xs font-semibold text-[#C2410C]">⚠ 업로드 권한 없음</p>
                  <p className="text-xs text-[#92400E] mt-1">
                    현재 검색·조회만 가능합니다. 아래에서 재인증하면 업로드 권한이 추가됩니다.
                  </p>
                </div>
              )}

              {status.ok && hasUpload && (
                <div className="bg-[#F0FDF4] border border-[#BBF7D0] rounded-xl p-3">
                  <p className="text-xs font-semibold text-[#16A34A]">✓ 업로드 권한 있음</p>
                  <p className="text-xs text-[#166534] mt-1">검색·조회·업로드 모두 가능합니다.</p>
                </div>
              )}

              {status.error && (
                <p className="text-xs text-[#DC2626]">{status.error}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-[#9CA3AF]">{loading ? "확인 중..." : "상태 없음"}</p>
          )}
        </div>

        {/* OAuth 재인증 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 space-y-4">
          <div>
            <p className="text-sm font-bold text-[#111827]">YouTube OAuth 재인증</p>
            <p className="text-xs text-[#6B7280] mt-1">
              업로드 권한을 포함해서 재인증합니다. Google 계정 승인이 필요합니다.
            </p>
          </div>

          <button onClick={getAuthUrl} disabled={urlLoading}
            className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-colors ${
              urlLoading ? "bg-[#E5E7EB] text-[#9CA3AF] cursor-not-allowed"
                         : "bg-[#F97316] text-white hover:bg-[#EA580C]"
            }`}>
            {urlLoading ? "URL 생성 중..." : "YouTube 인증 URL 생성"}
          </button>

          {authUrl && (
            <div className="space-y-3">
              <div className="bg-[#F0FDF4] border border-[#BBF7D0] rounded-xl p-4 space-y-2">
                <p className="text-xs font-bold text-[#16A34A]">인증 URL이 생성되었습니다</p>
                <p className="text-xs text-[#374151]">
                  아래 URL을 브라우저에서 열고 Google 계정으로 로그인 후 권한을 승인하세요.
                  승인 후 자동으로 서버에 토큰이 저장됩니다.
                </p>
              </div>
              <div className="flex gap-2">
                <a href={authUrl} target="_blank" rel="noopener noreferrer"
                  className="flex-1 py-2 rounded-xl bg-[#F97316] text-white text-sm font-semibold text-center hover:bg-[#EA580C] transition-colors">
                  Google 인증 페이지 열기
                </a>
                <button onClick={() => copy(authUrl)}
                  className="px-3 py-2 rounded-xl border border-[#E5E7EB] text-xs text-[#6B7280] hover:bg-[#F3F4F6]">
                  {copied ? "복사됨!" : "URL 복사"}
                </button>
              </div>
              <p className="text-xs text-[#9CA3AF]">
                승인 완료 후 새로고침 버튼을 눌러 상태를 확인하세요.
              </p>
            </div>
          )}
        </div>

        {/* 영상 업로드 */}
        <UploadCard hasUpload={!!hasUpload} />

        {/* 기능 안내 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5">
          <p className="text-sm font-bold text-[#111827] mb-3">YouTube 기능</p>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "영상 검색", desc: "키워드로 YouTube 영상 검색", available: status?.ok },
              { label: "댓글 분석", desc: "영상 댓글 수집 및 분석", available: status?.ok },
              { label: "자막 수집", desc: "영상 자막 수집 (OAuth 필요)", available: status?.ok },
              { label: "시장 조사", desc: "키워드별 경쟁 분석 리포트", available: status?.ok },
              { label: "영상 업로드", desc: "YouTube Studio에 영상 업로드", available: hasUpload },
              { label: "채널 관리", desc: "채널 정보 및 영상 관리", available: hasUpload },
            ].map(f => (
              <div key={f.label} className={`border rounded-xl p-3 ${
                f.available ? "border-[#BBF7D0] bg-[#F0FDF4]" : "border-[#E5E7EB] bg-[#F9FAFB]"
              }`}>
                <div className="flex items-center gap-1.5">
                  <span className={`text-xs font-bold ${f.available ? "text-[#16A34A]" : "text-[#9CA3AF]"}`}>
                    {f.available ? "✓" : "○"}
                  </span>
                  <span className={`text-xs font-semibold ${f.available ? "text-[#16A34A]" : "text-[#6B7280]"}`}>
                    {f.label}
                  </span>
                </div>
                <p className="text-xs text-[#9CA3AF] mt-0.5">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* 시장조사 바로가기 */}
        <a href="/market-research"
          className="block bg-white border border-[#E5E7EB] rounded-2xl p-5 hover:border-[#F97316] hover:shadow-sm transition-all">
          <p className="text-sm font-bold text-[#111827]">YouTube 시장 조사 →</p>
          <p className="text-xs text-[#6B7280] mt-1">
            스마트스토어·구매대행·커머스 키워드별 영상·댓글·자막 신호 분석
          </p>
        </a>

      </div>
    </PageShell>
  );
}
