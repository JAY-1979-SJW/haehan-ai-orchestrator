"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { PageShell } from "@/components/ui/PageShell";

interface SessionStatus {
  logged_in: boolean;
  user: string | null;
  checked_at: string | null;
  pending_captcha: boolean;
  browser_session_saved: boolean;
  error: string | null;
}

interface LoginResult {
  ok: boolean;
  logged_in: boolean;
  user: string | null;
  message: string;
  captcha: boolean;
}

function StatusBadge({ loggedIn, pendingCaptcha }: { loggedIn: boolean; pendingCaptcha: boolean }) {
  if (pendingCaptcha)
    return <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800 border border-yellow-200">⚠ CAPTCHA 대기</span>;
  if (loggedIn)
    return <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800 border border-green-200">✓ 로그인됨</span>;
  return <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600 border border-gray-200">✗ 미로그인</span>;
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  } catch {
    return iso;
  }
}

export default function NaverSessionPage() {
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [loginRunning, setLoginRunning] = useState(false);
  const [lastResult, setLastResult] = useState<string | null>(null);
  const [lastResultOk, setLastResultOk] = useState<boolean | null>(null);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<SessionStatus>("/naver/session/status");
      setStatus(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setLastResult(`상태 조회 실패: ${msg}`);
      setLastResultOk(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleLogin = async () => {
    if (loginRunning) return;
    setLoginRunning(true);
    setLastResult(null);
    setLastResultOk(null);
    try {
      const data = await apiFetch<LoginResult>("/naver/session/login", { method: "POST" });
      setLastResult(data.message);
      setLastResultOk(data.ok);
      await fetchStatus();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setLastResult(`오류: ${msg}`);
      setLastResultOk(false);
    } finally {
      setLoginRunning(false);
    }
  };

  return (
    <PageShell title="로그인 세션" description="네이버 CDP 세션 관리" chatDomain="naver">
      <div className="space-y-6">
        {/* 세션 상태 카드 */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[#374151]">현재 세션 상태</span>
            <button
              onClick={fetchStatus}
              disabled={loading}
              className="text-xs text-[#6B7280] hover:text-[#111827] disabled:opacity-40"
            >
              {loading ? "조회 중..." : "새로고침"}
            </button>
          </div>

          {status ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <StatusBadge loggedIn={status.logged_in} pendingCaptcha={status.pending_captcha} />
                {status.user && (
                  <span className="text-sm text-[#111827] font-medium">{status.user}</span>
                )}
              </div>
              <div className="text-xs text-[#9CA3AF] space-y-1">
                <div>최종 확인: {formatDate(status.checked_at)}</div>
                <div>
                  브라우저 세션 파일:{" "}
                  {status.browser_session_saved
                    ? <span className="text-green-600 font-medium">저장됨 ✓</span>
                    : <span className="text-gray-400">없음</span>}
                </div>
                {status.error && (
                  <div className="text-red-500">오류: {status.error}</div>
                )}
                {status.pending_captcha && (
                  <div className="text-yellow-600">브라우저에서 CAPTCHA/2FA를 직접 완료한 후 다시 상태를 확인하세요.</div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-sm text-[#9CA3AF]">{loading ? "조회 중..." : "상태 없음"}</div>
          )}
        </div>

        {/* 로그인 버튼 */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 space-y-4">
          <div>
            <p className="text-sm font-medium text-[#374151]">로그인 파이프라인 실행</p>
            <p className="text-xs text-[#6B7280] mt-1">
              CDP 브라우저가 꺼져 있으면 자동으로 시작합니다. 이미 로그인된 경우 세션만 갱신합니다.
            </p>
          </div>
          <button
            onClick={handleLogin}
            disabled={loginRunning}
            className={[
              "w-full py-2.5 px-4 rounded-lg text-sm font-medium transition-colors",
              loginRunning
                ? "bg-[#E5E7EB] text-[#9CA3AF] cursor-not-allowed"
                : "bg-[#03C75A] text-white hover:bg-[#02A84A] active:bg-[#028040]",
            ].join(" ")}
          >
            {loginRunning ? "실행 중... (CDP 시작 + 로그인)" : "네이버 로그인 실행"}
          </button>

          {lastResult && (
            <div
              className={[
                "text-xs rounded-lg p-3",
                lastResultOk
                  ? "bg-green-50 text-green-700 border border-green-200"
                  : "bg-red-50 text-red-700 border border-red-200",
              ].join(" ")}
            >
              {lastResult}
            </div>
          )}
        </div>

        {/* 사용 안내 */}
        <div className="bg-[#FFFBEB] border border-[#FDE68A] rounded-xl p-4 text-xs text-[#92400E] space-y-1">
          <p className="font-medium">참고 사항</p>
          <ul className="list-disc list-inside space-y-0.5">
            <li>CAPTCHA가 감지되면 브라우저에서 직접 완료 후 상태를 새로고침하세요.</li>
            <li>로그인 정보는 <code>.env_naver</code> 또는 통합 자격증명 저장소에서 읽습니다.</li>
            <li>세션 상태는 <code>data/naver_session_state.json</code>에 저장됩니다.</li>
          </ul>
        </div>
      </div>
    </PageShell>
  );
}
