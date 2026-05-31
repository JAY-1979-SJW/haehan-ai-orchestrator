"use client";
import { useState, useEffect, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";

const api = (path: string, opts?: RequestInit) =>
  fetch(`${API_BASE}/api/v1/hanafax${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", ...(opts?.headers ?? {}) },
  });

// ── 타입 ─────────────────────────────────────────────────────────────────────
interface Status { ok: boolean; message: string; fax_number: string; balance: string; plan: string; member_status: string; new_fax_count: string }
interface QueueItem { receiver_fax: string; receiver_name: string; subject: string; bid_name: string; status: string }
interface BatchItem { index: number; receiver_fax: string; receiver_name: string; subject: string }

// ── 상태 카드 ─────────────────────────────────────────────────────────────────
function StatusCard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api("/status");
      if (r.ok) setStatus(await r.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[#1D4ED8] flex items-center justify-center text-white text-sm font-bold">팩</div>
          <div>
            <p className="text-sm font-bold text-[#111827]">하나팩스</p>
            <p className="text-xs text-[#9CA3AF]">www.hanafax.com</p>
          </div>
        </div>
        <button onClick={load} disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-[#6B7280] hover:border-[#1D4ED8] hover:text-[#1D4ED8] disabled:opacity-40 transition-colors">
          {loading ? "조회 중..." : "새로고침"}
        </button>
      </div>

      {status ? (
        status.ok ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              { label: "팩스번호", value: status.fax_number },
              { label: "전송 잔액", value: status.balance, highlight: true },
              { label: "새 팩스", value: status.new_fax_count },
              { label: "요금제", value: status.plan },
              { label: "회원 상태", value: status.member_status },
            ].map((i) => (
              <div key={i.label} className="rounded-xl bg-[#F9FAFB] border border-[#E5E7EB] px-3 py-2.5">
                <p className="text-[10px] text-[#9CA3AF] mb-0.5">{i.label}</p>
                <p className={`text-sm font-bold ${i.highlight ? "text-[#1D4ED8]" : "text-[#111827]"}`}>{i.value || "-"}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[#DC2626]">{status.message}</p>
        )
      ) : (
        <p className="text-xs text-[#9CA3AF]">{loading ? "조회 중..." : "새로고침을 눌러주세요"}</p>
      )}
    </div>
  );
}

// ── 단건 발송 ─────────────────────────────────────────────────────────────────
function SendPanel() {
  const [fax, setFax] = useState("");
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string; job_id?: string } | null>(null);

  const send = async () => {
    if (!fax || !subject) return;
    setSending(true); setResult(null);
    try {
      const r = await api("/send", {
        method: "POST",
        body: JSON.stringify({ receiver_fax: fax, subject, body, receiver_name: name, confirmed }),
      });
      setResult(await r.json());
    } finally { setSending(false); }
  };

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 space-y-4">
      <p className="text-sm font-bold text-[#111827]">단건 팩스 발송</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-[#374151] mb-1">수신 팩스번호 *</label>
          <input value={fax} onChange={(e) => setFax(e.target.value)} placeholder="02-XXXX-XXXX"
            className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316]" />
        </div>
        <div>
          <label className="block text-xs font-medium text-[#374151] mb-1">수신자명</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="ABC건설"
            className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316]" />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-[#374151] mb-1">제목 *</label>
        <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="팩스 제목"
          className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316]" />
      </div>

      <div>
        <label className="block text-xs font-medium text-[#374151] mb-1">본문</label>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} placeholder="팩스 본문 내용"
          className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316] resize-none" />
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)}
          className="w-4 h-4 rounded accent-[#F97316]" />
        <span className="text-xs text-[#374151]">팩스 발송을 승인합니다</span>
      </label>

      <button onClick={send} disabled={sending || !fax || !subject || !confirmed}
        className="w-full py-2.5 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-40 transition-colors">
        {sending ? "발송 중..." : "팩스 발송"}
      </button>

      {result && (
        <div className={`rounded-xl px-4 py-3 text-sm ${result.ok ? "bg-[#F0FDF4] border border-[#BBF7D0] text-[#16A34A]" : "bg-[#FEF2F2] border border-[#FECACA] text-[#DC2626]"}`}>
          {result.ok ? "✓" : "✗"} {result.message}
          {result.job_id && <span className="ml-2 text-xs">접수번호: {result.job_id}</span>}
        </div>
      )}
    </div>
  );
}

// ── 큐 목록 ──────────────────────────────────────────────────────────────────
function QueuePanel() {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState<BatchItem[] | null>(null);
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState<{ sent: number; failed: number } | null>(null);

  const loadQueue = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api("/queue");
      if (r.ok) setQueue(await r.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadQueue(); }, [loadQueue]);

  const loadPlan = async () => {
    const r = await api("/batch/plan", { method: "POST", body: JSON.stringify({ limit: 10, delay_seconds: 30 }) });
    if (r.ok) { const d = await r.json(); setPlan(d.items); }
  };

  const execute = async () => {
    setExecuting(true);
    try {
      const r = await api("/batch/execute", {
        method: "POST",
        body: JSON.stringify({ confirmed: true, confirm_text: "HANAFAX_APPROVED_BATCH", limit: 10, delay_seconds: 30 }),
      });
      if (r.ok) setExecResult(await r.json());
    } finally { setExecuting(false); }
  };

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-bold text-[#111827]">발송 큐 <span className="text-[#9CA3AF] font-normal text-xs">({queue.length}건)</span></p>
        <div className="flex gap-2">
          <button onClick={loadQueue} disabled={loading}
            className="text-xs px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-[#6B7280] hover:border-[#1D4ED8] hover:text-[#1D4ED8] disabled:opacity-40 transition-colors">
            새로고침
          </button>
          <button onClick={loadPlan}
            className="text-xs px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-[#374151] hover:border-[#1D4ED8] hover:text-[#1D4ED8] transition-colors">
            발송 계획
          </button>
        </div>
      </div>

      {queue.length === 0 ? (
        <p className="text-xs text-[#9CA3AF] text-center py-4">큐가 비어 있습니다<br/><span className="text-[10px]">data/hanafax_queue.jsonl 파일에 추가하세요</span></p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[#E5E7EB]">
                {["수신자", "팩스번호", "제목", "상태"].map((h) => (
                  <th key={h} className="text-left text-[#9CA3AF] font-semibold pb-2 pr-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {queue.map((q, i) => (
                <tr key={i} className="border-b border-[#F3F4F6]">
                  <td className="py-2 pr-3 font-medium text-[#111827]">{q.receiver_name || "-"}</td>
                  <td className="py-2 pr-3 font-mono text-[#374151]">{q.receiver_fax}</td>
                  <td className="py-2 pr-3 text-[#6B7280] truncate max-w-[200px]">{q.subject}</td>
                  <td className="py-2">
                    <span className={`px-2 py-0.5 rounded-full font-semibold ${q.status === "sent" ? "bg-[#F0FDF4] text-[#16A34A]" : "bg-[#F9FAFB] text-[#6B7280]"}`}>
                      {q.status === "sent" ? "발송완료" : "대기"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 배치 계획 */}
      {plan && (
        <div className="border border-[#FED7AA] rounded-xl p-4 bg-[#FFF7ED] space-y-3">
          <p className="text-xs font-bold text-[#C2410C]">발송 계획 ({plan.length}건) — 확인 후 실행하세요</p>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {plan.map((p) => (
              <div key={p.index} className="flex gap-2 text-xs text-[#374151]">
                <span className="text-[#9CA3AF] w-4">{p.index}</span>
                <span className="font-mono">{p.receiver_fax}</span>
                <span>{p.receiver_name}</span>
                <span className="text-[#6B7280] truncate">{p.subject}</span>
              </div>
            ))}
          </div>
          <button onClick={execute} disabled={executing}
            className="w-full py-2 rounded-xl bg-[#DC2626] text-white text-xs font-semibold hover:bg-[#B91C1C] disabled:opacity-40 transition-colors">
            {executing ? "발송 중..." : `${plan.length}건 실 발송 승인 실행`}
          </button>
          {execResult && (
            <p className="text-xs text-[#16A34A] font-semibold">완료 — 성공: {execResult.sent}건 / 실패: {execResult.failed}건</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function HanafaxPage() {
  return (
    <PageShell title="하나팩스" description="팩스 발송 자동화" chatDomain="hanafax">
      <div className="space-y-5 w-full">
        <StatusCard />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <SendPanel />
          <QueuePanel />
        </div>
      </div>
    </PageShell>
  );
}
