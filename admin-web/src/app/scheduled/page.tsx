"use client";

/**
 * /scheduled — 예약 작업.
 *
 * 사용자가 작업과 시각(한 번/매일/매주/N분마다)을 정해 예약하고, 서버가 그 시각에 실행한다.
 * 브라우저가 필요한 작업은 실행 시 서버가 CDP 를 자동으로 띄운다. 예약 가능한 작업은 서버가 정한 목록뿐이다.
 * 발행·전송처럼 승인이 필요한 작업은 예약 시각이 되면 "승인 대기"가 되고, 사용자가 30분 안에 승인해야 실행된다.
 * 기준서: docs/specs/2026-10-01_user_scheduled_jobs.md
 */

import { useState, useEffect, useCallback } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { PageShell } from "@/components/ui/PageShell";
import { Btn } from "@/components/ui/Btn";
import { Modal } from "@/components/ui/Modal";
import { AdminTable, AdminThead, AdminTbody, AdminTr, AdminTh, AdminTd } from "@/components/ui/AdminTable";

type Recurrence =
  | { kind: "once"; at: string }
  | { kind: "daily"; time: string }
  | { kind: "weekly"; days: number[]; time: string }
  | { kind: "interval"; minutes: number };

interface Job {
  id: string;
  name: string;
  action: string;
  action_label: string;
  params: Record<string, string>;
  recurrence: Recurrence;
  status: "active" | "paused" | "done";
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: string | null;
  last_message: string | null;
}

interface ActionField {
  name: string;
  label: string;
  type: "select" | "text" | "line";
  options: string[];
  option_labels?: Record<string, string>;
  default: string;
}

interface ActionInfo {
  key: string;
  label: string;
  description: string;
  needs_browser: boolean;
  requires_approval: boolean;
  fields: ActionField[];
}

interface Approval {
  run_id: string;
  job_id: string;
  job_name: string;
  action: string;
  params: Record<string, string>;
  requested_at: string;
  expires_at: string;
}

interface Run {
  id: string;
  scheduled_for: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  message: string;
}

interface Form {
  name: string;
  action: string;
  params: Record<string, string>;
  kind: Recurrence["kind"];
  at: string; // datetime-local (PC 로컬 시간)
  time: string;
  days: number[];
  minutes: number;
}

const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

const EMPTY_FORM: Form = {
  name: "",
  action: "",
  params: {},
  kind: "daily",
  at: "",
  time: "09:00",
  days: [0],
  minutes: 60,
};

const PILL_CLASS: Record<string, string> = {
  active: "bg-green-100 text-green-800 border-green-200",
  paused: "bg-gray-100 text-gray-600 border-gray-200",
  done: "bg-blue-100 text-blue-800 border-blue-200",
  ok: "bg-green-100 text-green-800 border-green-200",
  failed: "bg-red-100 text-red-700 border-red-200",
  missed: "bg-yellow-100 text-yellow-800 border-yellow-200",
  skipped: "bg-yellow-100 text-yellow-800 border-yellow-200",
  running: "bg-orange-100 text-orange-800 border-orange-200",
  awaiting_approval: "bg-purple-100 text-purple-800 border-purple-200",
  rejected: "bg-red-100 text-red-700 border-red-200",
  expired: "bg-yellow-100 text-yellow-800 border-yellow-200",
  cancelled: "bg-gray-100 text-gray-600 border-gray-200",
};

const PILL_LABEL: Record<string, string> = {
  active: "활성",
  paused: "일시중지",
  done: "완료",
  ok: "성공",
  failed: "실패",
  missed: "놓침",
  skipped: "건너뜀",
  running: "실행중",
  awaiting_approval: "승인대기",
  rejected: "거부",
  expired: "만료",
  cancelled: "취소",
};

function Pill({ status }: { status: string }) {
  const cls = PILL_CLASS[status] ?? "bg-gray-100 text-gray-600 border-gray-200";
  return (
    <span className={`inline-block text-[11px] px-2 py-[2px] rounded-full border ${cls}`}>
      {PILL_LABEL[status] ?? status}
    </span>
  );
}

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail);
    return `${e.status} ${detail}`;
  }
  return e instanceof Error ? e.message : String(e);
}

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("ko-KR", { hour12: false });
}

function describeRecurrence(r: Recurrence): string {
  if (r.kind === "once") return `한 번 · ${formatTime(r.at)}`;
  if (r.kind === "daily") return `매일 ${r.time}`;
  if (r.kind === "weekly") return `매주 ${r.days.map((d) => DAY_LABELS[d]).join("·")} ${r.time}`;
  return `${r.minutes}분마다`;
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formFromJob(job: Job): Form {
  const r = job.recurrence;
  return {
    ...EMPTY_FORM,
    name: job.name,
    action: job.action,
    params: job.params,
    kind: r.kind,
    at: r.kind === "once" ? toLocalInput(r.at) : "",
    time: r.kind === "daily" || r.kind === "weekly" ? r.time : EMPTY_FORM.time,
    days: r.kind === "weekly" ? r.days : EMPTY_FORM.days,
    minutes: r.kind === "interval" ? r.minutes : EMPTY_FORM.minutes,
  };
}

function recurrenceFromForm(f: Form): Record<string, unknown> {
  if (f.kind === "once") return { kind: "once", at: f.at };
  if (f.kind === "daily") return { kind: "daily", time: f.time };
  if (f.kind === "weekly") return { kind: "weekly", days: f.days, time: f.time };
  return { kind: "interval", minutes: f.minutes };
}

export default function ScheduledJobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [actions, setActions] = useState<ActionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Job | null>(null);
  const [runsFor, setRunsFor] = useState<Job | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);

  const load = useCallback(async () => {
    try {
      const [j, a, ap] = await Promise.all([
        apiFetch<{ jobs: Job[] }>("/scheduled-jobs"),
        apiFetch<{ actions: ActionInfo[] }>("/scheduled-jobs/actions"),
        apiFetch<{ approvals: Approval[] }>("/scheduled-jobs/approvals"),
      ]);
      setJobs(j.jobs);
      setActions(a.actions);
      setApprovals(ap.approvals);
    } catch (e) {
      setMessage({ text: `예약 목록을 불러오지 못했습니다: ${errorText(e)}`, ok: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 30000); // 실행 결과·다음 시각을 주기적으로 갱신
    return () => clearInterval(timer);
  }, [load]);

  const currentAction = actions.find((a) => a.key === form.action);

  const defaultParams = (key: string): Record<string, string> => {
    const info = actions.find((a) => a.key === key);
    return Object.fromEntries((info?.fields ?? []).map((f) => [f.name, f.default]));
  };

  const openCreate = () => {
    const first = actions[0]?.key ?? "";
    setEditingId(null);
    setForm({ ...EMPTY_FORM, action: first, params: defaultParams(first) });
    setFormError(null);
    setFormOpen(true);
  };

  const openEdit = (job: Job) => {
    setEditingId(job.id);
    setForm(formFromJob(job));
    setFormError(null);
    setFormOpen(true);
  };

  const save = async () => {
    setSaving(true);
    setFormError(null);
    try {
      const body = { name: form.name, params: form.params, recurrence: recurrenceFromForm(form) };
      if (editingId) {
        await apiFetch(`/scheduled-jobs/${editingId}/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        await apiFetch("/scheduled-jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, action: form.action }),
        });
      }
      setFormOpen(false);
      setMessage({ text: editingId ? "예약을 수정했습니다." : "예약을 만들었습니다.", ok: true });
      await load();
    } catch (e) {
      setFormError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const act = async (job: Job, path: string, okText: string, method: "POST" | "DELETE" = "POST") => {
    setBusyId(job.id);
    try {
      await apiFetch(`/scheduled-jobs/${job.id}${path}`, { method });
      setMessage({ text: okText, ok: true });
      await load();
    } catch (e) {
      setMessage({ text: errorText(e), ok: false });
    } finally {
      setBusyId(null);
    }
  };

  const runNow = async (job: Job) => {
    setBusyId(job.id);
    setMessage({ text: `"${job.name}" 실행 중입니다. 브라우저 작업은 수 분 걸릴 수 있습니다.`, ok: true });
    try {
      const run = await apiFetch<Run>(`/scheduled-jobs/${job.id}/run-now`, { method: "POST" });
      setMessage({ text: `실행 결과: ${PILL_LABEL[run.status] ?? run.status} — ${run.message}`, ok: run.status === "ok" });
      await load();
    } catch (e) {
      setMessage({ text: errorText(e), ok: false });
    } finally {
      setBusyId(null);
    }
  };

  const showRuns = async (job: Job) => {
    setRunsFor(job);
    setRuns([]);
    try {
      const res = await apiFetch<{ runs: Run[] }>(`/scheduled-jobs/${job.id}/runs`);
      setRuns(res.runs);
    } catch (e) {
      setMessage({ text: errorText(e), ok: false });
    }
  };

  const decide = async (item: Approval, verb: "approve" | "reject") => {
    setBusyId(item.run_id);
    if (verb === "approve") setMessage({ text: `"${item.job_name}" 승인했습니다. 실행 중입니다...`, ok: true });
    try {
      const run = await apiFetch<Run>(`/scheduled-jobs/runs/${item.run_id}/${verb}`, { method: "POST" });
      setMessage({
        text: verb === "approve" ? `실행 결과: ${PILL_LABEL[run.status] ?? run.status} — ${run.message}` : "거부했습니다. 실행하지 않습니다.",
        ok: verb === "reject" || run.status === "ok",
      });
      await load();
    } catch (e) {
      setMessage({ text: errorText(e), ok: false });
      await load();
    } finally {
      setBusyId(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    const job = deleting;
    setDeleting(null);
    await act(job, "", "예약을 삭제했습니다.", "DELETE");
  };

  const toggleDay = (d: number) =>
    setForm((f) => ({ ...f, days: f.days.includes(d) ? f.days.filter((x) => x !== d) : [...f.days, d].sort() }));

  const inputCls = "border border-[#E5E7EB] rounded-lg px-3 py-1.5 text-sm w-full";

  return (
    <PageShell
      title="예약 작업"
      description="작업과 시각을 정해 두면 서버가 그 시각에 실행합니다. 브라우저가 필요한 작업은 자동으로 브라우저를 띄웁니다."
      headerRight={
        <Btn variant="primary" onClick={openCreate} disabled={actions.length === 0}>
          + 예약 만들기
        </Btn>
      }
    >
      <div className="space-y-4">
        {message && (
          <div
            role="status"
            className={`text-sm rounded-lg border px-4 py-2 ${
              message.ok ? "bg-green-50 text-green-700 border-green-200" : "bg-red-50 text-red-700 border-red-200"
            }`}
          >
            {message.text}
          </div>
        )}

        {approvals.length > 0 && (
          <div className="bg-[#F5F3FF] border border-[#DDD6FE] rounded-xl p-5 space-y-3">
            <p className="text-sm font-medium text-[#5B21B6]">승인 대기 {approvals.length}건 — 승인해야 실행됩니다</p>
            {approvals.map((item) => {
              const label = actions.find((a) => a.key === item.action)?.label ?? item.action;
              return (
                <div key={item.run_id} className="bg-white border border-[#DDD6FE] rounded-lg p-3 space-y-2">
                  <div className="text-sm">
                    <span className="font-medium">{item.job_name}</span>
                    <span className="text-xs text-[#6B7280]"> · {label}</span>
                  </div>
                  {Object.keys(item.params).length > 0 && (
                    <pre className="text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded p-2 whitespace-pre-wrap max-h-[240px] overflow-y-auto">
                      {Object.entries(item.params)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join("\n")}
                    </pre>
                  )}
                  <div className="flex items-center gap-2">
                    <Btn size="sm" variant="primary" disabled={busyId === item.run_id} onClick={() => void decide(item, "approve")}>
                      승인하고 실행
                    </Btn>
                    <Btn size="sm" disabled={busyId === item.run_id} onClick={() => void decide(item, "reject")}>
                      거부
                    </Btn>
                    <span className="text-xs text-[#6B7280]">{formatTime(item.expires_at)} 까지</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="bg-white border border-[#E5E7EB] rounded-xl p-5">
          <AdminTable>
            <AdminThead>
              <AdminTr>
                <AdminTh>이름</AdminTh>
                <AdminTh>작업</AdminTh>
                <AdminTh>반복</AdminTh>
                <AdminTh>다음 실행</AdminTh>
                <AdminTh>마지막 결과</AdminTh>
                <AdminTh>상태</AdminTh>
                <AdminTh>관리</AdminTh>
              </AdminTr>
            </AdminThead>
            <AdminTbody>
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center text-sm text-[#6B7280] py-8">
                    {loading ? "불러오는 중..." : "예약이 없습니다. 오른쪽 위 \"예약 만들기\"로 시작하세요."}
                  </td>
                </tr>
              )}
              {jobs.map((job) => (
                <AdminTr key={job.id}>
                  <AdminTd>{job.name}</AdminTd>
                  <AdminTd>
                    {job.action_label}
                    {job.params.target ? <span className="text-xs text-[#6B7280]"> ({job.params.target})</span> : null}
                    {job.params.title ? <div className="text-xs text-[#6B7280] max-w-[200px] truncate">{job.params.title}</div> : null}
                    {actions.find((a) => a.key === job.action)?.requires_approval && (
                      <span className="ml-1 text-[10px] text-[#5B21B6] border border-[#DDD6FE] rounded px-1">승인 필요</span>
                    )}
                  </AdminTd>
                  <AdminTd>{describeRecurrence(job.recurrence)}</AdminTd>
                  <AdminTd>{formatTime(job.next_run_at)}</AdminTd>
                  <AdminTd>
                    {job.last_status ? (
                      <div className="space-y-1">
                        <Pill status={job.last_status} />
                        <div className="text-xs text-[#6B7280]">{formatTime(job.last_run_at)}</div>
                        {job.last_message && <div className="text-xs text-[#6B7280] max-w-[220px]">{job.last_message}</div>}
                      </div>
                    ) : (
                      "-"
                    )}
                  </AdminTd>
                  <AdminTd>
                    <Pill status={job.status} />
                  </AdminTd>
                  <AdminTd>
                    <div className="flex flex-wrap gap-1">
                      <Btn size="xs" disabled={busyId === job.id} onClick={() => void runNow(job)}>
                        지금 실행
                      </Btn>
                      {job.status === "active" && (
                        <Btn size="xs" disabled={busyId === job.id} onClick={() => void act(job, "/pause", "일시중지했습니다.")}>
                          일시중지
                        </Btn>
                      )}
                      {job.status === "paused" && (
                        <Btn size="xs" disabled={busyId === job.id} onClick={() => void act(job, "/resume", "다시 시작했습니다.")}>
                          재개
                        </Btn>
                      )}
                      <Btn size="xs" onClick={() => void showRuns(job)}>
                        기록
                      </Btn>
                      <Btn size="xs" onClick={() => openEdit(job)}>
                        수정
                      </Btn>
                      <Btn size="xs" variant="danger" disabled={busyId === job.id} onClick={() => setDeleting(job)}>
                        삭제
                      </Btn>
                    </div>
                  </AdminTd>
                </AdminTr>
              ))}
            </AdminTbody>
          </AdminTable>
        </div>

        <div className="bg-[#FFFBEB] border border-[#FDE68A] rounded-xl p-4 text-xs text-[#92400E] space-y-1">
          <p>서버(앱)가 켜져 있을 때만 실행됩니다. 꺼져 있는 동안 지나간 예약은 10분이 넘으면 &quot;놓침&quot;으로 기록하고 건너뜁니다.</p>
          <p>발행·전송처럼 승인이 필요한 작업은 예약 시각마다 위 &quot;승인 대기&quot;에서 승인해야 실행됩니다(30분 안에 승인하지 않으면 건너뜁니다).</p>
        </div>
      </div>

      <Modal
        open={formOpen}
        title={editingId ? "예약 수정" : "예약 만들기"}
        onClose={() => setFormOpen(false)}
        footer={
          <>
            <Btn onClick={() => setFormOpen(false)}>취소</Btn>
            <Btn variant="primary" disabled={saving} onClick={() => void save()}>
              {saving ? "저장 중..." : "저장"}
            </Btn>
          </>
        }
      >
        <div className="space-y-3">
          {formError && (
            <div role="alert" className="text-sm rounded-lg border px-3 py-2 bg-red-50 text-red-700 border-red-200">
              {formError}
            </div>
          )}
          <label className="block text-sm">
            <span className="text-[#374151] font-medium">이름</span>
            <input className={inputCls} value={form.name} maxLength={80} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="block text-sm">
            <span className="text-[#374151] font-medium">작업</span>
            <select
              className={inputCls}
              value={form.action}
              disabled={editingId !== null}
              onChange={(e) => setForm({ ...form, action: e.target.value, params: defaultParams(e.target.value) })}
            >
              {actions.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.label}
                </option>
              ))}
            </select>
            {currentAction && (
              <span className="text-xs text-[#6B7280]">
                {currentAction.description}
                {currentAction.needs_browser ? " (브라우저 사용)" : ""}
                {currentAction.requires_approval ? " (실행 시각마다 승인 필요)" : ""}
              </span>
            )}
          </label>
          {(currentAction?.fields ?? []).map((f) =>
            f.type === "text" ? (
              <label key={f.name} className="block text-sm">
                <span className="text-[#374151] font-medium">{f.label}</span>
                <textarea
                  className={inputCls}
                  rows={f.name === "body" ? 10 : 4}
                  maxLength={f.name === "body" ? 20000 : 1000}
                  value={form.params[f.name] ?? f.default}
                  onChange={(e) => setForm({ ...form, params: { ...form.params, [f.name]: e.target.value } })}
                />
              </label>
            ) : f.type === "line" ? (
              <label key={f.name} className="block text-sm">
                <span className="text-[#374151] font-medium">{f.label}</span>
                <input
                  className={inputCls}
                  value={form.params[f.name] ?? f.default}
                  onChange={(e) => setForm({ ...form, params: { ...form.params, [f.name]: e.target.value } })}
                />
              </label>
            ) : (
            <label key={f.name} className="block text-sm">
              <span className="text-[#374151] font-medium">{f.label}</span>
              <select
                className={inputCls}
                value={form.params[f.name] ?? f.default}
                onChange={(e) => setForm({ ...form, params: { ...form.params, [f.name]: e.target.value } })}
              >
                {f.options.map((o) => (
                  <option key={o} value={o}>
                    {f.option_labels?.[o] ?? o}
                  </option>
                ))}
              </select>
            </label>
            ),
          )}
          <label className="block text-sm">
            <span className="text-[#374151] font-medium">반복</span>
            <select className={inputCls} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as Form["kind"] })}>
              <option value="once">한 번</option>
              <option value="daily">매일</option>
              <option value="weekly">매주</option>
              <option value="interval">N분마다</option>
            </select>
          </label>
          {form.kind === "once" && (
            <label className="block text-sm">
              <span className="text-[#374151] font-medium">실행 일시 (이 PC 시간)</span>
              <input type="datetime-local" className={inputCls} value={form.at} onChange={(e) => setForm({ ...form, at: e.target.value })} />
            </label>
          )}
          {(form.kind === "daily" || form.kind === "weekly") && (
            <label className="block text-sm">
              <span className="text-[#374151] font-medium">시각 (이 PC 시간)</span>
              <input type="time" className={inputCls} value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
            </label>
          )}
          {form.kind === "weekly" && (
            <div className="text-sm">
              <span className="text-[#374151] font-medium">요일</span>
              <div className="flex gap-2 mt-1">
                {DAY_LABELS.map((label, d) => (
                  <label key={label} className="flex items-center gap-1">
                    <input type="checkbox" checked={form.days.includes(d)} onChange={() => toggleDay(d)} />
                    {label}
                  </label>
                ))}
              </div>
            </div>
          )}
          {form.kind === "interval" && (
            <label className="block text-sm">
              <span className="text-[#374151] font-medium">간격 (분, 5분 이상)</span>
              <input
                type="number"
                min={5}
                className={inputCls}
                value={form.minutes}
                onChange={(e) => setForm({ ...form, minutes: Number(e.target.value) })}
              />
            </label>
          )}
        </div>
      </Modal>

      <Modal
        open={deleting !== null}
        title="예약 삭제"
        onClose={() => setDeleting(null)}
        footer={
          <>
            <Btn onClick={() => setDeleting(null)}>취소</Btn>
            <Btn variant="danger" onClick={() => void confirmDelete()}>
              삭제
            </Btn>
          </>
        }
      >
        <p className="text-sm text-[#374151]">&quot;{deleting?.name}&quot; 예약과 실행 기록을 삭제합니다. 되돌릴 수 없습니다.</p>
      </Modal>

      <Modal open={runsFor !== null} title={`실행 기록 — ${runsFor?.name ?? ""}`} onClose={() => setRunsFor(null)}>
        {runs.length === 0 ? (
          <p className="text-sm text-[#6B7280]">기록이 없습니다.</p>
        ) : (
          <ul className="space-y-2 max-h-[320px] overflow-y-auto">
            {runs.map((r) => (
              <li key={r.id} className="text-sm border border-[#E5E7EB] rounded-lg px-3 py-2">
                <div className="flex items-center gap-2">
                  <Pill status={r.status} />
                  <span className="text-xs text-[#6B7280]">{formatTime(r.started_at)}</span>
                </div>
                {r.message && <div className="text-xs text-[#374151] mt-1">{r.message}</div>}
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </PageShell>
  );
}
