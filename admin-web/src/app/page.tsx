"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";

// ── 네이버 세션 상태 타입 ─────────────────────────────────────────────────────
interface SessionStatus {
  logged_in: boolean;
  user: string | null;
  checked_at: string | null;
  pending_captcha: boolean;
  browser_session_saved: boolean;
  error: string | null;
}

// ── 빠른 메뉴 ────────────────────────────────────────────────────────────────
const QUICK_MENUS = [
  { href: "/naver/smartstore",             label: "스마트스토어",  desc: "AI 채팅·상품·주문·정산",    color: "#F97316", bg: "#FFF7ED", border: "#FED7AA" },
  { href: "/naver/smartstore/products",    label: "상품 관리",    desc: "상품 목록·등록·수정",       color: "#1D4ED8", bg: "#EFF6FF", border: "#BFDBFE" },
  { href: "/naver/smartstore/orders",      label: "주문 관리",    desc: "주문 목록·처리",            color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0" },
  { href: "/naver/smartstore/settlements", label: "정산 관리",    desc: "정산 내역·요약",            color: "#7C3AED", bg: "#F5F3FF", border: "#DDD6FE" },
  { href: "/naver/smartstore/reviews",     label: "리뷰/문의",    desc: "고객 리뷰·문의 확인",       color: "#C2410C", bg: "#FFF7ED", border: "#FED7AA" },
  { href: "/naver/smartstore/stats",       label: "데이터 분석",  desc: "매출·방문 통계",            color: "#0891B2", bg: "#ECFEFF", border: "#A5F3FC" },
  { href: "/ops",                          label: "운영센터",     desc: "서버 상태·감사 로그",       color: "#374151", bg: "#F9FAFB", border: "#E5E7EB" },
  { href: "/naver/session",                label: "세션 관리",    desc: "네이버 로그인 세션",        color: "#03C75A", bg: "#F0FDF4", border: "#BBF7D0" },
];

// ── 네이버 로그인 카드 ────────────────────────────────────────────────────────
function NaverLoginCard() {
  const [status, setStatus]         = useState<SessionStatus | null>(null);
  const [loading, setLoading]       = useState(false);
  const [loginRunning, setLoginRunning] = useState(false);
  const [result, setResult]         = useState<{ ok: boolean; msg: string } | null>(null);

  const AUTH = typeof btoa !== "undefined"
    ? `Basic ${btoa(`${process.env.NEXT_PUBLIC_API_USER ?? "owner"}:${process.env.NEXT_PUBLIC_API_PASS ?? "haehan2024!"}`)}`
    : "";

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/naver/session/status`,
        { headers: { Authorization: AUTH } });
      if (r.ok) setStatus(await r.json());
    } catch { /* 서버 미연결 시 무시 */ }
    finally { setLoading(false); }
  }, [AUTH]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const handleLogin = async () => {
    setLoginRunning(true);
    setResult(null);
    try {
      const r = await fetch(`${API_BASE}/api/v1/naver/session/login`,
        { method: "POST", headers: { Authorization: AUTH } });
      const d = await r.json();
      setResult({ ok: d.ok, msg: d.message ?? (d.ok ? "로그인 완료" : "실패") });
      await fetchStatus();
    } catch (e) {
      setResult({ ok: false, msg: String(e) });
    } finally {
      setLoginRunning(false);
    }
  };

  const loggedIn   = status?.logged_in ?? false;
  const captcha    = status?.pending_captcha ?? false;

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 space-y-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold text-[#111827]">네이버 로그인 세션</p>
          <p className="text-xs text-[#6B7280] mt-0.5">스마트스토어 CDP 자동화에 사용됩니다</p>
        </div>
        <button onClick={fetchStatus} disabled={loading}
          className="text-xs text-[#9CA3AF] hover:text-[#6B7280] disabled:opacity-40 transition-colors">
          {loading ? "조회 중..." : "새로고침"}
        </button>
      </div>

      {/* 세션 상태 */}
      <div className="flex items-center gap-3">
        {captcha ? (
          <span className="text-xs font-semibold px-3 py-1.5 rounded-full bg-[#FEF3C7] text-[#92400E] border border-[#FDE68A]">⚠ CAPTCHA 대기</span>
        ) : loggedIn ? (
          <span className="text-xs font-semibold px-3 py-1.5 rounded-full bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0]">✓ 로그인됨</span>
        ) : (
          <span className="text-xs font-semibold px-3 py-1.5 rounded-full bg-[#F9FAFB] text-[#6B7280] border border-[#E5E7EB]">✗ 미로그인</span>
        )}
        {status?.user && <span className="text-sm font-medium text-[#111827]">{status.user}</span>}
      </div>

      {status && (
        <div className="text-xs text-[#9CA3AF] space-y-1">
          {status.checked_at && <p>최종 확인: {new Date(status.checked_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}</p>}
          <p>세션 파일: {status.browser_session_saved
            ? <span className="text-[#16A34A] font-medium">저장됨 ✓</span>
            : <span>없음</span>}
          </p>
          {status.error && <p className="text-[#DC2626]">{status.error}</p>}
          {captcha && <p className="text-[#92400E]">브라우저에서 CAPTCHA를 직접 완료 후 새로고침하세요.</p>}
        </div>
      )}

      {/* 로그인 버튼 */}
      <button onClick={handleLogin} disabled={loginRunning}
        className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-colors ${
          loginRunning
            ? "bg-[#E5E7EB] text-[#9CA3AF] cursor-not-allowed"
            : "bg-[#03C75A] text-white hover:bg-[#02A84A]"
        }`}>
        {loginRunning ? "실행 중... (CDP 시작 + 로그인)" : "네이버 로그인 실행"}
      </button>

      {result && (
        <div className={`text-xs rounded-lg p-3 ${
          result.ok
            ? "bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0]"
            : "bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA]"
        }`}>
          {result.msg}
        </div>
      )}

      <Link href="/naver/session"
        className="block text-center text-xs text-[#6B7280] hover:text-[#111827] transition-colors">
        세션 상세 관리 →
      </Link>
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function HomePage() {
  return (
    <PageShell title="Haehan AI" description="스마트스토어 · 운영 · AI 자동화">
      <div className="space-y-6">

        {/* 헤더 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#F97316] flex items-center justify-center text-white font-bold text-sm shrink-0">AI</div>
            <div>
              <h1 className="text-lg font-bold text-[#111827]">Haehan AI 오케스트레이터</h1>
              <p className="text-sm text-[#6B7280]">스마트스토어 자동화 · CDP 브라우저 제어 · AI 에이전트</p>
            </div>
            <Link href="/naver/smartstore"
              className="ml-auto px-4 py-2 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] transition-colors shrink-0">
              스마트스토어 AI 채팅 →
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* 빠른 메뉴 */}
          <div className="lg:col-span-2 space-y-4">
            <p className="text-sm font-semibold text-[#374151]">빠른 메뉴</p>
            <div className="grid grid-cols-2 sm:grid-cols-2 gap-3">
              {QUICK_MENUS.map((m) => (
                <Link key={m.href} href={m.href}
                  className="block bg-white border rounded-xl p-4 hover:shadow-sm transition-all group"
                  style={{ borderColor: m.border }}>
                  <p className="text-sm font-bold" style={{ color: m.color }}>{m.label}</p>
                  <p className="text-xs text-[#6B7280] mt-0.5">{m.desc}</p>
                </Link>
              ))}
            </div>
          </div>

          {/* 네이버 로그인 설정 */}
          <div className="space-y-4">
            <p className="text-sm font-semibold text-[#374151]">로그인 설정</p>
            <NaverLoginCard />
          </div>

        </div>
      </div>
    </PageShell>
  );
}
