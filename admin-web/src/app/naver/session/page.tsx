"use client";

/**
 * /naver/session — 네이버 로그인 세션.
 *
 * 화면을 열면 실제 로그인 상태와 계정을 읽기 전용으로 확인하고, **로그아웃(out)일 때만** 자동 로그인을 1회 시도한다.
 * 이미 로그인됨·상태 불명확·다른 계정이면 아무것도 건드리지 않는다(세션을 파기하지 않는다).
 * 서버가 시도를 제한한다: 직전 시도 후 5분 대기, 하루 3회. 캡차·2단계 인증은 사용자가 브라우저에서 처리한다.
 * 기준서: docs/specs/2026-10-01_electron_naver_auto_login.md
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { PageShell } from "@/components/ui/PageShell";

type SessionState = "in" | "out" | "unknown" | "unavailable";
type AccountCheck = "verified" | "other" | "unknown" | null;
type EnsureAction = "none" | "wait" | "logged_in" | "unverified" | "captcha" | "failed";

interface LiveState {
  target: string;
  state: SessionState;
  cookie: boolean | null;
  alias: string | null;
  account: AccountCheck;
  targets?: string[];
}

interface EnsureResult extends LiveState {
  action: EnsureAction;
  reason: string;
  message: string;
  wait_seconds?: number;
}

const DEFAULT_TARGET = "skyjwsin";

type Tone = "ok" | "warn" | "info" | "off";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-green-100 text-green-800 border-green-200",
  warn: "bg-yellow-100 text-yellow-800 border-yellow-200",
  info: "bg-blue-100 text-blue-800 border-blue-200",
  off: "bg-gray-100 text-gray-600 border-gray-200",
};

function describe(live: LiveState): { label: string; tone: Tone } {
  if (live.state === "in") {
    if (live.account === "verified") return { label: "✓ 로그인됨 · 계정 확인됨", tone: "ok" };
    if (live.account === "other") return { label: "⚠ 다른 계정으로 로그인됨", tone: "warn" };
    return { label: "✓ 로그인됨 · 계정 미확인", tone: "info" };
  }
  if (live.state === "out") return { label: "✗ 로그아웃", tone: "off" };
  if (live.state === "unavailable") return { label: "브라우저 연결 불가", tone: "warn" };
  return { label: "⚠ 상태 불명확", tone: "warn" };
}

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail);
    return `${e.status} ${detail}`;
  }
  return e instanceof Error ? e.message : String(e);
}

export default function NaverSessionPage() {
  const [target, setTarget] = useState(DEFAULT_TARGET);
  const [targets, setTargets] = useState<string[]>([DEFAULT_TARGET]);
  const [live, setLive] = useState<LiveState | null>(null);
  const [checking, setChecking] = useState(false);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const autoTried = useRef(false);

  const check = useCallback(async (t: string): Promise<LiveState | null> => {
    setChecking(true);
    try {
      const data = await apiFetch<LiveState>(`/naver/session/live?target=${encodeURIComponent(t)}`);
      setLive(data);
      if (data.targets && data.targets.length > 0) setTargets(data.targets);
      return data;
    } catch (e: unknown) {
      setMessage({ text: `상태 확인 실패: ${errorText(e)}`, ok: false });
      return null;
    } finally {
      setChecking(false);
    }
  }, []);

  const ensure = useCallback(async (t: string, allowAttempt: boolean) => {
    setRunning(true);
    setMessage(null);
    try {
      const data = await apiFetch<EnsureResult>("/naver/session/ensure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: t, allow_attempt: allowAttempt }),
      });
      setLive(data);
      const good = data.state === "in" && (data.action === "none" || data.action === "logged_in");
      setMessage({ text: data.message, ok: good });
    } catch (e: unknown) {
      setMessage({ text: `로그인 처리 실패: ${errorText(e)}`, ok: false });
    } finally {
      setRunning(false);
    }
  }, []);

  // 화면을 열 때: 읽기 전용 확인 → 로그아웃(out)일 때만 자동 로그인 1회. (개발 모드의 이중 실행은 ref 로 막는다)
  useEffect(() => {
    if (autoTried.current) return;
    autoTried.current = true;
    void (async () => {
      const data = await check(DEFAULT_TARGET);
      if (data && data.state === "out") await ensure(DEFAULT_TARGET, true);
    })();
  }, [check, ensure]);

  const busy = checking || running;
  const badge = live ? describe(live) : null;

  return (
    <PageShell title="로그인 세션" description="네이버 로그인 상태 확인과 자동 로그인" chatDomain="naver">
      <div className="space-y-6">
        {/* 실제 세션 상태 */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium text-[#374151]">현재 세션 상태 (실제 확인)</span>
            <div className="flex items-center gap-2">
              <label className="text-xs text-[#6B7280]" htmlFor="naver-target">
                계정
              </label>
              <select
                id="naver-target"
                value={target}
                disabled={busy}
                onChange={(e) => {
                  setTarget(e.target.value);
                  void check(e.target.value);
                }}
                className="text-xs border border-[#E5E7EB] rounded-md px-2 py-1 bg-white"
              >
                {targets.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <button
                onClick={() => void check(target)}
                disabled={busy}
                className="text-xs text-[#6B7280] hover:text-[#111827] disabled:opacity-40"
              >
                {checking ? "확인 중..." : "새로고침"}
              </button>
            </div>
          </div>

          {badge && live ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <span
                  className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium border ${TONE_CLASS[badge.tone]}`}
                >
                  {badge.label}
                </span>
                {live.alias && <span className="text-sm text-[#111827] font-medium">{live.alias}</span>}
              </div>
              <div className="text-xs text-[#9CA3AF] space-y-1">
                <div>대상 계정: {live.target}</div>
                <div>세션 쿠키: {live.cookie === null ? "확인 불가" : live.cookie ? "있음" : "없음"}</div>
                {live.state === "unknown" && (
                  <div className="text-yellow-600">
                    세션 쿠키는 있는데 화면 근거가 충돌합니다. 세션을 파기하지 않도록 로그인을 시도하지 않았습니다.
                  </div>
                )}
                {live.account === "other" && (
                  <div className="text-yellow-600">
                    자동으로 계정을 전환하지 않습니다. 바꾸려면 브라우저에서 직접 로그아웃한 뒤 다시 확인하세요.
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-sm text-[#9CA3AF]">{checking ? "확인 중..." : "상태 없음"}</div>
          )}
        </div>

        {/* 자동 로그인 */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 space-y-4">
          <div>
            <p className="text-sm font-medium text-[#374151]">자동 로그인</p>
            <p className="text-xs text-[#6B7280] mt-1">
              화면을 열 때 로그아웃 상태면 자동으로 1회 시도합니다. 이미 로그인돼 있으면 아무것도 하지 않습니다.
              시도는 직전 시도 후 5분 대기, 하루 3회로 제한됩니다.
            </p>
          </div>
          <button
            onClick={() => void ensure(target, true)}
            disabled={busy}
            className={[
              "w-full py-2.5 px-4 rounded-lg text-sm font-medium transition-colors",
              busy
                ? "bg-[#E5E7EB] text-[#9CA3AF] cursor-not-allowed"
                : "bg-[#03C75A] text-white hover:bg-[#02A84A] active:bg-[#028040]",
            ].join(" ")}
          >
            {running ? "로그인 확인·진행 중... (수 분 걸릴 수 있음)" : `${target} 로그인 확인 / 자동 로그인`}
          </button>

          {message && (
            <div
              role="status"
              className={[
                "text-xs rounded-lg p-3",
                message.ok
                  ? "bg-green-50 text-green-700 border border-green-200"
                  : "bg-red-50 text-red-700 border border-red-200",
              ].join(" ")}
            >
              {message.text}
            </div>
          )}
        </div>

        {/* 사용 안내 */}
        <div className="bg-[#FFFBEB] border border-[#FDE68A] rounded-xl p-4 text-xs text-[#92400E] space-y-1">
          <p className="font-medium">참고 사항</p>
          <ul className="list-disc list-inside space-y-0.5">
            <li>로그아웃 URL 이동이나 쿠키 삭제는 하지 않습니다. 로그인된 세션은 그대로 보존됩니다.</li>
            <li>CAPTCHA·2단계 인증이 뜨면 자동으로 넘기지 않습니다. 브라우저에서 직접 처리한 뒤 새로고침하세요.</li>
            <li>로그인 정보는 통합 자격증명 저장소에서 읽으며 화면과 로그에 남기지 않습니다.</li>
            <li>계정 확인은 블로그 관리 주소(공개 alias)로 합니다. 조명 계정은 로그인 ID 와 공개 주소가 다릅니다.</li>
          </ul>
        </div>
      </div>
    </PageShell>
  );
}
