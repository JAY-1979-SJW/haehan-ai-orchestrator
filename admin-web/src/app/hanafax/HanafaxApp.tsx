"use client";

import { useCallback, useEffect, useState } from "react";
import { UniversalChat } from "@/components/chat/UniversalChat";
import { faxApi, parseRecipients, type Authorization, type LogRow, type RunStatus } from "./api";

/**
 * 하나팩스 화면 — 왼쪽: 승인서 목록·상세(미리보기·승인·발송·이력), 오른쪽: AI 창.
 *
 * 안전 설계
 * - 발송은 "승인" 뒤에만 가능하다(서버가 승인 전 발송을 거부). AI 창은 승인 대기 초안만 만들 수 있다.
 * - 미리보기(수신자·제목·문서·한도 목차)는 접이식이다. 열어볼지는 사용자가 정하고, 열지 않아도 승인할 수 있다.
 * - 기본은 드라이런(전송 없음). 실전송은 '실제로 전송' 을 체크해야 한다.
 */

const POLL_MS = 4000;

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
      const [d, l, r] = await Promise.all([faxApi.get(id), faxApi.log(id), faxApi.runStatus(id)]);
      setDetail(d);
      setLog(l);
      setRun(r);
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

            <button className="text-[#2563EB] underline" onClick={() => setShowPreview((v) => !v)}>
              {showPreview ? "미리보기 접기" : "미리보기 보기 (선택)"}
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
                  onClick={() => act(() => faxApi.approve(detail.id, live))}
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
                      <td>{r.status}</td>
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

      <section className="h-[calc(100dvh-170px)] min-h-[420px]">
        <UniversalChat domain="hanafax" title="AI 창 — 첨부 파일 경로와 받는 사람을 알려주세요" className="h-full" />
      </section>
    </div>
  );
}

function NewForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [path, setPath] = useState("");
  const [recipients, setRecipients] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const rows = parseRecipients(recipients);
      const created = await faxApi.create({
        name: name || subject,
        subject,
        document_ref: path.trim().replace(/^"|"$/g, ""),
        recipients: rows,
        max_per_run: Math.min(Math.max(rows.length, 1), 100),
        max_per_day: Math.min(Math.max(rows.length, 1), 300),
        allowed_start: "09:00",
        allowed_end: "18:00",
      });
      onCreated(created.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded border border-[#D1D5DB] px-2 py-1 text-sm";
  return (
    <div className="space-y-2 border-b p-3">
      <input className={input} placeholder="이름 (예: 10월 영업 안내)" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={input} placeholder="팩스 제목" value={subject} onChange={(e) => setSubject(e.target.value)} />
      <input className={input} placeholder="첨부 파일 경로 (pdf/docx/doc 전체 경로)" value={path} onChange={(e) => setPath(e.target.value)} />
      <textarea
        className={input}
        rows={4}
        placeholder={"받는 사람 — 한 줄에 하나: 번호, 이름\n02-123-4567, 홍길동건설"}
        value={recipients}
        onChange={(e) => setRecipients(e.target.value)}
      />
      {err && <div className="text-sm text-red-600">{err}</div>}
      <button className="rounded bg-[#2563EB] px-3 py-1.5 text-sm text-white disabled:opacity-50" disabled={busy || !subject || !path || !recipients} onClick={submit}>
        승인 대기로 올리기 (전송되지 않음)
      </button>
    </div>
  );
}
