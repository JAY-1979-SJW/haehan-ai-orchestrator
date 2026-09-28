"use client";

import { useEffect, useState } from "react";
import { buildApiUrl } from "@/lib/api";

type ApiStatus = "checking" | "live" | "unauthorized" | "error";

interface PanelStatus {
  label: string;
  path: string;
  status: ApiStatus;
}

async function checkEndpoint(path: string): Promise<ApiStatus> {
  try {
    // 상태 체크도 인증 필요 — localStorage 토큰을 Bearer 로 부착(미부착 시 401=unauthorized 표시되던 문제).
    // 경로는 buildApiUrl()(src/lib/api.ts)로 만든다 — "/api/v1..." 을 직접 fetch하면
    // NEXT_PUBLIC_API_BASE_PATH(개발: /api/proxy/api/v1, 운영: /orchestrator/api/v1) 를
    // 거치지 않아 dev 환경에서 항상 404 였다(2026-09-28 Electron e2e 진단으로 재현·확인).
    const token = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
    const res = await fetch(buildApiUrl(`/api/v1${path}`), {
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) return "live";
    if (res.status === 401 || res.status === 403) return "unauthorized";
    return "error";
  } catch {
    return "error";
  }
}

export function ApiStatusBanner() {
  const [panels, setPanels] = useState<PanelStatus[]>([
    { label: "승인 대기", path: "/ops/approvals", status: "checking" },
    { label: "웹 작업", path: "/ops/web-tasks", status: "checking" },
    { label: "감사 로그", path: "/ops/audit-events", status: "checking" },
    { label: "에이전트", path: "/ops/agents", status: "checking" },
    { label: "연동", path: "/ops/integrations", status: "checking" },
  ]);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      const results = await Promise.allSettled(
        panels.map((p) => checkEndpoint(p.path))
      );
      if (cancelled) return;
      setPanels((prev) =>
        prev.map((p, i) => ({
          ...p,
          status:
            results[i].status === "fulfilled" ? results[i].value : "error",
        }))
      );
      setChecked(true);
    }
    check();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const liveCount = panels.filter((p) => p.status === "live").length;
  const allUnavailable = checked && liveCount === 0;
  const allLive = checked && liveCount === panels.length;

  const bannerBg = allUnavailable
    ? "bg-red-50 border-red-200"
    : allLive
    ? "bg-green-50 border-green-200"
    : "bg-blue-50 border-blue-200";

  const bannerText = allUnavailable
    ? "백엔드 연결/인증 실패 — 데이터를 불러올 수 없습니다."
    : allLive
    ? "백엔드 연결됨 — 실시간 데이터 표시 중"
    : checked
    ? `백엔드 일부 연결됨 (${liveCount}/${panels.length})`
    : "백엔드 상태 확인 중…";

  return (
    <div
      data-testid="api-status-banner"
      className={`rounded-lg border px-4 py-3 text-xs ${bannerBg}`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-medium text-gray-700">{bannerText}</span>
        <div className="flex flex-wrap gap-2">
          {panels.map((p) => (
            <span key={p.path} className="flex items-center gap-1">
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${
                  p.status === "live"
                    ? "bg-green-500"
                    : p.status === "checking"
                    ? "bg-gray-300"
                    : p.status === "unauthorized"
                    ? "bg-red-500"
                    : "bg-yellow-400"
                }`}
              />
              <span className="text-gray-500">{p.label}</span>
            </span>
          ))}
        </div>
        <span className="ml-auto text-gray-400">읽기 전용</span>
      </div>
    </div>
  );
}
