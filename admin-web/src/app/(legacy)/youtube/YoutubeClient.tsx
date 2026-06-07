"use client";
/** /youtube — 셸: OAuth 상태 + UploadCard 조립 */
import { useState, useEffect, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";
import { type OAuthStatus, SCOPE_LABELS } from "./youtubeShared";
import { UploadCard } from "./UploadCard";

export function YoutubeClient() {
  const [status, setStatus]     = useState<OAuthStatus | null>(null);
  const [loading, setLoading]   = useState(false);
  const [authUrl, setAuthUrl]   = useState("");
  const [urlLoading, setUrlLoading] = useState(false);
  const [copied, setCopied]     = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/oauth/youtube/status`);
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
        `${API_BASE}/api/v1/oauth/youtube/auth-url?scope=force-ssl+upload`);
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
