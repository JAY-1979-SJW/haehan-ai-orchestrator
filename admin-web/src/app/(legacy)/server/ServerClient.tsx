"use client";

import { useCallback, useEffect, useState } from "react";

interface PortState { label: string; open: boolean }
interface Instance {
  hostname: string; role: string; os: string; flavor: string; os_volume: string;
  user: string; public_ip: string; domains: string[]; ports: Record<string, PortState>;
}
interface HealthItem { name: string; url: string; status: number | null }
interface Overview {
  ok: boolean; zone: string; project: string;
  instances: Instance[]; health: HealthItem[];
  deploy: { available: boolean; ok?: boolean | null; status?: string; created_at?: string; service?: string };
  links: Record<string, string>;
  note: string;
}

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const t = window.localStorage.getItem("haehan_ai_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function Dot({ ok }: { ok: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-[#16A34A]" : "bg-[#DC2626]"}`} />;
}

export function ServerClient() {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch("/api/proxy/api/v1/server/overview", { headers: authHeader() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openConsole = (url: string) => {
    // 로그인된 CDP 브라우저에서 열기 시도, 실패 시 새 탭
    fetch("/api/proxy/api/v1/smartstore/open", { method: "POST", headers: { "Content-Type": "application/json", ...authHeader() }, body: JSON.stringify({ url }) })
      .catch(() => {})
      .finally(() => window.open(url, "_blank"));
  };

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex items-center gap-2">
        <button onClick={load} disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-[#F97316] text-white text-xs font-semibold hover:bg-[#EA580C] disabled:opacity-50">
          {loading ? "확인 중…" : "🔄 상태 새로고침"}
        </button>
        {data && (
          <span className="text-xs text-[#6B7280]">존 {data.zone} · 프로젝트 {data.project}</span>
        )}
      </div>

      {error && <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3 text-sm text-[#DC2626]">오류: {error}</div>}

      {/* 도메인 헬스 */}
      {data && (
        <div className="border border-[#E5E7EB] rounded-2xl bg-white p-4">
          <p className="text-sm font-bold text-[#111827] mb-3">웹 서비스 상태</p>
          <div className="flex flex-wrap gap-3">
            {data.health.map((h) => (
              <div key={h.name} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-[#F9FAFB] border border-[#F3F4F6]">
                <Dot ok={h.status !== null && h.status < 500} />
                <span className="text-sm text-[#111827]">{h.name}</span>
                <span className="text-xs text-[#9CA3AF]">{h.status ?? "응답없음"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 인스턴스 */}
      {data?.instances.map((inst) => (
        <div key={inst.hostname} className="border border-[#E5E7EB] rounded-2xl bg-white p-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <p className="text-sm font-bold text-[#111827]">{inst.hostname} <span className="text-xs font-normal text-[#9CA3AF]">— {inst.role}</span></p>
              <p className="text-xs text-[#6B7280] mt-0.5">{inst.os} · {inst.flavor} · {inst.os_volume} · {inst.user}@{inst.public_ip}</p>
              <p className="text-xs text-[#9CA3AF] mt-0.5">{inst.domains.join(", ")}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            {Object.entries(inst.ports).map(([port, st]) => (
              <div key={port} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#F9FAFB] border border-[#F3F4F6]">
                <Dot ok={st.open} />
                <span className="text-xs text-[#111827]">{st.label}</span>
                <span className="text-[10px] text-[#9CA3AF]">{port}</span>
                {!st.open && (port === "22") && <span className="text-[10px] text-[#DC2626] font-semibold">차단</span>}
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* 배포 상태 */}
      {data && (
        <div className="border border-[#E5E7EB] rounded-2xl bg-white p-4">
          <p className="text-sm font-bold text-[#111827] mb-2">배포 상태</p>
          {data.deploy.available ? (
            <div className="text-sm text-[#374151] space-y-1">
              <p>결과: <span className={data.deploy.ok ? "text-[#16A34A]" : "text-[#DC2626]"}>{data.deploy.ok ? "성공" : "실패"}</span> · {data.deploy.status}</p>
              {data.deploy.created_at && <p className="text-xs text-[#9CA3AF]">{data.deploy.created_at}</p>}
            </div>
          ) : (
            <p className="text-sm text-[#9CA3AF]">최근 배포 기록 없음 ({data.deploy.status})</p>
          )}
        </div>
      )}

      {/* 안내 + 콘솔 링크 */}
      {data && (
        <div className="border border-[#FDE68A] bg-[#FFFBEB] rounded-2xl p-4 space-y-3">
          <p className="text-sm text-[#B45309]">ℹ️ {data.note}</p>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => openConsole(data.links.console)}
              className="px-3 py-1.5 rounded-lg bg-white border border-[#E5E7EB] text-xs font-semibold text-[#374151] hover:bg-[#F9FAFB]">
              🌐 IXcloud 콘솔 열기 (방화벽/보안그룹)
            </button>
            <button onClick={() => openConsole(data.links.security_group_manual)}
              className="px-3 py-1.5 rounded-lg bg-white border border-[#E5E7EB] text-xs font-semibold text-[#374151] hover:bg-[#F9FAFB]">
              📖 보안그룹 매뉴얼
            </button>
          </div>
        </div>
      )}

      {!data && !loading && !error && (
        <p className="text-sm text-[#9CA3AF]">상태를 불러오는 중…</p>
      )}
    </div>
  );
}
