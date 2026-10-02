"use client";

import { useCallback, useEffect, useState } from "react";
import {
  bulkApi,
  estimate,
  formatKst,
  PAUSE_REASON,
  STATUS_LABEL,
  stateOf,
  type BulkAuthorization,
  type BulkLogRow,
  type BulkStatus,
} from "../../lib/bulkApi";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const TONE: Record<string, string> = {
  gray: "bg-[#F3F4F6] text-[#374151]",
  blue: "bg-[#DBEAFE] text-[#1D4ED8]",
  green: "bg-[#D1FAE5] text-[#047857]",
  orange: "bg-[#FFEDD5] text-[#C2410C]",
  red: "bg-[#FEE2E2] text-[#B91C1C]",
};
const btn = "rounded-lg border border-[#E5E7EB] bg-white px-3 py-1.5 text-[12px] disabled:opacity-40";

/**
 * 대량 발송 1건의 진행 화면. 순서: ① 본인 주소 시험 발송 → ② 승인(드라이런/실전송) → ③ 실행·멈춤·재개 → 진행 상황.
 * 실전송 승인은 확인 단계를 한 번 더 거친다. 5초마다 진행 상황을 새로 읽는다.
 * 기준서: docs/specs/2026-10-02_mail_bulk_sequential.md §5
 */
export function BulkDetail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [auth, setAuth] = useState<BulkAuthorization | null>(null);
  const [status, setStatus] = useState<BulkStatus | null>(null);
  const [log, setLog] = useState<BulkLogRow[]>([]);
  const [selfTo, setSelfTo] = useState("");
  const [confirmLive, setConfirmLive] = useState(false);
  const [optOut, setOptOut] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const reload = useCallback(async () => {
    try {
      const [d, l] = await Promise.all([bulkApi.get(id), bulkApi.log(id)]);
      setAuth(d.authorization);
      setStatus(d.status);
      setLog(l);
    } catch (e) {
      setNotice({ kind: "err", text: errText(e) });
    }
  }, [id]);

  useEffect(() => {
    setConfirmLive(false);
    setNotice(null);
    void reload();
    const timer = setInterval(() => void reload(), 5000);
    return () => clearInterval(timer);
  }, [reload]);

  async function act(fn: () => Promise<unknown>, okText: string) {
    setBusy(true);
    setNotice(null);
    try {
      await fn();
      setNotice({ kind: "ok", text: okText });
      await reload();
      onChanged();
    } catch (e) {
      setNotice({ kind: "err", text: errText(e) });
    } finally {
      setBusy(false);
    }
  }

  if (!auth || !status) return <div className="p-4 text-[13px] text-[#6B7280]">{notice?.text ?? "불러오는 중…"}</div>;

  const st = stateOf(auth);
  const sent = status.counts.sent ?? 0;
  const unknown = status.counts.unknown ?? 0;
  const failed = status.counts.failed ?? 0;
  const done = sent + unknown;
  const pct = auth.recipient_count ? Math.round((done / auth.recipient_count) * 100) : 0;
  const est = estimate(auth.recipient_count, auth.max_per_day, auth.interval_sec);
  const canRun = auth.approved && !auth.revoked && !auth.paused && !status.running && !status.kill_switch && status.remaining > 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-[15px] font-semibold text-[#111827]">{auth.name}</h2>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${TONE[st.tone]}`}>{st.label}</span>
        {status.running && <span className="rounded-full bg-[#FEF3C7] px-2 py-0.5 text-[11px] font-semibold text-[#92400E]">발송 중…</span>}
        {status.kill_switch && <span className="rounded-full bg-[#FEE2E2] px-2 py-0.5 text-[11px] font-semibold text-[#B91C1C]">전체 정지 켜짐</span>}
      </div>

      {notice && (
        <p role="status" className="rounded-lg px-3 py-2 text-[12px]" style={{ background: notice.kind === "ok" ? "#ECFDF5" : "#FEF2F2", color: notice.kind === "ok" ? "#047857" : "#B91C1C" }}>
          {notice.text}
        </p>
      )}
      {auth.paused && (
        <p role="alert" className="rounded-lg bg-[#FFF7ED] px-3 py-2 text-[12px] text-[#9A3412]">
          <b>멈춤:</b> {PAUSE_REASON[auth.paused_reason] ?? auth.paused_reason} 원인을 확인한 뒤 &lsquo;재개&rsquo;를 누르세요.
        </p>
      )}

      <section className="rounded-xl border border-[#E5E7EB] p-3 text-[12px] text-[#374151]">
        <div className="font-medium">제목: {auth.subject}</div>
        <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-[12px] text-[#4B5563]">{auth.body_preview}</pre>
        <div className="mt-2 text-[#6B7280]">
          수신자 {auth.recipient_count}명 · 하루 {auth.max_per_day}통 · 간격 {auth.interval_sec}초 · {auth.allowed_start}~{auth.allowed_end} · 첨부 {auth.attachments.length}개 · 성격 {auth.kind === "promo" ? "홍보·광고" : "거래·업무 안내"}
        </div>
        <div className="mt-1 text-[#6B7280]">
          미리보기: {auth.recipients_preview.slice(0, 5).map((r) => `${r.email}${r.name ? `(${r.name})` : ""}`).join(", ")}
          {auth.recipient_count > 5 ? " …" : ""}
        </div>
      </section>

      <section className="rounded-xl border border-[#E5E7EB] p-3">
        <div className="mb-1 flex items-center justify-between text-[12px] text-[#374151]">
          <span>진행 {done}/{auth.recipient_count} ({pct}%) · 남음 {status.remaining}</span>
          <span>보냄 {sent} · 실패 {failed} · 확인 필요 {unknown}{status.counts.dry_run ? ` · 드라이런 ${status.counts.dry_run}` : ""}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[#F3F4F6]">
          <div className="h-full bg-[#F97316]" style={{ width: `${pct}%` }} />
        </div>
        {status.last?.summary && (
          <p className="mt-2 text-[12px] text-[#6B7280]">
            마지막 실행: 보냄 {status.last.summary.sent} · 실패 {status.last.summary.failed} · 확인 필요 {status.last.summary.unknown}
            {status.last.summary.decision !== "send" ? ` · 판정 ${status.last.summary.decision}(${status.last.summary.reason})` : ""}
          </p>
        )}
        {status.last?.status === "failed" && <p className="mt-2 text-[12px] text-[#B91C1C]">마지막 실행 실패: {status.last.message}</p>}
      </section>

      {!auth.approved && !auth.revoked && (
        <section className="rounded-xl border border-[#E5E7EB] p-3 text-[12px]">
          <div className="mb-1 font-semibold text-[#111827]">① 본인 주소로 시험 발송 {auth.test_sent_at ? `✓ 완료 (${formatKst(auth.test_sent_at)} KST)` : "(실전송 승인의 필수 단계)"}</div>
          <div className="flex flex-wrap gap-2">
            <input className="min-w-[240px] flex-1 rounded-lg border border-[#E5E7EB] px-3 py-1.5" value={selfTo} onChange={(e) => setSelfTo(e.target.value)} placeholder="내가 받아 볼 메일 주소" />
            <button type="button" className={btn} disabled={busy || !selfTo.includes("@")} onClick={() => void act(() => bulkApi.selfTest(id, selfTo.trim()), "시험 메일을 1통 보냈습니다. 받은 메일함에서 모양을 확인하세요")}>
              시험 1통 보내기
            </button>
          </div>
          <div className="mb-1 mt-3 font-semibold text-[#111827]">② 승인 (승인 후에는 내용을 바꿀 수 없습니다)</div>
          {!confirmLive ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" className={btn} disabled={busy} onClick={() => void act(() => bulkApi.approve(id, false), "드라이런으로 승인했습니다(실제 전송 없음)")}>
                드라이런으로 승인
              </button>
              <button type="button" className="rounded-lg bg-[#F97316] px-3 py-1.5 text-[12px] font-semibold text-white disabled:opacity-40" disabled={busy || !auth.test_sent_at} onClick={() => setConfirmLive(true)}>
                실전송으로 승인…
              </button>
            </div>
          ) : (
            <div className="rounded-lg bg-[#FFF7ED] p-3 text-[#9A3412]">
              <p>
                <b>{auth.recipient_count}명</b>에게 하루 {auth.max_per_day}통씩 약 <b>{est.days}일</b>에 걸쳐(하루 약 {est.minutesPerDay}분) 한 명씩 보냅니다. 승인하면 수신자·제목·본문·첨부는 바꿀 수 없고, 보낸 메일은 되돌릴 수 없습니다.
              </p>
              <div className="mt-2 flex gap-2">
                <button type="button" className="rounded-lg bg-[#DC2626] px-3 py-1.5 text-[12px] font-semibold text-white disabled:opacity-40" disabled={busy} onClick={() => void act(() => bulkApi.approve(id, true), "실전송으로 승인했습니다. 이제 실행할 수 있습니다")}>
                  확인하고 승인
                </button>
                <button type="button" className={btn} onClick={() => setConfirmLive(false)}>돌아가기</button>
              </div>
            </div>
          )}
        </section>
      )}

      {auth.approved && !auth.revoked && (
        <section className="flex flex-wrap items-center gap-2">
          <button type="button" className="rounded-lg bg-[#F97316] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-40" disabled={busy || !canRun} onClick={() => void act(() => bulkApi.run(id), "차례 발송을 시작했습니다")}>
            {auth.live ? "지금 차례 발송 시작" : "드라이런 실행"}
          </button>
          {!auth.paused ? (
            <button type="button" className={btn} disabled={busy} onClick={() => void act(() => bulkApi.pause(id), "멈췄습니다(진행 중인 한 통까지만 마무리)")}>일시 멈춤</button>
          ) : (
            <button type="button" className={btn} disabled={busy} onClick={() => void act(() => bulkApi.resume(id), "재개했습니다. 실행 버튼으로 이어서 보냅니다")}>재개</button>
          )}
        </section>
      )}

      {!auth.revoked && (
        <section className="flex flex-wrap items-center gap-2 text-[12px]">
          <button type="button" className="rounded-lg border border-[#FCA5A5] bg-white px-3 py-1.5 text-[12px] text-[#B91C1C] disabled:opacity-40" disabled={busy} onClick={() => void act(() => bulkApi.revoke(id), "취소했습니다(되돌릴 수 없음)")}>
            승인서 취소
          </button>
          <span className="text-[#9CA3AF]">취소하면 남은 사람에게 더 보내지 않습니다.</span>
        </section>
      )}

      <section className="rounded-xl border border-[#E5E7EB] p-3 text-[12px]">
        <div className="mb-1 font-semibold text-[#111827]">수신거부 등록 · 전체 정지</div>
        <div className="flex flex-wrap items-center gap-2">
          <input className="min-w-[220px] rounded-lg border border-[#E5E7EB] px-3 py-1.5" value={optOut} onChange={(e) => setOptOut(e.target.value)} placeholder="수신거부 요청한 주소" />
          <button type="button" className={btn} disabled={busy || !optOut.includes("@")} onClick={() => void act(() => bulkApi.optOut(optOut.trim(), "수신거부 요청"), "수신거부 목록에 추가했습니다(이후 모든 대량 발송에서 제외)").then(() => setOptOut(""))}>
            수신거부 추가
          </button>
          <button type="button" className={btn} disabled={busy} onClick={() => void act(() => bulkApi.killSwitch(!status.kill_switch), status.kill_switch ? "전체 정지를 껐습니다" : "전체 정지를 켰습니다(모든 대량 발송이 즉시 멈춤)")}>
            {status.kill_switch ? "전체 정지 끄기" : "전체 정지 켜기"}
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-[#E5E7EB] p-3">
        <div className="mb-1 text-[12px] font-semibold text-[#111827]">발송 이력 (최근 200건, 한국 시간, 주소는 가림)</div>
        {log.length === 0 ? (
          <p className="text-[12px] text-[#9CA3AF]">아직 이력이 없습니다.</p>
        ) : (
          <table className="w-full text-left text-[12px]">
            <tbody>
              {log.map((r, i) => (
                <tr key={`${r.created_at}-${i}`} className="border-t border-[#F3F4F6]">
                  <td className="py-1 pr-2 text-[#6B7280]">{formatKst(r.created_at, true)}</td>
                  <td className="py-1 pr-2">{r.email}</td>
                  <td className="py-1 pr-2 font-medium">{STATUS_LABEL[r.status] ?? r.status}</td>
                  <td className="py-1 text-[#9CA3AF]">{r.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
