"use client";
import { useState, useEffect, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";

interface PendingUser {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export default function UserApprovalPage() {
  const [pending, setPending] = useState<PendingUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // /api/proxy 가 관리자(Basic Auth) 자격을 자동 주입 — admin/licenses 와 동일 모델
      const r = await fetch(`${API_BASE}/api/v1/users/pending`);
      if (!r.ok) throw new Error(`승인 대기 목록을 불러오지 못했습니다 (${r.status})`);
      const d = await r.json();
      setPending(Array.isArray(d) ? d : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "목록 로드 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const approve = async (user: PendingUser) => {
    if (!confirm(`${user.name}(${user.email}) 님을 승인하시겠습니까?\n승인하면 즉시 로그인하여 서비스를 사용할 수 있습니다.`)) return;
    setApproving(user.id);
    setError(null);
    try {
      const r = await fetch(`${API_BASE}/api/v1/users/${encodeURIComponent(user.id)}/approve`, {
        method: "POST",
      });
      if (!r.ok) throw new Error(`승인 처리 실패 (${r.status})`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "승인 실패");
    } finally {
      setApproving(null);
    }
  };

  return (
    <PageShell title="회원 승인" description="가입 신청한 사용자를 승인합니다" chatDomain="admin">
      <div className="space-y-6">

        {/* 통계 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 text-center">
            <p className="text-2xl font-bold text-[#F97316]">{pending.length}</p>
            <p className="text-xs text-[#6B7280] mt-1">승인 대기</p>
          </div>
          <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 text-center flex items-center justify-center">
            <button onClick={load} disabled={loading}
              className="text-sm text-[#6B7280] hover:text-[#111827] disabled:opacity-40">
              {loading ? "불러오는 중..." : "↻ 새로고침"}
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-xl bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5 text-sm text-[#DC2626]">
            {error}
          </div>
        )}

        {/* 대기 목록 */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-[#E5E7EB]">
            <p className="text-sm font-bold text-[#111827]">승인 대기 중인 가입 신청</p>
          </div>
          <div className="divide-y divide-[#F3F4F6]">
            {!loading && pending.length === 0 && (
              <p className="text-sm text-[#9CA3AF] text-center py-10">승인 대기 중인 신청이 없습니다</p>
            )}
            {pending.map((u) => (
              <div key={u.id} className="px-5 py-4 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-[#111827]">{u.name}</span>
                    <span className="text-xs text-[#6B7280]">{u.email}</span>
                  </div>
                  <p className="text-xs text-[#9CA3AF] mt-1">
                    신청: {new Date(u.created_at).toLocaleString("ko-KR")}
                  </p>
                </div>
                <button onClick={() => approve(u)} disabled={approving === u.id}
                  className="text-sm px-4 py-2 bg-[#16A34A] text-white font-semibold rounded-lg hover:bg-[#15803D] disabled:opacity-40 shrink-0">
                  {approving === u.id ? "승인 중..." : "승인"}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </PageShell>
  );
}
