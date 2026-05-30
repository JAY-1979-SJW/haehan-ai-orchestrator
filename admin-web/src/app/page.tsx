"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";
import { getMe, type UserInfo } from "@/lib/userAuth";
import SessionStatusPanel from "@/components/SessionStatusPanel";

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
  { href: "/cad",                          label: "CAD 자동화",   desc: "물량산출·안전구획도",       color: "#F97316", bg: "#FFF7ED", border: "#FED7AA" },
  { href: "/ops",                          label: "운영센터",     desc: "서버 상태·감사 로그",       color: "#374151", bg: "#F9FAFB", border: "#E5E7EB" },
  { href: "/gabia",                          label: "가비아",       desc: "도메인·DNS·호스팅 AI 자동화", color: "#1D4ED8", bg: "#EFF6FF", border: "#BFDBFE" },
  { href: "/hanafax",                        label: "하나팩스",     desc: "팩스 발송·큐·잔액 관리",      color: "#1D4ED8", bg: "#EFF6FF", border: "#BFDBFE" },
  { href: "/bid",                            label: "입찰분석 BID", desc: "나라장터 공고 조회·AI 분석",   color: "#111827", bg: "#F9FAFB", border: "#E5E7EB" },
  { href: "/dataportal",                     label: "공공데이터포털", desc: "API 키 발급·관리·데이터 신청", color: "#0891B2", bg: "#ECFEFF", border: "#A5F3FC" },
];

// ── 서비스 현황 카드 ──────────────────────────────────────────────────────────
const SERVICE_STATUS = [
  { label: "KRAS 위험성평가", url: "https://kras.haehan-ai.kr", status: "운영중", color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0" },
  { label: "CAD 물량산출",   url: "/cad",                       status: "운영중", color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0" },
  { label: "스마트스토어 AI", url: "/naver/smartstore",          status: "운영중", color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0" },
  { label: "YouTube 자동화", url: "/youtube",                    status: "운영중", color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0" },
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
    <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold text-[#111827]">네이버 로그인 세션</p>
          <p className="text-xs text-[#6B7280] mt-0.5">CDP 자동화 연결 상태</p>
        </div>
        <button onClick={fetchStatus} disabled={loading}
          className="text-xs text-[#9CA3AF] hover:text-[#6B7280] disabled:opacity-40 transition-colors">
          {loading ? "조회 중..." : "새로고침"}
        </button>
      </div>

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

      <button onClick={handleLogin} disabled={loginRunning}
        className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-colors ${
          loginRunning
            ? "bg-[#E5E7EB] text-[#9CA3AF] cursor-not-allowed"
            : "bg-[#03C75A] text-white hover:bg-[#02A84A]"
        }`}>
        {loginRunning ? "실행 중..." : "네이버 로그인 실행"}
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
  const [user, setUser] = useState<UserInfo | null>(null);
  const [authChecked, setAuthChecked] = useState(false);

  // 비회원도 앱을 볼 수 있도록 강제 리다이렉트 없이 사용자 정보만 조회한다.
  // (로그인하지 않은 경우 헤더에 '로그인' 링크가 표시된다)
  useEffect(() => {
    getMe().then((u) => {
      setUser(u);
      setAuthChecked(true);
    });
  }, []);

  if (!authChecked) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center">
        <div className="text-sm text-[#9CA3AF]">로딩 중...</div>
      </div>
    );
  }

  return (
    <PageShell title="Haehan AI" description="AI 오케스트레이터 대시보드" chatDomain="default">
      <div className="space-y-6 w-full">

        {/* 헤더 배너 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#F97316] flex items-center justify-center text-white font-bold text-sm shrink-0">AI</div>
            <div className="flex-1 min-w-0">
              <h1 className="text-lg font-bold text-[#111827]">Haehan AI 오케스트레이터</h1>
              <p className="text-sm text-[#6B7280]">CAD 자동화 · 위험성평가 · 스마트스토어 · AI 에이전트</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {user ? (
                <Link href="/mypage"
                  className="px-3 py-1.5 rounded-lg bg-[#F9FAFB] border border-[#E5E7EB] text-sm text-[#374151] hover:border-[#F97316] hover:text-[#F97316] transition-colors">
                  {user.name} ▾
                </Link>
              ) : (
                <Link href="/login"
                  className="px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-sm text-[#6B7280] hover:text-[#111827] transition-colors">
                  로그인
                </Link>
              )}
              <Link href="/naver/smartstore"
                className="px-4 py-2 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] transition-colors">
                스마트스토어 AI →
              </Link>
            </div>
          </div>
        </div>

        {/* 서비스 현황 */}
        <div>
          <p className="text-xs font-semibold text-[#9CA3AF] uppercase tracking-wider mb-3">서비스 현황</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {SERVICE_STATUS.map((s) => (
              <Link key={s.label} href={s.url}
                className="bg-white border rounded-xl p-3 hover:shadow-sm transition-all"
                style={{ borderColor: s.border }}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold" style={{ color: s.color }}>● {s.status}</span>
                </div>
                <p className="text-sm font-bold text-[#111827]">{s.label}</p>
              </Link>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">

          {/* 빠른 메뉴 */}
          <div className="lg:col-span-2 space-y-3">
            <p className="text-xs font-semibold text-[#9CA3AF] uppercase tracking-wider">빠른 메뉴</p>
            <div className="grid grid-cols-2 sm:grid-cols-2 gap-3">
              {QUICK_MENUS.map((m) => (
                <Link key={m.href} href={m.href}
                  target={m.href.startsWith("http") ? "_blank" : undefined}
                  className="block bg-white border rounded-xl p-4 hover:shadow-sm transition-all"
                  style={{ borderColor: m.border }}>
                  <p className="text-sm font-bold" style={{ color: m.color }}>{m.label}</p>
                  <p className="text-xs text-[#6B7280] mt-0.5">{m.desc}</p>
                </Link>
              ))}
            </div>
          </div>

          {/* 네이버 로그인 설정 */}
          <div className="flex flex-col space-y-3">
            <p className="text-xs font-semibold text-[#9CA3AF] uppercase tracking-wider">로그인 설정</p>
            <div className="flex-1 min-h-0">
              <NaverLoginCard />
            </div>
          </div>

        </div>

        {/* 앱별 로그인 세션 현황 */}
        <SessionStatusPanel />

        {/* 랜딩 페이지 링크 */}
        <div className="text-center pt-2">
          <Link href="/about"
            className="text-xs text-[#9CA3AF] hover:text-[#6B7280] transition-colors">
            서비스 소개 →
          </Link>
        </div>

      </div>
    </PageShell>
  );
}
