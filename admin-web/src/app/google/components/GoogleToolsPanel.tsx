"use client";

import { useState } from "react";

/**
 * 구글 각종 도구(캘린더/드라이브/문서/시트/유튜브/GCP) 버튼 연결.
 * 백엔드(ai_orchestrator/connectors/google/actions.py)를 기존 공용 프록시
 * (/api/proxy/[...path])로 호출한다. 2026-09-29: 백엔드 기본값이 OAuth API로
 * 전환됨(source=api 기본, CDP는 ?source=cdp 로 fallback만 유지) — 이 컴포넌트는
 * 변경 없음, 신규 백엔드 로직 없음. 읽기전용 GET만 연결(캘린더 이벤트 생성 등
 * 쓰기 액션은 제외).
 */

interface ToolDef {
  key: string;
  label: string;
  path: string;
  render: (data: Record<string, unknown>) => React.ReactNode;
}

function CalendarList({ events }: { events: { title: string; aria: string }[] }) {
  if (events.length === 0) return <div className="text-xs text-gray-500">일정이 없습니다.</div>;
  return (
    <ul className="space-y-1">
      {events.map((ev, i) => (
        <li key={i} className="text-xs text-gray-700">
          {ev.title}
        </li>
      ))}
    </ul>
  );
}

function NamedList({ items }: { items: { name: string; id?: string; url?: string }[] }) {
  if (items.length === 0) return <div className="text-xs text-gray-500">항목이 없습니다.</div>;
  return (
    <ul className="space-y-1">
      {items.map((it, i) => (
        <li key={it.id || i} className="text-xs text-gray-700">
          {it.url ? (
            <a href={it.url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
              {it.name}
            </a>
          ) : (
            it.name
          )}
        </li>
      ))}
    </ul>
  );
}

const TOOLS: ToolDef[] = [
  {
    key: "calendar-today",
    label: "캘린더: 오늘 일정",
    path: "/api/proxy/api/v1/google/tools/calendar/today",
    render: (d) => <CalendarList events={(d.events as { title: string; aria: string }[]) ?? []} />,
  },
  {
    key: "calendar-week",
    label: "캘린더: 이번 주 일정",
    path: "/api/proxy/api/v1/google/tools/calendar/week",
    render: (d) => <CalendarList events={(d.events as { title: string; aria: string }[]) ?? []} />,
  },
  {
    key: "drive-recent",
    label: "드라이브: 최근 파일",
    path: "/api/proxy/api/v1/google/tools/drive/recent",
    render: (d) => <NamedList items={(d.files as { name: string; id?: string }[]) ?? []} />,
  },
  {
    key: "docs-recent",
    label: "문서: 최근 목록",
    path: "/api/proxy/api/v1/google/tools/docs/recent",
    render: (d) => <NamedList items={(d.docs as { name: string; id?: string; url?: string }[]) ?? []} />,
  },
  {
    key: "sheets-recent",
    label: "스프레드시트: 최근 목록",
    path: "/api/proxy/api/v1/google/tools/sheets/recent",
    render: (d) => <NamedList items={(d.sheets as { name: string; id?: string; url?: string }[]) ?? []} />,
  },
  {
    key: "youtube-studio-status",
    label: "YouTube 스튜디오 상태",
    path: "/api/proxy/api/v1/google/tools/youtube/studio/status",
    render: (d) => {
      const ch = d.channel as
        | { title?: string; subscriber_count?: string; video_count?: string; view_count?: string }
        | undefined;
      if (!ch || !ch.title) return <div className="text-xs text-gray-500">연결된 채널 없음 (토큰 없음).</div>;
      return (
        <div className="text-xs text-gray-700">
          {ch.title} · 구독자 {ch.subscriber_count} · 동영상 {ch.video_count} · 조회수 {ch.view_count}
        </div>
      );
    },
  },
  {
    key: "gcp-status",
    label: "GCP 프로젝트 상태",
    path: "/api/proxy/api/v1/google/tools/gcp/status",
    render: (d) => (
      <div className="text-xs text-gray-700">
        <div>{String(d.project ?? "-")}</div>
        {Array.isArray(d.alerts) && d.alerts.length > 0 && (
          <ul className="mt-1 list-disc pl-4 text-orange-700">
            {(d.alerts as string[]).map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        )}
      </div>
    ),
  },
];

interface ToolState {
  loading: boolean;
  error: string | null;
  data: Record<string, unknown> | null;
}

export function GoogleToolsPanel() {
  const [state, setState] = useState<Record<string, ToolState>>({});

  async function run(tool: ToolDef) {
    setState((s) => ({ ...s, [tool.key]: { loading: true, error: null, data: null } }));
    try {
      const res = await fetch(tool.path);
      const data = await res.json();
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      setState((s) => ({ ...s, [tool.key]: { loading: false, error: null, data } }));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setState((s) => ({ ...s, [tool.key]: { loading: false, error: message, data: null } }));
    }
  }

  return (
    <section data-testid="google-tools-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">구글 도구 (OAuth API 기반)</h2>
      <div className="space-y-3">
        {TOOLS.map((tool) => {
          const s = state[tool.key];
          return (
            <div key={tool.key} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-800">{tool.label}</span>
                <button
                  type="button"
                  onClick={() => run(tool)}
                  disabled={s?.loading}
                  className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {s?.loading ? "조회 중..." : "조회"}
                </button>
              </div>
              {s?.error && (
                <div className="mt-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {s.error}
                </div>
              )}
              {s?.data && <div className="mt-2">{tool.render(s.data)}</div>}
            </div>
          );
        })}
      </div>
    </section>
  );
}
