"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { mailboxApi } from "../../lib/api";
import { bulkApi, stateOf, type BulkAuthorization } from "../../lib/bulkApi";
import { BulkCreateForm } from "./BulkCreateForm";
import { BulkDetail } from "./BulkDetail";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const DOT: Record<string, string> = { gray: "#9CA3AF", blue: "#3B82F6", green: "#10B981", orange: "#F97316", red: "#EF4444" };

/**
 * 메일 순차 대량 발송 — 승인서 목록과 만들기·진행 화면. 수신자마다 따로, 간격을 두고 한 명씩 차례로 보낸다.
 * 관리자 전용이며 AI 업무 창에서는 다루지 못한다. 기준서: docs/specs/2026-10-02_mail_bulk_sequential.md
 */
export function BulkApp() {
  const [items, setItems] = useState<BulkAuthorization[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [account, setAccount] = useState("");
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    try {
      setItems(await bulkApi.list());
      setError("");
    } catch (e) {
      setError(errText(e));
    }
  }, []);

  useEffect(() => {
    void reload();
    mailboxApi
      .accounts()
      .then((a) => setAccount((a.find((x) => x.ready) ?? a[0])?.account ?? ""))
      .catch((e) => setError(errText(e)));
  }, [reload]);

  return (
    <div className="flex h-[calc(100dvh-132px)] min-h-[520px] flex-col gap-2">
      <div className="flex shrink-0 items-center gap-3 text-[12px] text-[#6B7280]">
        <Link href="/mailbox" className="rounded-lg border border-[#E5E7EB] bg-white px-3 py-1 text-[#374151]">← 메일함</Link>
        <span>수신자마다 따로 한 통씩, 간격을 두고 차례로 보냅니다. 승인한 내용만 보내고, 문제가 생기면 스스로 멈춥니다.</span>
      </div>
      {error && <p role="alert" className="shrink-0 rounded-lg bg-[#FEF2F2] px-3 py-2 text-[12px] text-[#B91C1C]">{error}</p>}
      <div className="flex min-h-0 flex-1 overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white">
        <aside className="flex w-72 shrink-0 flex-col border-r border-[#F3F4F6]">
          <div className="p-3">
            <button type="button" disabled={!account} onClick={() => { setCreating(true); setSelected(null); }} className="w-full rounded-lg bg-[#F97316] px-3 py-2 text-[13px] font-semibold text-white disabled:opacity-40">+ 새 대량 발송</button>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {items.length === 0 && <li className="px-4 py-6 text-center text-[12px] text-[#9CA3AF]">아직 만든 대량 발송이 없습니다.</li>}
            {items.map((a) => {
              const st = stateOf(a);
              return (
                <li key={a.id}>
                  <button type="button" onClick={() => { setSelected(a.id); setCreating(false); }} className="w-full border-b border-[#F9FAFB] px-4 py-3 text-left" style={{ background: selected === a.id ? "#FFF7ED" : "transparent" }}>
                    <div className="truncate text-[13px] font-medium text-[#111827]">{a.name}</div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[#6B7280]">
                      <span className="inline-block h-2 w-2 rounded-full" style={{ background: DOT[st.tone] }} />
                      {st.label} · {a.recipient_count}명
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>
        <section className="flex min-w-0 flex-1 flex-col">
          {creating && (
            <BulkCreateForm
              account={account}
              onCancel={() => setCreating(false)}
              onCreated={(a) => { setCreating(false); setSelected(a.id); void reload(); }}
            />
          )}
          {!creating && selected && <BulkDetail key={selected} id={selected} onChanged={() => void reload()} />}
          {!creating && !selected && <div className="m-auto text-[13px] text-[#9CA3AF]">왼쪽에서 선택하거나 새 대량 발송을 만드세요.</div>}
        </section>
      </div>
    </div>
  );
}
