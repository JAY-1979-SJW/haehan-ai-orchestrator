"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getMe, changePassword, clearToken, type UserInfo } from "@/lib/userAuth";

const ROLE_LABEL: Record<string, string> = {
  user: "일반 사용자",
  admin: "관리자",
  owner: "최고 관리자",
  operator: "운영자",
};

const PLAN_LABEL: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  enterprise: "Enterprise",
};

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [newPwConfirm, setNewPwConfirm] = useState("");
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSuccess, setPwSuccess] = useState(false);

  useEffect(() => {
    getMe().then((u) => {
      if (!u) { router.push("/login"); return; }
      setUser(u);
      setLoading(false);
    });
  }, [router]);

  const handleLogout = () => {
    clearToken();
    router.push("/login");
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwError(null);
    setPwSuccess(false);
    if (newPw !== newPwConfirm) { setPwError("새 비밀번호가 일치하지 않습니다"); return; }
    if (newPw.length < 8) { setPwError("비밀번호는 최소 8자입니다"); return; }
    setPwLoading(true);
    try {
      await changePassword(curPw, newPw);
      setPwSuccess(true);
      setCurPw(""); setNewPw(""); setNewPwConfirm("");
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "변경 실패");
    } finally {
      setPwLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center">
        <p className="text-sm text-[#6B7280]">로딩 중...</p>
      </div>
    );
  }
  if (!user) return null;

  const isOwner = user.role === "owner" || user.role === "admin";
  const joinedAt = new Date(user.created_at).toLocaleDateString("ko-KR", {
    year: "numeric", month: "long", day: "numeric",
  });

  return (
    <div className="min-h-screen bg-[#F9FAFB] px-4 py-8">
      <div className="max-w-lg mx-auto space-y-4">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#F97316] flex items-center justify-center text-white font-bold text-xs">AI</div>
            <Link href="/" className="text-sm font-semibold text-[#111827] hover:text-[#F97316]">Haehan AI</Link>
            <span className="text-sm text-[#9CA3AF]">설정</span>
          </div>
          <button onClick={handleLogout}
            className="text-sm text-[#6B7280] hover:text-[#111827] transition-colors">
            로그아웃
          </button>
        </div>

        {/* 프로필 카드 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <div className="flex items-center gap-4 mb-5">
            <div className="w-14 h-14 rounded-full bg-[#FFF7ED] border-2 border-[#F97316] flex items-center justify-center text-[#F97316] font-bold text-xl">
              {user.name.charAt(0)}
            </div>
            <div>
              <p className="text-base font-bold text-[#111827]">{user.name}</p>
              <p className="text-sm text-[#6B7280]">{user.email}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-[#F9FAFB] border border-[#E5E7EB] px-4 py-3">
              <p className="text-xs text-[#9CA3AF] mb-1">역할</p>
              <p className="text-sm font-semibold text-[#111827]">{ROLE_LABEL[user.role] ?? user.role}</p>
            </div>
            <div className="rounded-xl bg-[#F9FAFB] border border-[#E5E7EB] px-4 py-3">
              <p className="text-xs text-[#9CA3AF] mb-1">플랜</p>
              <p className="text-sm font-semibold text-[#F97316]">{PLAN_LABEL[user.plan] ?? user.plan}</p>
            </div>
            <div className="col-span-2 rounded-xl bg-[#F9FAFB] border border-[#E5E7EB] px-4 py-3">
              <p className="text-xs text-[#9CA3AF] mb-1">가입일</p>
              <p className="text-sm font-semibold text-[#111827]">{joinedAt}</p>
            </div>
          </div>
        </div>

        {/* 최고 관리자 바로가기 (owner/admin 전용) */}
        {isOwner && (
          <Link href="/admin"
            className="block bg-[#111827] text-white border border-[#111827] rounded-2xl p-5 hover:bg-[#1F2937] transition-colors">
            <p className="text-sm font-bold">최고 관리자 페이지</p>
            <p className="text-xs text-[#9CA3AF] mt-1">사용자 승인·관리, 라이선스, 운영센터</p>
          </Link>
        )}

        {/* 비밀번호 변경 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <h2 className="text-sm font-bold text-[#111827] mb-4">비밀번호 변경</h2>
          <form onSubmit={handlePasswordChange} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">현재 비밀번호</label>
              <input type="password" value={curPw} onChange={(e) => setCurPw(e.target.value)} required
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent" />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">새 비밀번호</label>
              <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} required placeholder="최소 8자"
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent" />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">새 비밀번호 확인</label>
              <input type="password" value={newPwConfirm} onChange={(e) => setNewPwConfirm(e.target.value)} required
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent" />
            </div>
            {pwError && <div className="rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">{pwError}</div>}
            {pwSuccess && <div className="rounded-xl bg-[#F0FDF4] border border-[#BBF7D0] px-4 py-2.5 text-sm text-[#16A34A]">비밀번호가 변경되었습니다</div>}
            <button type="submit" disabled={pwLoading}
              className="w-full py-2.5 rounded-xl bg-[#111827] text-white text-sm font-semibold hover:bg-[#374151] disabled:opacity-50 transition-colors">
              {pwLoading ? "변경 중..." : "비밀번호 변경"}
            </button>
          </form>
        </div>

        <div className="text-center">
          <Link href="/" className="text-sm text-[#6B7280] hover:text-[#111827] transition-colors">← 홈으로</Link>
        </div>
      </div>
    </div>
  );
}
