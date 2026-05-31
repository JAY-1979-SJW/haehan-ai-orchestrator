"use client";
import { useEffect, useState, useCallback } from "react";
import { API_BASE } from "@/lib/assistant/api";


interface SiteStatus {
  key: string;
  label: string;
  icon: string;
  color: string;
  status: string;
  detail: string;
  href: string;
  has_session_cookie: boolean;
  checked_at: string;
  login_url: string;
}

interface SessionData {
  checked_at: string;
  cdp_available: boolean;
  sites: SiteStatus[];
}

const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string; border: string }> = {
  LOGGED_IN:       { label: "로그인됨",    bg: "#F0FDF4", text: "#16A34A", border: "#BBF7D0" },
  SESSION_EXPIRED: { label: "세션 만료",   bg: "#FEF2F2", text: "#DC2626", border: "#FECACA" },
  LOGIN_REQUIRED:  { label: "로그인 필요", bg: "#FEF2F2", text: "#DC2626", border: "#FECACA" },
  CHALLENGE:       { label: "추가 인증",   bg: "#FEF3C7", text: "#92400E", border: "#FDE68A" },
  ERROR:           { label: "오류",        bg: "#FEF2F2", text: "#DC2626", border: "#FECACA" },
  NO_TAB:          { label: "탭 없음",     bg: "#F9FAFB", text: "#6B7280", border: "#E5E7EB" },
  UNKNOWN:         { label: "미확인",      bg: "#F9FAFB", text: "#9CA3AF", border: "#E5E7EB" },
};

export default function SessionStatusPanel() {
  const [data, setData]       = useState<SessionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/sessions/status`);
      if (r.ok) setData(await r.json());
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await fetch(`${API_BASE}/api/v1/sessions/refresh`, {
        method: "POST",
      });
      if (r.ok) setData(await r.json());
    } catch { /* ignore */ }
    finally { setRefreshing(false); }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 60_000);
    const onFocus = () => fetchStatus();
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(id); window.removeEventListener("focus", onFocus); };
  }, [fetchStatus]);

  const checkedAt = data?.checked_at
    ? new Date(data.checked_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })
    : null;

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-sm font-bold text-[#111827]">앱별 로그인 세션</p>
          {checkedAt && <p className="text-xs text-[#9CA3AF] mt-0.5">최종 확인: {checkedAt}</p>}
        </div>
        <div className="flex items-center gap-2">
          {data && !data.cdp_available && (
            <span className="text-xs text-[#DC2626] font-semibold">CDP 미연결</span>
          )}
          <button onClick={refresh} disabled={refreshing || loading}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F9FAFB] border border-[#E5E7EB] text-[#374151] hover:border-[#F97316] hover:text-[#F97316] disabled:opacity-40 transition-colors">
            {refreshing ? "확인 중..." : "새로고침"}
          </button>
        </div>
      </div>

      {/* 사이트 목록 */}
      {loading && !data ? (
        <p className="text-xs text-[#9CA3AF] text-center py-4">로딩 중...</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {(data?.sites ?? []).map((s) => {
            const cfg = STATUS_CONFIG[s.status] ?? STATUS_CONFIG["UNKNOWN"];
            return (
              <div key={s.key}
                className="rounded-xl border p-3 flex flex-col gap-1.5"
                style={{ background: cfg.bg, borderColor: cfg.border }}>
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0"
                    style={{ background: s.color }}>
                    {s.icon}
                  </div>
                  <span className="text-xs font-bold text-[#111827] truncate">{s.label}</span>
                </div>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full self-start"
                  style={{ background: cfg.border, color: cfg.text }}>
                  {cfg.label}
                </span>
                {s.status !== "LOGGED_IN" && s.login_url && (
                  <a href={s.login_url} target="_blank" rel="noopener noreferrer"
                    className="text-[10px] font-semibold underline mt-0.5"
                    style={{ color: s.color }}>
                    로그인 →
                  </a>
                )}
                {s.detail && s.status !== "LOGGED_IN" && (
                  <p className="text-[10px] text-[#6B7280] leading-tight">{s.detail}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
