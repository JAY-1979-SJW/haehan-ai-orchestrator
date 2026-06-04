"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getMe, clearToken, type UserInfo } from "@/lib/userAuth";
import { useRouter } from "next/navigation";

// ── 데이터 ────────────────────────────────────────────────────────────────────
const FEATURES = [
  {
    icon: "🛡️",
    title: "위험성평가 (KRAS)",
    desc: "KOSHA DB 연동으로 법적 제출용 위험성평가표를 자동 생성합니다. 월 1회 DB 자동 갱신.",
    detail: "kras.haehan-ai.kr 운영 중",
    badge: "운영중",
    badgeColor: "#16A34A",
    href: "https://kras.haehan-ai.kr",
    external: true,
  },
  {
    icon: "🛒",
    title: "스마트스토어 AI 자동화",
    desc: "AI 채팅으로 업무를 지시하면 상품 등록·주문 처리·정산·리뷰 관리를 자동으로 처리합니다.",
    detail: "CDP 브라우저 자동 제어",
    badge: null,
    badgeColor: "",
    href: "/naver/smartstore",
  },
  {
    icon: "▶",
    title: "YouTube 자동화",
    desc: "영상 업로드, 자막 생성, 채널 관리를 OAuth 인증 기반으로 자동 처리합니다.",
    detail: "OAuth 인증 완료",
    badge: null,
    badgeColor: "",
    href: "/youtube",
  },
  {
    icon: "🤖",
    title: "AI 에이전트 오케스트레이터",
    desc: "MCP 기반 멀티 에이전트가 네이버·구글·카페·메일을 자율 실행하고 감사 로그를 기록합니다.",
    detail: "승인 게이트 + 감사 추적",
    badge: null,
    badgeColor: "",
    href: "/ops",
  },
];

const HOW_IT_WORKS = [
  { step: "01", title: "회원가입", desc: "이메일과 비밀번호로 30초 만에 가입합니다." },
  { step: "02", title: "기능 선택", desc: "스마트스토어, AI 에이전트 중 필요한 기능을 선택합니다." },
  { step: "03", title: "자동화 실행", desc: "도면·데이터를 업로드하거나 AI에게 지시하면 결과물이 자동으로 만들어집니다." },
];

const PLANS = [
  {
    name: "Free",
    price: "무료",
    desc: "기본 기능 무제한 체험",
    features: ["스마트스토어 AI 채팅", "운영센터 조회", "이메일 지원"],
    cta: "무료로 시작하기",
    ctaHref: "/signup",
    highlight: false,
  },
  {
    name: "Pro",
    price: "문의",
    desc: "실서비스 전체 기능",
    features: ["스마트스토어 완전 자동화", "YouTube 자동화", "AI 에이전트 전체", "감사 로그 전체 이력", "우선 지원"],
    cta: "도입 문의",
    ctaHref: "mailto:skyjwshin@gmail.com",
    highlight: true,
  },
];

const SERVICES = [
  { label: "haehan-ai.kr", desc: "메인 서비스 홈", href: "https://haehan-ai.kr", color: "#111827", short: "H" },
  { label: "kras.haehan-ai.kr", desc: "위험성평가 서비스", href: "https://kras.haehan-ai.kr", color: "#16A34A", short: "K" },
  { label: "bid.haehan-ai.kr", desc: "입찰분석 서비스", href: "https://bid.haehan-ai.kr", color: "#1D4ED8", short: "B" },
];

// ── 헤더 ──────────────────────────────────────────────────────────────────────
function Header({ user, onLogout }: { user: UserInfo | null; onLogout: () => void }) {
  return (
    <header className="bg-white border-b border-[#E5E7EB] sticky top-0 z-50">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/about" className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-[#F97316] flex items-center justify-center text-white font-bold text-xs">AI</div>
          <span className="text-[15px] font-bold text-[#111827]">
            Haehan <span className="text-[#F97316]">AI</span>
            <span className="text-xs font-normal text-[#9CA3AF] ml-1">Autowork</span>
          </span>
        </Link>

        <nav className="hidden sm:flex items-center gap-5 text-sm text-[#6B7280]">
          <a href="#features" className="hover:text-[#111827] transition-colors">기능</a>
          <a href="#how" className="hover:text-[#111827] transition-colors">이용방법</a>
          <a href="#pricing" className="hover:text-[#111827] transition-colors">요금제</a>
          <a href="https://haehan-ai.kr" target="_blank" className="hover:text-[#111827] transition-colors">본사 홈</a>
        </nav>

        <div className="flex items-center gap-2">
          {user ? (
            <>
              <Link href="/mypage" className="text-sm text-[#6B7280] hover:text-[#111827] px-3 py-1.5 transition-colors hidden sm:block">{user.name}</Link>
              <Link href="/" className="px-4 py-1.5 rounded-lg bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] transition-colors">대시보드 →</Link>
            </>
          ) : (
            <>
              <Link href="/login" className="text-sm text-[#6B7280] hover:text-[#111827] px-3 py-1.5 transition-colors">로그인</Link>
              <Link href="/signup" className="px-4 py-1.5 rounded-lg bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] transition-colors">무료 시작</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

// ── 메인 ──────────────────────────────────────────────────────────────────────
export default function AboutPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [inquiryOpen, setInquiryOpen] = useState(false);

  useEffect(() => { getMe().then(setUser); }, []);

  const handleLogout = () => { clearToken(); router.push("/login"); };

  return (
    <div className="min-h-screen bg-white text-[#111827]">
      <Header user={user} onLogout={handleLogout} />

      {/* ── Hero ── */}
      <section className="bg-gradient-to-b from-[#FFF7ED] to-white pt-16 pb-20 px-4 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white border border-[#FED7AA] text-[#F97316] text-xs font-semibold mb-6 shadow-sm">
          <span className="w-1.5 h-1.5 rounded-full bg-[#F97316] animate-pulse" />
          autowork.haehan-ai.kr — 지금 운영 중
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-[#111827] leading-tight mb-5 max-w-3xl mx-auto">
          건설·커머스·콘텐츠<br />
          <span className="text-[#F97316]">모든 업무를 AI가</span> 자동으로
        </h1>
        <p className="text-base sm:text-lg text-[#6B7280] max-w-2xl mx-auto mb-8 leading-relaxed">
          위험성평가표 — 착공 전 필수 서류를 자동으로.<br className="hidden sm:block" />
          스마트스토어·YouTube까지 AI 에이전트가 한 번에 처리합니다.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          {user ? (
            <Link href="/" className="px-8 py-3 rounded-xl bg-[#F97316] text-white font-semibold text-base hover:bg-[#EA580C] transition-colors shadow-sm">
              대시보드 바로가기 →
            </Link>
          ) : (
            <>
              <Link href="/signup" className="px-8 py-3 rounded-xl bg-[#F97316] text-white font-semibold text-base hover:bg-[#EA580C] transition-colors shadow-sm">
                무료로 시작하기
              </Link>
              <Link href="/login" className="px-8 py-3 rounded-xl border border-[#E5E7EB] text-[#374151] font-semibold text-base hover:border-[#F97316] hover:text-[#F97316] transition-colors">
                로그인
              </Link>
            </>
          )}
        </div>

        {/* 수치 */}
        <div className="mt-12 grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-2xl mx-auto">
          {[
            { v: "AI", l: "자동화 에이전트" },
            { v: "전체", l: "업무 자동화" },
            { v: "24/7", l: "자동 운영" },
            { v: "실서비스", l: "데모 아닌 실제 운영" },
          ].map((s) => (
            <div key={s.l} className="bg-white border border-[#E5E7EB] rounded-2xl py-4 px-3 shadow-sm">
              <p className="text-2xl font-extrabold text-[#F97316]">{s.v}</p>
              <p className="text-xs text-[#6B7280] mt-1">{s.l}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 기능 ── */}
      <section id="features" className="max-w-5xl mx-auto px-4 py-20">
        <div className="text-center mb-10">
          <h2 className="text-2xl font-bold mb-2">하나의 플랫폼, 모든 자동화</h2>
          <p className="text-[#6B7280]">단일 기능 제품이 아닙니다. 건설·커머스·콘텐츠를 하나로.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f) => (
            <Link
              key={f.title}
              href={f.href}
              target={(f as { external?: boolean }).external ? "_blank" : undefined}
              className="bg-white border border-[#E5E7EB] rounded-2xl p-5 hover:border-[#F97316] hover:shadow-md transition-all group block"
            >
              <div className="flex items-start justify-between mb-3">
                <span className="text-2xl">{f.icon}</span>
                {f.badge && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                    style={{ background: f.badgeColor + "20", color: f.badgeColor, border: `1px solid ${f.badgeColor}50` }}>
                    {f.badge}
                  </span>
                )}
              </div>
              <p className="text-sm font-bold text-[#111827] mb-1 group-hover:text-[#F97316] transition-colors">{f.title}</p>
              <p className="text-xs text-[#6B7280] leading-relaxed mb-3">{f.desc}</p>
              <p className="text-xs font-semibold text-[#F97316]">{f.detail}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* ── 이용 방법 ── */}
      <section id="how" className="bg-[#F9FAFB] border-y border-[#E5E7EB] py-20 px-4">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-bold mb-2">이렇게 사용하세요</h2>
            <p className="text-[#6B7280]">복잡한 설정 없이 3단계로 시작합니다.</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {HOW_IT_WORKS.map((h, i) => (
              <div key={h.step} className="relative">
                {i < HOW_IT_WORKS.length - 1 && (
                  <div className="hidden sm:block absolute top-6 left-full w-full h-px bg-[#E5E7EB] z-0" style={{ width: "calc(100% - 48px)", left: "calc(50% + 24px)" }} />
                )}
                <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 text-center relative z-10">
                  <div className="w-10 h-10 rounded-full bg-[#FFF7ED] border-2 border-[#FED7AA] flex items-center justify-center mx-auto mb-3">
                    <span className="text-sm font-extrabold text-[#F97316]">{h.step}</span>
                  </div>
                  <p className="text-sm font-bold text-[#111827] mb-1">{h.title}</p>
                  <p className="text-xs text-[#6B7280]">{h.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── 요금제 ── */}
      <section id="pricing" className="max-w-3xl mx-auto px-4 py-20">
        <div className="text-center mb-10">
          <h2 className="text-2xl font-bold mb-2">요금제</h2>
          <p className="text-[#6B7280]">지금 바로 무료로 시작하고, 필요하면 확장하세요.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {PLANS.map((p) => (
            <div key={p.name}
              className={`rounded-2xl p-6 border transition-all ${p.highlight
                ? "bg-[#111827] border-[#111827] text-white"
                : "bg-white border-[#E5E7EB]"}`}>
              <div className="mb-4">
                <p className={`text-xs font-bold uppercase tracking-wider mb-1 ${p.highlight ? "text-[#F97316]" : "text-[#9CA3AF]"}`}>{p.name}</p>
                <p className={`text-3xl font-extrabold ${p.highlight ? "text-white" : "text-[#111827]"}`}>{p.price}</p>
                <p className={`text-sm mt-1 ${p.highlight ? "text-[#9CA3AF]" : "text-[#6B7280]"}`}>{p.desc}</p>
              </div>
              <ul className="space-y-2 mb-6">
                {p.features.map((f) => (
                  <li key={f} className={`text-sm flex items-center gap-2 ${p.highlight ? "text-[#D1D5DB]" : "text-[#374151]"}`}>
                    <span className="text-[#F97316] font-bold">✓</span> {f}
                  </li>
                ))}
              </ul>
              {p.ctaHref.startsWith("mailto") ? (
                <button onClick={() => setInquiryOpen(true)}
                  className={`block w-full text-center py-2.5 rounded-xl font-semibold text-sm transition-colors ${p.highlight
                    ? "bg-[#F97316] text-white hover:bg-[#EA580C]"
                    : "border border-[#E5E7EB] text-[#374151] hover:border-[#F97316] hover:text-[#F97316]"}`}>
                  {p.cta}
                </button>
              ) : (
                <Link href={p.ctaHref}
                  className={`block w-full text-center py-2.5 rounded-xl font-semibold text-sm transition-colors ${p.highlight
                    ? "bg-[#F97316] text-white hover:bg-[#EA580C]"
                    : "border border-[#E5E7EB] text-[#374151] hover:border-[#F97316] hover:text-[#F97316]"}`}>
                  {p.cta}
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ── 연결 서비스 ── */}
      <section className="bg-[#F9FAFB] border-t border-[#E5E7EB] py-12 px-4">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-sm font-bold text-[#374151] mb-4 text-center">Haehan AI 패밀리 서비스</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {SERVICES.map((s) => (
              <a key={s.label} href={s.href} target="_blank"
                className="flex items-center gap-3 p-3 rounded-xl bg-white border border-[#E5E7EB] hover:shadow-sm hover:border-[#F97316] transition-all">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold shrink-0"
                  style={{ background: s.color }}>
                  {s.short}
                </div>
                <div>
                  <p className="text-xs font-bold text-[#111827]">{s.label}</p>
                  <p className="text-[11px] text-[#9CA3AF]">{s.desc}</p>
                </div>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* ── 하단 CTA ── */}
      <section className="bg-[#111827] py-16 px-4 text-center">
        <h2 className="text-2xl font-bold text-white mb-3">지금 바로 시작하세요</h2>
        <p className="text-[#9CA3AF] mb-8 max-w-md mx-auto">
          도면 하나 넣으면 서류 세 가지가 나옵니다. 회원가입 후 바로 사용 가능합니다.
        </p>
        {user ? (
          <Link href="/" className="inline-block px-8 py-3 rounded-xl bg-[#F97316] text-white font-semibold hover:bg-[#EA580C] transition-colors">
            대시보드 바로가기 →
          </Link>
        ) : (
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link href="/signup" className="px-8 py-3 rounded-xl bg-[#F97316] text-white font-semibold hover:bg-[#EA580C] transition-colors">
              무료 회원가입
            </Link>
            <Link href="/login" className="px-8 py-3 rounded-xl border border-[#374151] text-[#9CA3AF] font-semibold hover:border-[#6B7280] hover:text-white transition-colors">
              이미 계정이 있어요
            </Link>
          </div>
        )}
      </section>

      {/* ── 푸터 ── */}
      <footer className="border-t border-[#E5E7EB] py-8 px-4">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-[#9CA3AF]">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-[#F97316] flex items-center justify-center text-white font-bold text-[10px]">AI</div>
            <span>Haehan AI Autowork</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/" className="hover:text-[#6B7280]">대시보드</Link>
            <Link href="/signup" className="hover:text-[#6B7280]">회원가입</Link>
            <Link href="/login" className="hover:text-[#6B7280]">로그인</Link>
            <Link href="/mypage" className="hover:text-[#6B7280]">마이페이지</Link>
            <button onClick={() => setInquiryOpen(true)} className="hover:text-[#6B7280]">문의</button>
          </div>
          <p>© 2026 Haehan AI</p>
        </div>
      </footer>

      {inquiryOpen && <InquiryModal onClose={() => setInquiryOpen(false)} />}
    </div>
  );
}

function InquiryModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ name: "", contact: "", company: "", subject: "", message: "", website: "" });
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [err, setErr] = useState("");
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function submit() {
    if (!form.name.trim() || !form.message.trim()) { setErr("이름과 문의 내용을 입력해 주세요."); return; }
    setState("sending"); setErr("");
    try {
      const r = await fetch("/api/proxy/api/v1/inquiries", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "전송 실패");
      setState("done");
    } catch (e) { setState("error"); setErr(String(e)); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
        {state === "done" ? (
          <div className="text-center py-6">
            <p className="text-2xl mb-2">✅</p>
            <p className="text-lg font-bold text-[#111827]">문의가 접수되었습니다</p>
            <p className="text-sm text-[#6B7280] mt-1">빠른 시일 내에 답변드리겠습니다.</p>
            <button onClick={onClose} className="mt-5 px-5 py-2 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C]">닫기</button>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <p className="text-lg font-bold text-[#111827]">도입 문의</p>
              <button onClick={onClose} className="text-[#9CA3AF] hover:text-[#111827]">✕</button>
            </div>
            <div className="space-y-2.5">
              <input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="이름 *"
                className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2.5 text-sm outline-none focus:border-[#F97316]" />
              <input value={form.contact} onChange={(e) => set("contact", e.target.value)} placeholder="연락처 (이메일 또는 전화)"
                className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2.5 text-sm outline-none focus:border-[#F97316]" />
              <input value={form.company} onChange={(e) => set("company", e.target.value)} placeholder="회사/기관 (선택)"
                className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2.5 text-sm outline-none focus:border-[#F97316]" />
              <input value={form.subject} onChange={(e) => set("subject", e.target.value)} placeholder="제목"
                className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2.5 text-sm outline-none focus:border-[#F97316]" />
              <textarea value={form.message} onChange={(e) => set("message", e.target.value)} placeholder="문의 내용 *" rows={4}
                className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2.5 text-sm outline-none focus:border-[#F97316] resize-none" />
              {/* 허니팟(봇 차단) — 사용자 눈에 안 보임 */}
              <input value={form.website} onChange={(e) => set("website", e.target.value)} tabIndex={-1} autoComplete="off"
                style={{ position: "absolute", left: "-9999px" }} aria-hidden="true" />
            </div>
            {err && <p className="text-xs text-[#DC2626] mt-2">{err}</p>}
            <button onClick={submit} disabled={state === "sending"}
              className="mt-4 w-full py-2.5 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-50">
              {state === "sending" ? "전송 중…" : "문의 보내기"}
            </button>
            <p className="text-[11px] text-[#9CA3AF] mt-2 text-center">남겨주신 연락처로 답변드립니다.</p>
          </>
        )}
      </div>
    </div>
  );
}
