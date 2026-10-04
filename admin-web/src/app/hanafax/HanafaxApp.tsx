"use client";

import { useCallback, useEffect, useState } from "react";
import { FaxSitePreview } from "@/components/chat/FaxSitePreview";
import { UniversalChat } from "@/components/chat/UniversalChat";
import { AttachmentField } from "./AttachmentField";
import { faxApi, parseRecipients, type AddressGroup, type Authorization, type GroupSyncStatus, type LogRow, type ReconcileStatus, type RunStatus } from "@/lib/hanafaxApi";

/**
 * 하나팩스 화면 — 왼쪽: 승인서 목록·상세(미리보기·승인·발송·이력), 오른쪽: AI 창.
 *
 * 안전 설계
 * - 발송은 "승인" 뒤에만 가능하다(서버가 승인 전 발송을 거부). AI 창은 승인 대기 초안만 만들 수 있다.
 * - 미리보기(수신자·제목·문서·한도 목차)는 접이식이다. 열어볼지는 사용자가 정하고, 열지 않아도 승인할 수 있다.
 * - 기본은 드라이런(전송 없음). 실전송은 '실제로 전송' 을 체크해야 한다.
 */

const POLL_MS = 4000;

// 이력 상태 한글 표시 — sent 는 '접수'일 뿐이고 최종 성공/실패는 전송결과 대조(delivered/delivery_failed)로 확정된다.
const STATUS_LABEL: Record<string, string> = {
  sent: "접수됨(최종 결과 대기)",
  delivered: "전달 확인(성공)",
  delivery_failed: "전달 실패",
  unknown: "확인 필요",
  failed: "실패(재시도 가능)",
  dry_run: "드라이런",
  claimed: "전송 요청 중",
};

// AI 창 지침 — 에이전트가 앱 허용 API(call_api)로 승인 대기 초안만 만들고, 승인은 사람이 카드 버튼으로 하게 한다.
const AGENT_HINT =
  "[하나팩스 지침] 팩스 발송 요청이면 mcp__haehan-orchestrator__call_api 로 endpoint 'hanafax.draft' 를 호출해 승인 대기 초안만 만든다 " +
  "(body: name, subject, document_ref=첨부 파일 전체 경로, recipients=[{fax,name}] 또는 recipients_file=주소록 엑셀/CSV 경로 또는 site_group=하나팩스 주소록 그룹 번호). " +
  "사용자가 하나팩스 주소록 그룹 이름을 말하면: ① call_api 'hanafax.address_groups' 로 그룹 목록(intid·이름·인원) 확인 → ② 'hanafax.address_group_sync' (path_params={intid})로 가져오기 시작 → " +
  "③ 'hanafax.address_group_sync_status' 를 몇 초마다 조회해 state.ok 가 true(cached=true) 가 될 때까지 기다림(큰 그룹은 몇 분) → ④ 'hanafax.draft' 에 site_group=<intid> (1000명이 넘는 그룹은 group_offset/group_limit 로 1000명씩 구간) 로 초안 생성. " +
  "사용자가 알려 준 첨부 파일 경로(화면에서 올린 파일은 앱 폴더의 전체 경로)를 document_ref 에 그대로 쓴다. " +
  "Python·Bash 로 직접 만들거나 발송하지 않는다(권한 없음). 응답의 id 로 답변 끝에 [[fax-approve:<id>]] 를 그대로 적고 " +
  "'아래 승인 버튼을 눌러 주세요'라고 안내한다. 승인·발송은 사용자가 버튼으로만 한다. 주소록을 쓰면 응답의 import_summary 건수를 알린다.";

function statusLabel(a: Authorization): { text: string; cls: string } {
  if (a.revoked) return { text: "취소됨", cls: "bg-gray-200 text-gray-700" };
  if (!a.approved) return { text: "승인 대기", cls: "bg-amber-100 text-amber-800" };
  return a.live
    ? { text: "승인됨 · 실전송", cls: "bg-green-100 text-green-800" }
    : { text: "승인됨 · 드라이런", cls: "bg-blue-100 text-blue-800" };
}

export function HanafaxApp() {
  const [items, setItems] = useState<Authorization[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Authorization | null>(null);
  const [log, setLog] = useState<LogRow[]>([]);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [recon, setRecon] = useState<ReconcileStatus | null>(null);
  const [aiAttach, setAiAttach] = useState("");
  const [killed, setKilled] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [live, setLive] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshList = useCallback(async () => {
    try {
      const [list, ks] = await Promise.all([faxApi.list(), faxApi.killSwitch()]);
      setItems(list);
      setKilled(ks.kill_switch);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const refreshDetail = useCallback(async (id: string) => {
    try {
      const [d, l, r, c] = await Promise.all([faxApi.get(id), faxApi.log(id), faxApi.runStatus(id), faxApi.reconcileStatus(id)]);
      setDetail(d);
      setLog(l);
      setRun(r);
      setRecon(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // AI 창에서 올린 승인 대기 건이 보이도록 주기적으로 새로 고친다
  useEffect(() => {
    void refreshList();
    const t = setInterval(() => {
      void refreshList();
      if (selectedId) void refreshDetail(selectedId);
    }, POLL_MS);
    return () => clearInterval(t);
  }, [refreshList, refreshDetail, selectedId]);

  function select(id: string) {
    setSelectedId(id);
    setShowPreview(false);
    setLive(false);
    setError(null);
    void refreshDetail(id);
  }

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      await refreshList();
      if (selectedId) await refreshDetail(selectedId);
    }
  }

  const st = detail ? statusLabel(detail) : null;
  const canApprove = detail && !detail.approved && !detail.revoked;
  const canSend = detail && detail.approved && !detail.revoked && !run?.running && !killed;

  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="hanafax-app">
      <section className="space-y-3">
        <div className="flex items-center justify-between rounded border border-[#E5E7EB] bg-white p-3">
          <div className="text-sm">
            자동 발송 전체 정지:{" "}
            <b className={killed ? "text-red-600" : "text-green-700"}>{killed ? "정지 중" : "정상"}</b>
          </div>
          <button
            className="rounded border px-3 py-1 text-sm"
            disabled={busy}
            onClick={() => act(() => faxApi.setKillSwitch(!killed))}
          >
            {killed ? "정지 해제" : "모든 발송 정지"}
          </button>
        </div>


        {error && <div className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700">{error}</div>}

        <div className="rounded border border-[#E5E7EB] bg-white">
          <div className="flex items-center justify-between border-b p-3">
            <b className="text-sm">발송 요청</b>
            <button className="rounded bg-[#2563EB] px-3 py-1 text-sm text-white" onClick={() => setShowNew((v) => !v)}>
              {showNew ? "닫기" : "새 발송 요청"}
            </button>
          </div>
          {showNew && (
            <NewForm
              onCreated={(id) => {
                setShowNew(false);
                void refreshList();
                select(id);
              }}
            />
          )}
          <ul className="max-h-60 divide-y overflow-auto">
            {items.length === 0 && <li className="p-3 text-sm text-gray-500">요청이 없습니다. AI 창에 “이 파일을 ○○에게 팩스로 보내줘”라고 하거나 위에서 직접 만드세요.</li>}
            {items.map((a) => {
              const s = statusLabel(a);
              return (
                <li key={a.id}>
                  <button
                    className={`flex w-full items-center justify-between p-3 text-left text-sm hover:bg-gray-50 ${a.id === selectedId ? "bg-blue-50" : ""}`}
                    onClick={() => select(a.id)}
                  >
                    <span>
                      <b>{a.name}</b> · {a.recipient_count}명
                      <span className="block text-xs text-gray-500">{a.subject}</span>
                    </span>
                    <span className={`rounded px-2 py-0.5 text-xs ${s.cls}`}>{s.text}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        {detail && st && (
          <div className="space-y-3 rounded border border-[#E5E7EB] bg-white p-3 text-sm">
            <div className="flex items-center justify-between">
              <b>{detail.name}</b>
              <span className={`rounded px-2 py-0.5 text-xs ${st.cls}`}>{st.text}</span>
            </div>
            <div className="text-gray-600">
              제목: {detail.subject} · 수신 {detail.recipient_count}명 · 첨부: {detail.document_name}
            </div>
            {detail.document_matches === false && (
              <div className="rounded bg-red-50 p-2 text-red-700">첨부 파일이 요청 때와 달라졌거나 없습니다 — 승인·발송할 수 없습니다.</div>
            )}

            <FaxSitePreview key={detail.id} authId={detail.id} />
            <button className="text-[#2563EB] underline" onClick={() => setShowPreview((v) => !v)}>
              {showPreview ? "목차 접기" : "내용 목차 보기 (선택)"}
            </button>
            {showPreview && (
              <div className="space-y-1 rounded bg-gray-50 p-2" data-testid="fax-preview">
                <div>① 제목: {detail.subject}</div>
                <div>② 첨부 파일: {detail.document_ref}</div>
                <div>③ 수신자 ({detail.recipients?.length ?? 0}명)</div>
                <ul className="ml-4 max-h-40 list-disc overflow-auto">
                  {detail.recipients?.map((r) => (
                    <li key={r.fax}>
                      {r.name || "(이름 없음)"} · {r.fax}
                    </li>
                  ))}
                </ul>
                <div>
                  ④ 한도: 1회 {detail.max_per_run}건 · 1일 {detail.max_per_day}건 · 총 {detail.max_total}건
                </div>
                <div>
                  ⑤ 발송 시간대: {detail.allowed_start} ~ {detail.allowed_end}
                </div>
              </div>
            )}

            {canApprove && (
              <div className="space-y-2 border-t pt-2">
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
                  실제로 전송 (체크하지 않으면 전송 없이 계획만 기록하는 드라이런)
                </label>
                <button
                  className="rounded bg-green-600 px-3 py-1.5 text-white disabled:opacity-50"
                  disabled={busy || detail.document_matches === false}
                  onClick={() => act(() => faxApi.approve(detail.id, live, false))}
                >
                  이 내용으로 승인
                </button>
                <button
                  className="ml-2 rounded bg-[#2563EB] px-3 py-1.5 text-white disabled:opacity-50"
                  disabled={busy || detail.document_matches === false || killed}
                  onClick={() => act(() => faxApi.approve(detail.id, live, true))}
                >
                  승인하고 바로 발송
                </button>
              </div>
            )}

            <div className="flex flex-wrap gap-2 border-t pt-2">
              <button
                className="rounded bg-[#2563EB] px-3 py-1.5 text-white disabled:opacity-50"
                disabled={busy || !canSend}
                onClick={() => act(() => faxApi.run(detail.id))}
              >
                {run?.running ? "발송 중…" : "지금 발송"}
              </button>
              {!detail.revoked && (
                <button className="rounded border px-3 py-1.5" disabled={busy} onClick={() => act(() => faxApi.revoke(detail.id))}>
                  승인서 취소
                </button>
              )}
              {!detail.approved && !detail.revoked && <span className="self-center text-xs text-gray-500">승인해야 발송할 수 있습니다.</span>}
              {killed && <span className="self-center text-xs text-red-600">전체 정지 중이라 발송되지 않습니다.</span>}
            </div>
            {run?.last && (
              <div className={`rounded p-2 ${run.last.status === "done" ? "bg-green-50" : "bg-red-50"}`}>
                마지막 실행: {run.last.message}
              </div>
            )}
            {detail.pending_numbers && detail.pending_numbers.length > 0 && (
              <div className="space-y-1 rounded border border-amber-300 bg-amber-50 p-2" data-testid="fax-pending">
                <b>확인 필요 {detail.pending_numbers.length}건</b> — 결과를 확정하지 못해 다시 보내지 않고 멈춘 번호입니다.
                하나팩스 &quot;전송결과&quot; 메뉴에서 실제로 나갔는지 확인한 뒤 처리하세요.
                {detail.pending_numbers.map((n) => (
                  <div key={n} className="flex items-center justify-between gap-2">
                    <span>{n}</span>
                    <span className="space-x-1">
                      <button
                        className="rounded border bg-white px-2 py-0.5 disabled:opacity-50"
                        disabled={busy}
                        onClick={() => act(() => faxApi.resolvePending(detail.id, n, "sent"))}
                      >
                        발송됨 확인
                      </button>
                      <button
                        className="rounded border bg-white px-2 py-0.5 disabled:opacity-50"
                        disabled={busy}
                        onClick={() => act(() => faxApi.resolvePending(detail.id, n, "not_sent"))}
                      >
                        발송 안 됨(재전송 허용)
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            )}
            {log.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="fax-reconcile">
                <button
                  className="rounded border px-2 py-1 disabled:opacity-50"
                  disabled={busy || recon?.running}
                  onClick={() => act(() => faxApi.startReconcile(detail.id))}
                >
                  {recon?.running ? "전송결과 확인 중…" : "전송결과 확인 (최종 성공/실패)"}
                </button>
                <span className="text-gray-500">접수된 건을 하나팩스 전송결과와 대조합니다(읽기 전용, 발송 3분 뒤 자동 실행).</span>
                {recon?.state && recon.state.ok && (
                  <span>
                    확인 {recon.state.checked}건 → 성공 {recon.state.delivered}, 전달 실패 {recon.state.delivery_failed}
                    {recon.state.partial ? `, 일부 실패(상세 확인 필요) ${recon.state.partial}` : ""}
                    {recon.state.unmatched ? `, 대조 못 함 ${recon.state.unmatched}` : ""}
                  </span>
                )}
                {recon?.state && !recon.state.ok && <span className="text-red-600">{recon.state.message}</span>}
              </div>
            )}
            {log.length > 0 && (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-500">
                    <th>번호</th>
                    <th>상태</th>
                    <th>접수번호</th>
                    <th>시각</th>
                  </tr>
                </thead>
                <tbody>
                  {log.slice(0, 30).map((r, i) => (
                    <tr key={i}>
                      <td>{r.fax_digits}</td>
                      <td>{STATUS_LABEL[r.status] ?? r.status}</td>
                      <td>{r.job_id ?? "-"}</td>
                      <td>{r.created_at.replace("T", " ").slice(0, 16)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>

      <section className="flex h-[calc(100dvh-170px)] min-h-[420px] flex-col gap-2">
        <details className="rounded border border-[#E5E7EB] bg-white p-2 text-xs" data-testid="fax-ai-attachment">
          <summary className="cursor-pointer font-medium">AI에게 줄 첨부 파일 올리기 (선택)</summary>
          <div className="mt-2 space-y-1">
            <AttachmentField value={aiAttach} onChange={setAiAttach} showCopy />
            <div className="text-gray-500">올린 뒤 &quot;경로 복사&quot;를 눌러 AI 창에 붙여 넣고 &quot;이 파일을 ○○에게 팩스로 보내줘&quot;라고 말하면 됩니다.</div>
          </div>
        </details>
        <div className="min-h-0 flex-1">
        <UniversalChat domain="hanafax" agentHint={AGENT_HINT} title="AI 창 — 첨부 파일 경로와 받는 사람을 알려주세요" className="h-full" />
        </div>
      </section>
    </div>
  );
}

function NewForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [path, setPath] = useState("");
  const [recipients, setRecipients] = useState("");
  const [mode, setMode] = useState<"manual" | "group">("manual");
  const [groups, setGroups] = useState<AddressGroup[] | null>(null);
  const [groupId, setGroupId] = useState("");
  const [sync, setSync] = useState<GroupSyncStatus | null>(null);
  const [rangeStart, setRangeStart] = useState(1);
  const [rangeCount, setRangeCount] = useState(1000);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const group = groups?.find((g) => g.intid === groupId) ?? null;

  // 그룹 읽기 진행 상황 확인(백그라운드 — 큰 그룹은 몇 분)
  useEffect(() => {
    if (!groupId || !sync?.running) return;
    const t = setInterval(async () => {
      try {
        setSync(await faxApi.groupSyncStatus(groupId));
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    }, 3000);
    return () => clearInterval(t);
  }, [groupId, sync?.running]);

  async function loadGroups() {
    setBusy(true);
    setErr(null);
    try {
      setGroups(await faxApi.addressGroups());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function pickGroup(id: string) {
    setGroupId(id);
    setSync(null);
    setRangeStart(1);
    if (id) {
      try {
        setSync(await faxApi.groupSyncStatus(id));
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    }
  }

  async function startSync() {
    setErr(null);
    try {
      setSync(await faxApi.startGroupSync(groupId));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const base = { name: name || subject, subject, document_ref: path.trim().replace(/^"|"$/g, ""), allowed_start: "09:00", allowed_end: "18:00" };
      const created =
        mode === "group"
          ? await faxApi.create({ ...base, recipients: [], site_group: groupId, group_offset: Math.max(rangeStart - 1, 0), group_limit: Math.min(Math.max(rangeCount, 1), 1000) })
          : await (async () => {
              const rows = parseRecipients(recipients);
              return faxApi.create({ ...base, recipients: rows, max_per_run: Math.min(Math.max(rows.length, 1), 100), max_per_day: Math.min(Math.max(rows.length, 1), 300) });
            })();
      onCreated(created.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded border border-[#D1D5DB] px-2 py-1 text-sm";
  const tab = (active: boolean) => `rounded px-2 py-1 text-xs ${active ? "bg-[#2563EB] text-white" : "border"}`;
  const ready = mode === "manual" ? !!recipients : !!groupId && !!sync?.cached && !sync.running;
  return (
    <div className="space-y-2 border-b p-3">
      <input className={input} placeholder="이름 (예: 10월 영업 안내)" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={input} placeholder="팩스 제목" value={subject} onChange={(e) => setSubject(e.target.value)} />
      <AttachmentField value={path} onChange={setPath} />
      <div className="flex gap-2">
        <button className={tab(mode === "manual")} onClick={() => setMode("manual")}>
          직접 입력
        </button>
        <button className={tab(mode === "group")} onClick={() => setMode("group")}>
          하나팩스 주소록 그룹
        </button>
      </div>
      {mode === "manual" ? (
        <textarea
          className={input}
          rows={4}
          placeholder={"받는 사람 — 한 줄에 하나: 번호, 이름\n02-123-4567, 홍길동건설"}
          value={recipients}
          onChange={(e) => setRecipients(e.target.value)}
        />
      ) : (
        <div className="space-y-2 rounded bg-gray-50 p-2 text-xs" data-testid="fax-group-picker">
          {!groups ? (
            <button className="rounded border bg-white px-2 py-1 disabled:opacity-50" disabled={busy} onClick={loadGroups}>
              {busy ? "하나팩스 주소록을 읽는 중… (수십 초)" : "주소록 그룹 불러오기"}
            </button>
          ) : (
            <>
              <select className={input} value={groupId} onChange={(e) => pickGroup(e.target.value)}>
                <option value="">그룹을 고르세요</option>
                {groups.map((g) => (
                  <option key={g.intid} value={g.intid} disabled={g.members === 0}>
                    {g.name} · {g.members}명 (팩스번호 {g.fax_count}개)
                  </option>
                ))}
              </select>
              {group && (
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <button className="rounded border bg-white px-2 py-1 disabled:opacity-50" disabled={!!sync?.running} onClick={startSync}>
                      {sync?.running ? `읽는 중… ${sync.state?.page ?? 0}/${sync.state?.pages ?? "?"}쪽` : sync?.cached ? "다시 가져오기" : "이 그룹 가져오기 (읽기 전용)"}
                    </button>
                    {sync?.cached && !sync.running && <span className="text-green-700">가져옴 ✓ (24시간 안에 사용)</span>}
                    {sync?.state?.ok === false && <span className="text-red-600">{sync.state.message}</span>}
                  </div>
                  {sync?.cached && !sync.running && (
                    <div className="flex flex-wrap items-center gap-2">
                      <span>승인할 구간:</span>
                      <input type="number" min={1} max={group.members} className="w-20 rounded border px-1 py-0.5" value={rangeStart} onChange={(e) => setRangeStart(Number(e.target.value))} />
                      <span>번째부터</span>
                      <input type="number" min={1} max={1000} className="w-20 rounded border px-1 py-0.5" value={rangeCount} onChange={(e) => setRangeCount(Number(e.target.value))} />
                      <span>명 (한 번에 최대 1000명 — 큰 그룹은 구간을 나눠 승인)</span>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
      {err && <div className="text-sm text-red-600">{err}</div>}
      <button className="rounded bg-[#2563EB] px-3 py-1.5 text-sm text-white disabled:opacity-50" disabled={busy || !subject || !path || !ready} onClick={submit}>
        승인 대기로 올리기 (전송되지 않음)
      </button>
    </div>
  );
}
