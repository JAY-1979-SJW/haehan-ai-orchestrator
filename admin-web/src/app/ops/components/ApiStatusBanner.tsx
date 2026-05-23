"use client";

import { useEffect, useState } from "react";

type ApiStatus = "checking" | "live" | "unauthorized" | "error";

interface PanelStatus {
  label: string;
  path: string;
  status: ApiStatus;
}

async function checkEndpoint(path: string): Promise<ApiStatus> {
  try {
    const res = await fetch(`/api/v1${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
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
    { label: "approvals", path: "/ops/approvals", status: "checking" },
    { label: "web tasks", path: "/ops/web-tasks", status: "checking" },
    { label: "audit", path: "/ops/audit-events", status: "checking" },
    { label: "agents", path: "/ops/agents", status: "checking" },
    { label: "integrations", path: "/ops/integrations", status: "checking" },
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
    ? "Backend API auth/connection failed. Mock fallback is disabled."
    : allLive
    ? "Backend API connected. Showing live data."
    : checked
    ? `Backend API partially connected (${liveCount}/${panels.length}). Mock fallback is disabled.`
    : "Checking backend API status...";

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
        <span className="ml-auto text-gray-400">read-only</span>
      </div>
    </div>
  );
}
