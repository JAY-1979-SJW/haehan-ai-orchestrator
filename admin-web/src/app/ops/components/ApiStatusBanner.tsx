"use client";

import { useEffect, useState } from "react";

type ApiStatus = "checking" | "live" | "fallback" | "error";

interface PanelStatus {
  label: string;
  path: string;
  status: ApiStatus;
}

async function checkEndpoint(path: string): Promise<ApiStatus> {
  try {
    const res = await fetch(`/api/v1${path}`, {
      headers: { Authorization: "Bearer admin-token" },
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (res.ok) return "live";
    return "fallback";
  } catch {
    return "fallback";
  }
}

export function ApiStatusBanner() {
  const [panels, setPanels] = useState<PanelStatus[]>([
    { label: "승인 대기", path: "/ops/approvals", status: "checking" },
    { label: "웹 작업", path: "/ops/web-tasks", status: "checking" },
    { label: "감사 로그", path: "/ops/audit-events", status: "checking" },
    { label: "에이전트", path: "/ops/agents", status: "checking" },
    { label: "연동 현황", path: "/ops/integrations", status: "checking" },
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
            results[i].status === "fulfilled"
              ? results[i].value
              : "fallback",
        }))
      );
      setChecked(true);
    }
    check();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const liveCount = panels.filter((p) => p.status === "live").length;
  const allFallback = checked && liveCount === 0;
  const allLive = checked && liveCount === panels.length;

  const bannerBg = allFallback
    ? "bg-yellow-50 border-yellow-200"
    : allLive
    ? "bg-green-50 border-green-200"
    : "bg-blue-50 border-blue-200";

  const bannerText = allFallback
    ? "백엔드 API 미연결 — 안전한 대체 데이터 표시 중 (read-only 모드)"
    : allLive
    ? "백엔드 API 연결됨 — 실시간 데이터 표시 중"
    : checked
    ? `백엔드 API 부분 연결 (${liveCount}/${panels.length})`
    : "API 상태 확인 중…";

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
                    : "bg-yellow-400"
                }`}
              />
              <span className="text-gray-500">{p.label}</span>
            </span>
          ))}
        </div>
        <span className="ml-auto text-gray-400">⚠️ 위험 실행 비활성 · read-only</span>
      </div>
    </div>
  );
}
