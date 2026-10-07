"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getMe, changePassword, clearToken, getBuildInfo, getDesktopSetupStatus, type BuildInfo, type UserInfo } from "@/lib/userAuth";
import { MarketingOpsSwitch } from "@/components/settings/MarketingOpsSwitch";

const ROLE_LABEL: Record<string, string> = {
  user: "일반 사용자",
  admin: "관리자",
  owner: "오너",
  operator: "운영자",
};

const PLAN_LABEL: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  enterprise: "Enterprise",
};

export default function MyPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [build, setBuild] = useState<BuildInfo | null>(null);
  const [isDesktop, setIsDesktop] = useState(false);

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

  useEffect(() => {
    getBuildInfo().then(setBuild);
    // 백엔드가 데스크톱 모드에서만 응답한다(서버 모드는 404 → null). 화면에서 따로 추측하지 않는다.
    getDesktopSetupStatus().then((st) => setIsDesktop(st !== null));
  }, []);

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

  // 데스크톱 소유자 모드는 created_at 이 빈 문자열이다 — new Date("") 는 "Invalid Date" 로 보이므로 값이 없거나 잘못되면 "-"
  const joinedDate = new Date(user.created_at);
  const joinedAt =
    user.created_at && !Number.isNaN(joinedDate.getTime())
      ? joinedDate.toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" })
      : "-";

  return (
    <div className="min-h-screen bg-[#F9FAFB] px-4 py-8">
      <div className="max-w-lg mx-auto space-y-4">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#F97316] flex items-center justify-center text-white font-bold text-xs">AI</div>
            <Link href="/" className="text-sm font-semibold text-[#111827] hover:text-[#F97316]">Haehan AI</Link>
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

        {/* 기능 스위치 — 관리자·오너만(서버 API 도 admin·owner 전용) */}
        {(user.role === "admin" || user.role === "owner") && <MarketingOpsSwitch />}

        {/* 비밀번호 변경 — 데스크톱(서버가 desktop-setup-status 로 알려 줌)은 비밀번호가 없어 숨긴다. 서버 모드는 그대로 보인다 */}
        {!isDesktop && (
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <h2 className="text-sm font-bold text-[#111827] mb-4">비밀번호 변경</h2>
          <form onSubmit={handlePasswordChange} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">현재 비밀번호</label>
              <input
                type="password"
                value={curPw}
                onChange={(e) => setCurPw(e.target.value)}
                required
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">새 비밀번호</label>
              <input
                type="password"
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                required
                placeholder="최소 8자"
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#374151] mb-1">새 비밀번호 확인</label>
              <input
                type="password"
                value={newPwConfirm}
                onChange={(e) => setNewPwConfirm(e.target.value)}
                required
                className="w-full border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:border-transparent"
              />
            </div>

            {pwError && (
              <div className="rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">{pwError}</div>
            )}
            {pwSuccess && (
              <div className="rounded-xl bg-[#F0FDF4] border border-[#BBF7D0] px-4 py-2.5 text-sm text-[#16A34A]">비밀번호가 변경되었습니다</div>
            )}

            <button
              type="submit"
              disabled={pwLoading}
              className="w-full py-2.5 rounded-xl bg-[#111827] text-white text-sm font-semibold hover:bg-[#374151] disabled:opacity-50 transition-colors"
            >
              {pwLoading ? "변경 중..." : "비밀번호 변경"}
            </button>
          </form>
        </div>
        )}

        {/* 앱 정보 — 어느 빌드인지 확인(문의·진단용) */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-[#111827] mb-3">앱 정보</h2>
          <dl className="text-sm text-[#374151] space-y-1.5" data-testid="build-info">
            <div className="flex justify-between">
              <dt className="text-[#6B7280]">빌드(커밋)</dt>
              <dd className="font-mono">{build ? (build.git_sha === "unknown" ? "알 수 없음" : build.git_sha.slice(0, 7)) : "확인 불가"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#6B7280]">빌드 시각</dt>
              <dd className="font-mono">{build ? (build.build_time === "unknown" ? "알 수 없음" : build.build_time) : "확인 불가"}</dd>
            </div>
          </dl>
        </div>

        {/* 홈으로 */}
        <div className="text-center">
          <Link href="/" className="text-sm text-[#6B7280] hover:text-[#111827] transition-colors">
            ← 홈으로
          </Link>
        </div>
      </div>
    </div>
  );
}
