"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { SiteMapExploreCard } from "@/components/sitemap/SiteMapExploreCard";
import {
  AUTH_LABEL,
  CATEGORIES,
  CATEGORY_LABEL,
  RISK_LABEL,
  STATE_LABEL,
  siteMapApi,
  type Category,
  type ExploreRequestSummary,
  type HostSummary,
  type MapTask,
  type Risk,
  type SiteMap,
  type TaskState,
} from "./api";

/**
 * 사이트 업무 지도 화면 — 왼쪽: 탐색해 둔 사이트 목록, 오른쪽: 업무 표 · 상세(절차·입력 필드) · 이름·목적·분류 확정 · 검증 결과 기록.
 * 이 화면은 외부 사이트에 접속하지 않는다(저장된 지도를 읽고 고칠 뿐). 위험 등급은 여기서 바꿀 수 없다(낮추기 금지).
 */

const RISK_STYLE: Record<Risk, string> = {
  read: "bg-green-100 text-green-800",
  write: "bg-amber-100 text-amber-800",
  submit: "bg-red-100 text-red-800",
};
const STATE_STYLE: Record<TaskState, string> = {
  observed: "bg-gray-100 text-gray-700",
  verified: "bg-green-100 text-green-800",
  stale: "bg-orange-100 text-orange-800",
};
const field = "w-full rounded-lg border border-[#E5E7EB] px-2 py-1 text-[12px]";
const btn = "rounded-lg border border-[#E5E7EB] bg-white px-3 py-1 text-[12px] hover:bg-[#F9FAFB] disabled:opacity-50";
const btnPrimary = "rounded-lg border border-[#F97316] bg-[#F97316] px-3 py-1 text-[12px] text-white hover:bg-[#EA580C] disabled:opacity-50";
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const day = (iso: string) => (iso ? iso.slice(0, 10) : "-");
const LIVE_EXPLORE = new Set(["pending", "running"]);

function Chip({ cls, children }: { cls: string; children: React.ReactNode }) {
  return <span className={`rounded-full px-2 py-[1px] text-[11px] ${cls}`}>{children}</span>;
}

export function SiteMapApp() {
  const [hosts, setHosts] = useState<HostSummary[]>([]);
  const [host, setHost] = useState<string | null>(null);
  const [siteMap, setSiteMap] = useState<SiteMap | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [requests, setRequests] = useState<ExploreRequestSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshHosts = useCallback(async () => {
    try {
      setHosts(await siteMapApi.hosts());
      setRequests(await siteMapApi.exploreRequests());
    } catch (e) {
      setError(errText(e));
    }
  }, []);

  const loadMap = useCallback(async (h: string) => {
    try {
      setSiteMap(await siteMapApi.map(h));
    } catch (e) {
      setSiteMap(null);
      setError(errText(e));
    }
  }, []);

  useEffect(() => {
    void refreshHosts();
  }, [refreshHosts]);

  function pickHost(h: string) {
    setHost(h);
    setTaskId(null);
    setError(null);
    setNotice(null);
    void loadMap(h);
  }

  async function act(run: () => Promise<unknown>, okMessage: string) {
    if (!host) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await run();
      setNotice(okMessage);
      await Promise.all([loadMap(host), refreshHosts()]);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const tasks = useMemo(() => siteMap?.tasks ?? [], [siteMap]);
  const selected = useMemo(() => tasks.find((t) => t.id === taskId) ?? null, [tasks, taskId]);
  const pendingCards = requests.filter((r) => LIVE_EXPLORE.has(r.status));
  const unclassified = tasks.filter((t) => t.category === "unclassified").length;

  return (
    <div className="space-y-3 p-3 text-[13px]">
      {error && <div className="rounded-lg bg-red-50 p-2 text-red-700" role="alert">{error}</div>}
      {notice && <div className="rounded-lg bg-green-50 p-2 text-green-800">{notice}</div>}

      {pendingCards.length > 0 && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-3" data-testid="sitemap-pending-explores">
          <div className="mb-1 font-semibold">탐색 요청 ({pendingCards.length})</div>
          {pendingCards.map((r) => (
            <SiteMapExploreCard key={r.id} requestId={r.id} />
          ))}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
        <HostList hosts={hosts} host={host} onPick={pickHost} />
        <div className="space-y-3">
          {!host && <div className="rounded-xl border border-dashed border-[#D1D5DB] p-6 text-center text-[#6B7280]">왼쪽에서 사이트를 고르세요. 지도가 없으면 AI 업무 창에서 탐색을 요청하세요.</div>}
          {host && siteMap && (
            <>
              <div className="rounded-xl border border-[#E5E7EB] bg-white p-3">
                <div className="text-[15px] font-semibold">{siteMap.host}</div>
                <div className="text-[12px] text-[#6B7280]">
                  {AUTH_LABEL[siteMap.auth]} 사이트 · 업무 {tasks.length}개 · 마지막 갱신 {day(siteMap.updated_at)}
                  {unclassified > 0 && <span className="ml-2 rounded bg-violet-100 px-2 text-violet-800">분류 미정 {unclassified}</span>}
                </div>
              </div>
              <TaskTable tasks={tasks} taskId={taskId} onPick={setTaskId} />
              {selected && (
                <TaskDetail
                  key={selected.id}
                  task={selected}
                  busy={busy}
                  onSave={(input) => act(() => siteMapApi.classify(host, { task_id: selected.id, ...input }), "업무 정보를 저장했습니다")}
                  onOutcome={(ok) =>
                    act(() => siteMapApi.outcome(host, selected.id, ok), ok ? "검증됨으로 기록했습니다" : "재확인 필요로 기록했습니다")
                  }
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function HostList({ hosts, host, onPick }: { hosts: HostSummary[]; host: string | null; onPick: (h: string) => void }) {
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-3">
      <div className="mb-2 font-semibold">탐색한 사이트 ({hosts.length})</div>
      {hosts.length === 0 && <div className="text-[#6B7280]">아직 탐색한 사이트가 없습니다.</div>}
      <ul className="space-y-1">
        {hosts.map((h) => (
          <li key={h.host}>
            <button
              onClick={() => onPick(h.host)}
              className={`w-full rounded-lg border px-2 py-1 text-left ${host === h.host ? "border-[#F97316] bg-[#FFF7ED]" : "border-[#E5E7EB] hover:bg-[#F9FAFB]"}`}
            >
              <div className="break-all font-medium">{h.host}</div>
              {h.error ? (
                <div className="text-[11px] text-red-700">{h.error}</div>
              ) : (
                <div className="text-[11px] text-[#6B7280]">
                  업무 {h.tasks ?? 0} · 검증 {h.verified ?? 0}
                  {h.stale ? ` · 재확인 ${h.stale}` : ""}
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TaskTable({ tasks, taskId, onPick }: { tasks: MapTask[]; taskId: string | null; onPick: (id: string) => void }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-[#E5E7EB] bg-white" data-testid="sitemap-task-table">
      <table className="w-full text-left text-[12px]">
        <thead className="bg-[#F9FAFB] text-[#6B7280]">
          <tr>
            <th className="px-2 py-1">업무</th>
            <th className="px-2 py-1">분류</th>
            <th className="px-2 py-1">위험</th>
            <th className="px-2 py-1">상태</th>
            <th className="px-2 py-1">입력칸</th>
            <th className="px-2 py-1">관찰일</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.id} onClick={() => onPick(t.id)} className={`cursor-pointer border-t border-[#F3F4F6] ${taskId === t.id ? "bg-[#FFF7ED]" : "hover:bg-[#F9FAFB]"}`}>
              <td className="px-2 py-1">
                <div className="font-medium">{t.name || t.id}</div>
                <div className="break-all text-[11px] text-[#9CA3AF]">{t.id}</div>
              </td>
              <td className="px-2 py-1">{CATEGORY_LABEL[t.category]}</td>
              <td className="px-2 py-1"><Chip cls={RISK_STYLE[t.risk]}>{RISK_LABEL[t.risk]}</Chip></td>
              <td className="px-2 py-1"><Chip cls={STATE_STYLE[t.state]}>{STATE_LABEL[t.state]}</Chip></td>
              <td className="px-2 py-1">{t.fields.length}</td>
              <td className="px-2 py-1">{day(t.observed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {tasks.length === 0 && <div className="p-3 text-[#6B7280]">이 사이트에는 아직 업무가 없습니다.</div>}
    </div>
  );
}

function stepText(s: MapTask["steps"][number]): string {
  const target = s.url ?? s.selectors?.[0]?.[0] ?? "";
  return `${s.type}${target ? ` — ${target}` : ""}${s.value ? ` = ${s.value}` : ""}`;
}

function TaskDetail({
  task,
  busy,
  onSave,
  onOutcome,
}: {
  task: MapTask;
  busy: boolean;
  onSave: (input: { name: string; purpose: string; category: Category }) => void;
  onOutcome: (ok: boolean) => void;
}) {
  const [name, setName] = useState(task.name);
  const [purpose, setPurpose] = useState(task.purpose);
  const [category, setCategory] = useState<Category>(task.category);
  const dirty = name !== task.name || purpose !== task.purpose || category !== task.category;

  return (
    <div className="space-y-3 rounded-xl border border-[#E5E7EB] bg-white p-3" data-testid="sitemap-task-detail">
      <div className="flex flex-wrap items-center gap-2">
        <Chip cls={RISK_STYLE[task.risk]}>{RISK_LABEL[task.risk]}</Chip>
        <Chip cls={STATE_STYLE[task.state]}>{STATE_LABEL[task.state]}</Chip>
        <span className="text-[#6B7280]">{AUTH_LABEL[task.auth]} · 검증 {day(task.verified_at)} · 실패 {task.failures}회</span>
      </div>
      {task.risk !== "read" && (
        <div className="rounded-lg bg-red-50 p-2 text-[12px] text-red-800">
          {RISK_LABEL[task.risk]} 업무입니다. 에이전트는 절차를 참고만 하고 <b>실행은 사람 승인 없이 하지 않습니다.</b> 위험 등급은 여기서 바꿀 수 없습니다.
        </div>
      )}
      <div className="break-all text-[12px] text-[#6B7280]">{task.url}</div>

      <div className="grid gap-2 md:grid-cols-2">
        <label className="text-[12px]">업무 이름<input aria-label="업무 이름" className={field} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></label>
        <label className="text-[12px]">분류
          <select aria-label="분류" className={field} value={category} onChange={(e) => setCategory(e.target.value as Category)}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
          </select>
        </label>
        <label className="text-[12px] md:col-span-2">목적(어떤 업무에 쓰는가)<input aria-label="목적" className={field} value={purpose} maxLength={200} onChange={(e) => setPurpose(e.target.value)} placeholder="예) 하도급 상대 업체의 상태·등록업종 확인" /></label>
      </div>
      <div className="flex flex-wrap gap-2">
        <button className={btnPrimary} disabled={busy || !dirty} onClick={() => onSave({ name, purpose, category })}>이름·목적·분류 저장</button>
        <button className={btn} disabled={busy} onClick={() => onOutcome(true)} title="이 지도대로 실제로 한 번 성공했을 때">지도대로 성공 → 검증됨</button>
        <button className={btn} disabled={busy} onClick={() => onOutcome(false)} title="필드·주소가 지도와 달라 실패했을 때">지도와 달라 실패 → 재확인 필요</button>
      </div>

      <div>
        <div className="mb-1 font-semibold">입력 필드 ({task.fields.length})</div>
        <table className="w-full text-left text-[12px]">
          <thead className="text-[#6B7280]"><tr><th className="py-1">이름</th><th>종류</th><th>라벨</th><th>필수</th></tr></thead>
          <tbody>
            {task.fields.map((f, i) => (
              <tr key={`${f.name}-${f.id}-${i}`} className="border-t border-[#F3F4F6]">
                <td className="py-1">{f.name || f.id}</td><td>{f.role}</td><td>{f.label || "-"}</td><td>{f.required ? "예" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {task.fields.length === 0 && <div className="text-[#6B7280]">입력칸이 아직 수집되지 않았습니다(분류 미정 업무는 그 화면을 한 번 더 읽어야 채워집니다).</div>}
      </div>

      <div>
        <div className="mb-1 font-semibold">절차 ({task.steps.length}단계)</div>
        <ol className="list-decimal space-y-[2px] pl-5 text-[12px]">
          {task.steps.map((s, i) => <li key={i} className="break-all">{stepText(s)}</li>)}
        </ol>
        {task.risk !== "read" && <div className="mt-1 text-[11px] text-[#6B7280]">마지막 제출·저장 클릭은 절차에 포함하지 않습니다(사람이 직접).</div>}
      </div>

      {task.changes.length > 0 && (
        <div>
          <div className="mb-1 font-semibold">구조 변경 이력</div>
          <ul className="space-y-[2px] text-[12px] text-[#6B7280]">
            {task.changes.map((c, i) => <li key={i}>{day(c.at)} · 이전 상태 {STATE_LABEL[c.was as TaskState] ?? c.was} → 구조가 바뀌어 다시 관찰 상태</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
