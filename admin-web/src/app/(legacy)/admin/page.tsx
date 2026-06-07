"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getMe, type UserInfo } from "@/lib/userAuth";
import { API_BASE } from "@/lib/assistant/api";

interface AdminCard {
  href: string;
  title: string;
  desc: string;
  color: string;
  bg: string;
  border: string;
}

const CARDS: AdminCard[] = [
  { href: "/admin/users",    title: "사용자 승인·관리", desc: "가입 승인 대기·전체 사용자",   color: "#F97316", bg: "#FFF7ED", border: "#FED7AA" },
  { href: "/admin/licenses", title: "라이선스 관리",    desc: "발급·조회·만료 관리",          color: "#7C3AED", bg: "#F5F3FF", border: "#DDD6FE" },
  { href: "/ops",            title: "운영센터",         desc: "서버 상태·감사 로그·배포",      color: "#374151", bg: "#F9FAFB", border: "#E5E7EB" },
  { href: "/settings",       title: "내 계정·비밀번호",  desc: "프로필·비밀번호 변경",          color: "#1D4ED8", bg: "#EFF6FF", border: "#BFDBFE" },
];

export default function AdminHubPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingCount, setPendingCount] = useState<number | null>(null);

  useEffect(() => {
    getMe().then((u) => {
      if (!u) { router.push("/login"); return; }
      if (u.role !== "owner" && u.role !== "admin") { router.replace("/"); return; }
      setUser(u);
      setLoading(false);
    });
  }, [router]);

  useEffect(() => {
    if (!user) return;
    fetch(`${API_BASE}/api/v1/users/pending`)
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setPendingCount(Array.isArray(d) ? d.length : 0))
      .catch(() => setPendingCount(null));
  }, [user]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center">
        <p className="text-sm text-[#6B7280]">로딩 중...</p>
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="min-h-screen bg-[#F9FAFB] px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-5">
        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#111827] flex items-center justify-center text-white font-bold text-xs">AI</div>
            <div>
              <h1 className="text-lg font-bold text-[#111827]">최고 관리자</h1>
              <p className="text-xs text-[#6B7280]">{user.name} · {user.email}</p>
            </div>
          </div>
          <Link href="/" className="text-sm text-[#6B7280] hover:text-[#111827] transition-colors">← 홈</Link>
        </div>

        {/* 승인 대기 요약 */}
        <Link href="/admin/users"
          className="block bg-white border border-[#E5E7EB] rounded-2xl p-5 hover:border-[#F97316] transition-colors">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-bold text-[#111827]">가입 승인 대기</p>
              <p className="text-xs text-[#6B7280] mt-1">새 사용자 가입을 검토·승인하세요</p>
            </div>
            <div className="flex items-center gap-2">
              <span className={`text-2xl font-bold ${pendingCount ? "text-[#F97316]" : "text-[#9CA3AF]"}`}>
                {pendingCount === null ? "—" : pendingCount}
              </span>
              <span className="text-xs text-[#9CA3AF]">건</span>
            </div>
          </div>
        </Link>

        {/* 관리 카드 그리드 */}
        <div className="grid grid-cols-2 gap-3">
          {CARDS.map((c) => (
            <Link key={c.href} href={c.href}
              className="bg-white border rounded-2xl p-5 transition-colors hover:shadow-sm"
              style={{ borderColor: c.border }}>
              <div className="w-9 h-9 rounded-lg flex items-center justify-center mb-3 text-sm font-bold"
                style={{ background: c.bg, color: c.color }}>
                {c.title.charAt(0)}
              </div>
              <p className="text-sm font-bold text-[#111827]">{c.title}</p>
              <p className="text-xs text-[#6B7280] mt-1">{c.desc}</p>
            </Link>
          ))}
        </div>

        <p className="text-center text-xs text-[#9CA3AF]">
          최고 관리자 전용 페이지 · owner/admin 권한 필요
        </p>
      </div>
    </div>
  );
}
