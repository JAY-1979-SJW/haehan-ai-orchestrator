"use client";
import { useState } from "react";
import Link from "next/link";
import { signup } from "@/lib/userAuth";

export default function SignupPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false); // 가입 접수 → 승인 대기 안내

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) { setError("비밀번호가 일치하지 않습니다"); return; }
    if (password.length < 8) { setError("비밀번호는 최소 8자입니다"); return; }
    setLoading(true);
    try {
      // 가입은 즉시 로그인되지 않음 — 관리자 승인 후 로그인 가능
      await signup(email, name, password);
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "회원가입 실패");
    } finally {
      setLoading(false);
    }
  };

  // 가입 접수 완료 → 승인 대기 안내 화면
  if (submitted) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <div className="flex items-center justify-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl bg-[#F97316] flex items-center justify-center text-white font-bold text-sm">AI</div>
            <span className="text-xl font-bold text-[#111827]">Haehan AI</span>
          </div>
          <div className="bg-white border border-[#E5E7EB] rounded-2xl p-8 shadow-sm text-center">
            <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-[#FFF7ED] flex items-center justify-center text-2xl">✓</div>
            <h1 className="text-lg font-bold text-[#111827] mb-2">가입이 접수되었습니다</h1>
            <p className="text-sm text-[#6B7280] mb-1">관리자 승인 후 로그인하실 수 있습니다.</p>
            <p className="text-sm text-[#6B7280] mb-6">승인이 완료되면 입력하신 이메일로 안내드립니다.</p>
            <Link
              href="/login"
              className="inline-block w-full py-2.5 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] transition-colors"
            >
              로그인 화면으로
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* 로고 */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-[#F97316] flex items-center justify-center text-white font-bold text-sm">AI</div>
          <span className="text-xl font-bold text-[#111827]">Haehan AI</span>
        </div>

        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-8 shadow-sm">
          <h1 className="text-lg font-bold text-[#111827] mb-1">회원가입</h1>
          <p className="text-sm text-[#6B7280] mb-6">가입 후 관리자 승인을 거쳐 이용하실 수 있습니다</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[#374151] mb-1">이름</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="홍길동"
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[#374151] mb-1">이메일</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="example@email.com"
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[#374151] mb-1">비밀번호</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="최소 8자"
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[#374151] mb-1">비밀번호 확인</label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                placeholder="비밀번호 재입력"
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
              />
            </div>

            {error && (
              <div className="rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "처리 중..." : "가입하기"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-[#6B7280]">
            이미 계정이 있으신가요?{" "}
            <Link href="/login" className="text-[#F97316] font-semibold hover:underline">
              로그인
            </Link>
          </p>

          <p className="mt-3 text-center">
            <Link href="/" className="text-sm text-[#6B7280] hover:text-[#111827] transition-colors">
              ← 홈으로 돌아가기 (로그인 없이 둘러보기)
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
