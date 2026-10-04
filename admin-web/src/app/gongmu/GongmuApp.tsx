"use client";

import { useCallback, useEffect, useState } from "react";
import {
  STATUS_LABEL,
  STATUS_ORDER,
  gongmuApi,
  type Contract,
  type Grade,
  type ImportResult,
  type Settings,
  type Site,
  type Summary,
  type Task,
  type TaskDetail,
  type TaskStatus,
} from "./api";

/**
 * 공무 업무판 화면 — 왼쪽: 현장 목록·등록·가져오기, 오른쪽: 이번 주 할 일 · 상태별 업무 보드 · 계약 · 업무 상세(서류).
 * 이 화면은 외부 사이트에 접속하거나 제출하지 않는다. 완료 표시는 사람이 직접 한다.
 */

const GRADE_STYLE: Record<Grade, { label: string; cls: string }> = {
  overdue: { label: "지연", cls: "bg-red-100 text-red-800" },
  soon: { label: "임박", cls: "bg-amber-100 text-amber-800" },
  later: { label: "여유", cls: "bg-gray-100 text-gray-700" },
  unknown: { label: "기한 확인 필요", cls: "bg-violet-100 text-violet-800" },
  closed: { label: "종료", cls: "bg-green-100 text-green-800" },
};

const won = (n: number | null) => (n == null ? "-" : `${n.toLocaleString("ko-KR")}원`);
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const field = "w-full rounded-lg border border-[#E5E7EB] px-2 py-1 text-[12px]";
const btn = "rounded-lg border border-[#E5E7EB] bg-white px-3 py-1 text-[12px] hover:bg-[#F9FAFB] disabled:opacity-50";
const btnPrimary = "rounded-lg border border-[#F97316] bg-[#F97316] px-3 py-1 text-[12px] text-white hover:bg-[#EA580C] disabled:opacity-50";

function GradeBadge({ grade, days }: { grade: Grade; days: number | null }) {
  const s = GRADE_STYLE[grade];
  const extra = grade === "overdue" && days != null ? ` ${-days}일` : grade === "soon" && days != null ? ` D-${days}` : "";
  return <span className={`rounded-full px-2 py-[1px] text-[11px] ${s.cls}`}>{s.label}{extra}</span>;
}

export function GongmuApp() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [settings, setSettings] = useState<Settings>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  const refreshAll = useCallback(async () => {
    try {
      const [sum, list, st] = await Promise.all([gongmuApi.summary(), gongmuApi.sites(), gongmuApi.settings()]);
      setSummary(sum);
      setSites(list);
      setSettings(st.settings);
    } catch (e) {
      setError(errText(e));
    }
  }, []);

  const refreshSite = useCallback(async (id: string) => {
    try {
      const [s, t] = await Promise.all([gongmuApi.site(id), gongmuApi.tasks(id)]);
      setContracts(s.contracts);
      setTasks(t);
    } catch (e) {
      setError(errText(e));
    }
  }, []);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  async function act(fn: () => Promise<unknown>, okMessage?: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await fn();
      if (okMessage) setNotice(okMessage);
      await refreshAll();
      if (siteId) await refreshSite(siteId);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  function pickSite(id: string) {
    setSiteId(id);
    setDetail(null);
    void refreshSite(id);
  }

  const site = sites.find((s) => s.id === siteId) ?? null;
  const attention = tasks.filter((t) => t.grade === "overdue" || t.grade === "soon");

  return (
    <div className="space-y-3 p-3 text-[13px]">
      {summary && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">{summary.disclaimer}</div>
      )}
      {summary && (
        <div className="flex flex-wrap gap-2" data-testid="gongmu-summary">
          <span className="rounded-full bg-red-100 px-3 py-1 text-red-800">지연 {summary.counts.overdue}</span>
          <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-800">임박 {summary.counts.soon}</span>
          <span className="rounded-full bg-violet-100 px-3 py-1 text-violet-800">기한 확인 필요 {summary.counts.unknown}</span>
          <span className="rounded-full bg-gray-100 px-3 py-1 text-gray-700">진행 중 {summary.counts.open}</span>
        </div>
      )}
      {error && <div className="rounded-lg bg-red-50 p-2 text-red-700" role="alert">{error}</div>}
      {notice && <div className="rounded-lg bg-green-50 p-2 text-green-800">{notice}</div>}

      <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
        <div className="space-y-3">
          <SiteList sites={sites} siteId={siteId} onPick={pickSite} />
          <NewSiteForm busy={busy} onCreate={(input) => act(async () => { const r = await gongmuApi.createSite(input); pickSite(r.site.id); }, "현장을 등록하고 해당 업무를 만들었습니다")} />
          <ImportBox busy={busy} result={importResult} onImport={(kind, path) => act(async () => setImportResult(kind === "sites" ? await gongmuApi.importSites(path) : await gongmuApi.importContracts(path)))} />
          <SettingsBox settings={settings} busy={busy} onSave={(v) => act(() => gongmuApi.saveSettings(v), "기준을 저장하고 업무를 다시 계산했습니다")} />
        </div>

        <div className="space-y-3">
          {!site && <div className="rounded-xl border border-dashed border-[#D1D5DB] p-6 text-center text-[#6B7280]">왼쪽에서 현장을 고르거나 새로 등록하세요.</div>}
          {site && (
            <>
              <div className="rounded-xl border border-[#E5E7EB] bg-white p-3">
                <div className="text-[15px] font-semibold">{site.name}</div>
                <div className="text-[12px] text-[#6B7280]">
                  {site.role === "prime" ? "원도급" : "하도급"} · 도급금액 {won(site.contract_amount)} · 착공 {site.start_date ?? "미정"} · 준공예정 {site.end_date ?? "미정"} · 발주처 {site.client || "-"}
                </div>
              </div>

              <div className="rounded-xl border border-[#E5E7EB] bg-white p-3" data-testid="gongmu-attention">
                <div className="mb-2 font-semibold">이번 주 해야 할 일</div>
                {attention.length === 0 && <div className="text-[#6B7280]">기한이 임박하거나 지난 업무가 없습니다.</div>}
                {attention.map((t) => (
                  <TaskRow key={t.id} task={t} onOpen={() => void gongmuApi.task(t.id).then(setDetail).catch((e) => setError(errText(e)))} />
                ))}
              </div>

              <Board tasks={tasks} onOpen={(id) => void gongmuApi.task(id).then(setDetail).catch((e) => setError(errText(e)))} />

              {detail && (
                <TaskPanel
                  detail={detail}
                  busy={busy}
                  run={(fn, msg) => act(async () => setDetail(await fn()), msg)}
                />
              )}

              <ContractBox
                contracts={contracts}
                busy={busy}
                onCreate={(input) => act(() => gongmuApi.createContract(site.id, input), "계약을 등록하고 업무를 다시 계산했습니다")}
                onChange={(cid, input) => act(() => gongmuApi.addChange(cid, input), "변경을 기록하고 공사대장 통보 업무를 다시 계산했습니다")}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SiteList({ sites, siteId, onPick }: { sites: Site[]; siteId: string | null; onPick: (id: string) => void }) {
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-3">
      <div className="mb-2 font-semibold">현장 ({sites.length})</div>
      {sites.length === 0 && <div className="text-[#6B7280]">등록된 현장이 없습니다.</div>}
      {sites.map((s) => (
        <button key={s.id} onClick={() => onPick(s.id)} className={`mb-1 block w-full rounded-lg px-2 py-1 text-left ${s.id === siteId ? "bg-orange-50 ring-1 ring-orange-300" : "hover:bg-[#F9FAFB]"}`}>
          <div className="font-medium">{s.name}</div>
          <div className="text-[11px] text-[#6B7280]">{s.role === "prime" ? "원도급" : "하도급"} · {won(s.contract_amount)}</div>
        </button>
      ))}
    </div>
  );
}

function NewSiteForm({ busy, onCreate }: { busy: boolean; onCreate: (input: Record<string, unknown>) => void }) {
  const [f, setF] = useState({ name: "", role: "원도급", contract_amount: "", start_date: "", end_date: "", client: "" });
  const set = (k: string, v: string) => setF((p) => ({ ...p, [k]: v }));
  return (
    <form
      className="space-y-1 rounded-xl border border-[#E5E7EB] bg-white p-3"
      onSubmit={(e) => {
        e.preventDefault();
        onCreate({ ...f, start_date: f.start_date || null, end_date: f.end_date || null });
        setF({ name: "", role: "원도급", contract_amount: "", start_date: "", end_date: "", client: "" });
      }}
    >
      <div className="font-semibold">현장 등록</div>
      <input aria-label="현장명" className={field} placeholder="현장명" value={f.name} onChange={(e) => set("name", e.target.value)} required />
      <input aria-label="발주처" className={field} placeholder="발주처" value={f.client} onChange={(e) => set("client", e.target.value)} />
      <div className="flex gap-1">
        <select aria-label="우리 회사 지위" className={field} value={f.role} onChange={(e) => set("role", e.target.value)}>
          <option>원도급</option>
          <option>하도급</option>
        </select>
        <input aria-label="도급금액" className={field} placeholder="도급금액(원)" value={f.contract_amount} onChange={(e) => set("contract_amount", e.target.value)} />
      </div>
      <div className="flex gap-1">
        <input aria-label="착공일" type="date" className={field} value={f.start_date} onChange={(e) => set("start_date", e.target.value)} />
        <input aria-label="준공예정일" type="date" className={field} value={f.end_date} onChange={(e) => set("end_date", e.target.value)} />
      </div>
      <button type="submit" className={btnPrimary} disabled={busy}>등록하고 업무 만들기</button>
    </form>
  );
}

function ImportBox({ busy, result, onImport }: { busy: boolean; result: ImportResult | null; onImport: (kind: "sites" | "contracts", path: string) => void }) {
  const [path, setPath] = useState("");
  return (
    <div className="space-y-1 rounded-xl border border-[#E5E7EB] bg-white p-3">
      <div className="font-semibold">엑셀·CSV 가져오기</div>
      <div className="text-[11px] text-[#6B7280]">문서·다운로드·바탕화면 폴더 안의 파일 전체 경로. 현장: 현장명·지위(원도급/하도급)·도급금액·착공일 열. 계약: 현장명·구분·계약금액·계약일 열. 한 행이라도 잘못되면 아무것도 넣지 않습니다.</div>
      <input aria-label="가져올 파일 경로" className={field} placeholder="C:\Users\...\현장목록.xlsx" value={path} onChange={(e) => setPath(e.target.value)} />
      <div className="flex gap-1">
        <button className={btn} disabled={busy || !path} onClick={() => onImport("sites", path)}>현장 가져오기</button>
        <button className={btn} disabled={busy || !path} onClick={() => onImport("contracts", path)}>계약 가져오기</button>
      </div>
      {result && (
        <div className="text-[12px]">
          {result.imported}건 가져옴{result.skipped_existing ? ` · 이미 있어 건너뜀 ${result.skipped_existing}` : ""}
          {result.errors.map((er) => <div key={er.line} className="text-red-700">{er.line}행: {er.error}</div>)}
        </div>
      )}
    </div>
  );
}

const SETTING_LABEL: Record<string, string> = {
  prime_notice_min: "공사대장 통보 — 원도급 기준(원)",
  sub_notice_min: "공사대장 통보 — 하도급 기준(원)",
  soon_days: "기한 임박 기준(일)",
};

function SettingsBox({ settings, busy, onSave }: { settings: Settings; busy: boolean; onSave: (v: Settings) => void }) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  return (
    <details className="rounded-xl border border-[#E5E7EB] bg-white p-3">
      <summary className="cursor-pointer font-semibold">기준 설정(법령 확인 후 수정)</summary>
      <div className="mt-2 space-y-1">
        {Object.keys(SETTING_LABEL).map((k) => (
          <label key={k} className="block text-[12px]">
            {SETTING_LABEL[k]}
            <input className={field} value={draft[k] ?? String(settings[k] ?? "")} onChange={(e) => setDraft((p) => ({ ...p, [k]: e.target.value }))} />
          </label>
        ))}
        <button className={btn} disabled={busy} onClick={() => onSave(Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v.replace(/,/g, ""))])))}>저장</button>
      </div>
    </details>
  );
}

function TaskRow({ task, onOpen }: { task: Task; onOpen: () => void }) {
  return (
    <button onClick={onOpen} className="mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left hover:bg-[#F9FAFB]">
      <GradeBadge grade={task.grade} days={task.days_left} />
      <span className="font-mono text-[11px] text-[#6B7280]">{task.catalog_code}</span>
      <span className="flex-1">{task.catalog_name}{task.period ? ` (${task.period})` : ""}</span>
      <span className="text-[11px] text-[#6B7280]">{task.due_date ?? "기한 없음"}</span>
    </button>
  );
}

function Board({ tasks, onOpen }: { tasks: Task[]; onOpen: (id: string) => void }) {
  return (
    <div className="grid gap-2 md:grid-cols-5" data-testid="gongmu-board">
      {STATUS_ORDER.map((status) => {
        const col = tasks.filter((t) => t.status === status);
        return (
          <div key={status} className="rounded-xl border border-[#E5E7EB] bg-white p-2">
            <div className="mb-1 text-[12px] font-semibold">{STATUS_LABEL[status]} ({col.length})</div>
            {col.map((t) => (
              <button key={t.id} onClick={() => onOpen(t.id)} className="mb-1 block w-full rounded-lg border border-[#F3F4F6] p-1 text-left hover:bg-[#F9FAFB]">
                <div className="text-[11px]"><span className="font-mono text-[#6B7280]">{t.catalog_code}</span> {t.catalog_name}</div>
                <div className="mt-[2px] flex items-center gap-1">
                  <GradeBadge grade={t.grade} days={t.days_left} />
                  <span className="text-[10px] text-[#6B7280]">{t.category === "legal" ? "법정" : "실무"}{t.due_date ? ` · ${t.due_date}` : ""}</span>
                </div>
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function TaskPanel({ detail, busy, run }: {
  detail: TaskDetail;
  busy: boolean;
  run: (fn: () => Promise<TaskDetail>, msg?: string) => void;
}) {
  const [due, setDue] = useState(detail.due_date ?? "");
  const [assignee, setAssignee] = useState(detail.assignee);
  const [memo, setMemo] = useState(detail.memo);
  const [paths, setPaths] = useState<Record<string, string>>({});
  useEffect(() => {
    setDue(detail.due_date ?? "");
    setAssignee(detail.assignee);
    setMemo(detail.memo);
  }, [detail.id, detail.due_date, detail.assignee, detail.memo]);

  return (
    <div className="space-y-2 rounded-xl border border-orange-300 bg-white p-3" data-testid="gongmu-task-panel">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[12px] text-[#6B7280]">{detail.catalog_code}</span>
        <span className="text-[14px] font-semibold">{detail.catalog_name}</span>
        <GradeBadge grade={detail.grade} days={detail.days_left} />
      </div>
      {detail.basis && <div className="text-[12px] text-[#6B7280]">근거: {detail.basis}</div>}
      {detail.verify_law && <div className="rounded-lg bg-violet-50 p-2 text-[12px] text-violet-800">법령·기준 확인 필요 항목입니다. 국가법령정보센터 원문으로 시점·기준을 확인한 뒤 기한을 입력하세요.</div>}
      {detail.submit_to && <div className="text-[12px]">제출처: {detail.submit_to} <span className="text-[#6B7280]">(이 화면은 제출하지 않습니다 — 직접 제출 후 완료 처리)</span></div>}

      <div className="flex flex-wrap gap-1">
        {STATUS_ORDER.map((s: TaskStatus) => (
          <button key={s} disabled={busy || detail.status === s} onClick={() => run(() => gongmuApi.setStatus(detail.id, s))} className={detail.status === s ? btnPrimary : btn}>{STATUS_LABEL[s]}</button>
        ))}
      </div>

      <div className="grid gap-1 md:grid-cols-3">
        <label className="text-[12px]">기한<input type="date" aria-label="기한" className={field} value={due} onChange={(e) => setDue(e.target.value)} /></label>
        <label className="text-[12px]">담당자<input aria-label="담당자" className={field} value={assignee} onChange={(e) => setAssignee(e.target.value)} /></label>
        <label className="text-[12px] md:col-span-3">메모<textarea aria-label="메모" className={field} rows={2} value={memo} onChange={(e) => setMemo(e.target.value)} /></label>
      </div>
      <button className={btn} disabled={busy} onClick={() => run(() => gongmuApi.patchTask(detail.id, { due_date: due || null, assignee, memo }), "저장했습니다")}>기한·담당·메모 저장</button>

      <div className="font-semibold">필요 서류 ({detail.docs_checklist.filter((d) => d.ready).length}/{detail.docs_checklist.length} 준비)</div>
      {detail.docs_checklist.map((d) => (
        <div key={d.doc_name} className="flex flex-wrap items-center gap-1 text-[12px]">
          <input type="checkbox" aria-label={`${d.doc_name} 준비됨`} checked={d.ready} disabled={busy} onChange={(e) => run(() => gongmuApi.setDoc(detail.id, d.doc_name, e.target.checked, ""))} />
          <span className="w-40">{d.doc_name}</span>
          <input aria-label={`${d.doc_name} 파일 경로`} className={`${field} flex-1`} placeholder={d.file_path || "파일 경로(문서·다운로드·바탕화면 폴더 안)"} value={paths[d.doc_name] ?? ""} onChange={(e) => setPaths((p) => ({ ...p, [d.doc_name]: e.target.value }))} />
          <button className={btn} disabled={busy || !paths[d.doc_name]} onClick={() => run(() => gongmuApi.setDoc(detail.id, d.doc_name, true, paths[d.doc_name]), "서류 경로를 연결했습니다")}>연결</button>
        </div>
      ))}
    </div>
  );
}

function ContractBox({ contracts, busy, onCreate, onChange }: {
  contracts: Contract[];
  busy: boolean;
  onCreate: (input: Record<string, unknown>) => void;
  onChange: (contractId: string, input: Record<string, unknown>) => void;
}) {
  const [f, setF] = useState({ kind: "하도급", counterparty: "", amount: "", contract_date: "" });
  const [chg, setChg] = useState({ id: "", date: "", amount: "", memo: "" });
  return (
    <div className="space-y-2 rounded-xl border border-[#E5E7EB] bg-white p-3">
      <div className="font-semibold">계약 ({contracts.length})</div>
      {contracts.map((c) => (
        <div key={c.id} className="rounded-lg border border-[#F3F4F6] p-2 text-[12px]">
          {c.kind === "prime" ? "도급" : "하도급"} · {c.counterparty || "-"} · {won(c.amount)} · 계약일 {c.contract_date ?? "-"}
          {c.changes.map((x, i) => <div key={i} className="text-[#6B7280]">변경 {x.date} {x.amount != null ? won(x.amount) : ""} {x.memo}</div>)}
          <button className={`${btn} mt-1`} onClick={() => setChg({ id: c.id, date: "", amount: "", memo: "" })}>변경 기록하기</button>
        </div>
      ))}
      {chg.id && (
        <form className="flex flex-wrap items-end gap-1 rounded-lg bg-amber-50 p-2" onSubmit={(e) => { e.preventDefault(); onChange(chg.id, { date: chg.date, amount: chg.amount || null, memo: chg.memo }); setChg({ id: "", date: "", amount: "", memo: "" }); }}>
          <label className="text-[12px]">변경일<input aria-label="변경일" type="date" className={field} value={chg.date} onChange={(e) => setChg({ ...chg, date: e.target.value })} required /></label>
          <label className="text-[12px]">변경 후 금액<input aria-label="변경 후 금액" className={field} value={chg.amount} onChange={(e) => setChg({ ...chg, amount: e.target.value })} /></label>
          <label className="text-[12px]">사유<input aria-label="변경 사유" className={field} value={chg.memo} onChange={(e) => setChg({ ...chg, memo: e.target.value })} /></label>
          <button type="submit" className={btnPrimary} disabled={busy}>변경 기록</button>
        </form>
      )}
      <form className="flex flex-wrap items-end gap-1" onSubmit={(e) => { e.preventDefault(); onCreate({ ...f, contract_date: f.contract_date || null }); setF({ kind: "하도급", counterparty: "", amount: "", contract_date: "" }); }}>
        <label className="text-[12px]">구분<select aria-label="계약 구분" className={field} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option>하도급</option><option>도급</option></select></label>
        <label className="text-[12px]">상대 업체<input aria-label="상대 업체" className={field} value={f.counterparty} onChange={(e) => setF({ ...f, counterparty: e.target.value })} /></label>
        <label className="text-[12px]">계약금액<input aria-label="계약금액" className={field} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></label>
        <label className="text-[12px]">계약일<input aria-label="계약일" type="date" className={field} value={f.contract_date} onChange={(e) => setF({ ...f, contract_date: e.target.value })} /></label>
        <button type="submit" className={btnPrimary} disabled={busy}>계약 등록</button>
      </form>
    </div>
  );
}
