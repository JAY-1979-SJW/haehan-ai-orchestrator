"use client";

import { useState } from "react";

/**
 * Gmail 개인 메일함 AI 비서 — 안 읽은 메일 요약 + 회신 초안(AI) → 사람 승인 → 발송.
 * docs/specs/2026-09-29_personal_mailbox_ai_assistant.md 축소범위(Gmail만, 첨부 없음) 구현.
 *
 * 안전 설계: AI 초안 생성(/gmail/ai-draft-unread)은 읽기전용이고 발송 능력이 전혀 없다.
 * 실제 발송은 이 화면에서 사람이 초안을 검토·수정하고 "발송" 버튼을 눌러야만
 * (+ 브라우저 confirm 재확인) 별도로 /gmail/reply + /gmail/send 를 호출한다.
 */

interface DraftItem {
  mail_index: number;
  from: string;
  subject: string;
  summary: string;
  needs_reply: boolean;
  draft_reply: string;
}

interface ItemState {
  editedBody: string;
  sending: boolean;
  sent: boolean;
  error: string | null;
}

export function MailAssistantPanel() {
  const [items, setItems] = useState<DraftItem[] | null>(null);
  const [itemState, setItemState] = useState<Record<number, ItemState>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCheck() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/api/v1/gmail/ai-draft-unread", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 5 }),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      setItems(data.items);
      const nextState: Record<number, ItemState> = {};
      for (const it of data.items as DraftItem[]) {
        nextState[it.mail_index] = {
          editedBody: it.draft_reply,
          sending: false,
          sent: false,
          error: null,
        };
      }
      setItemState(nextState);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setItems(null);
    } finally {
      setLoading(false);
    }
  }

  function updateBody(mailIndex: number, body: string) {
    setItemState((s) => ({ ...s, [mailIndex]: { ...s[mailIndex], editedBody: body } }));
  }

  async function handleSend(mailIndex: number) {
    const body = itemState[mailIndex]?.editedBody ?? "";
    if (!body.trim()) return;
    if (!window.confirm("이 내용으로 실제 회신을 발송합니다. 계속할까요?")) return;

    setItemState((s) => ({ ...s, [mailIndex]: { ...s[mailIndex], sending: true, error: null } }));
    try {
      const replyRes = await fetch("/api/proxy/api/v1/gmail/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mail_index: mailIndex, body, reply_all: false, dry_run: false }),
      });
      const replyData = await replyRes.json();
      if (!replyRes.ok || replyData.ok === false) {
        throw new Error(replyData.detail || `회신 작성 실패 (HTTP ${replyRes.status})`);
      }

      const sendRes = await fetch("/api/proxy/api/v1/gmail/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true }),
      });
      const sendData = await sendRes.json();
      if (!sendRes.ok || sendData.ok === false) {
        throw new Error(sendData.detail || `발송 실패 (HTTP ${sendRes.status})`);
      }

      setItemState((s) => ({ ...s, [mailIndex]: { ...s[mailIndex], sending: false, sent: true } }));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setItemState((s) => ({ ...s, [mailIndex]: { ...s[mailIndex], sending: false, error: message } }));
    }
  }

  return (
    <section data-testid="mail-assistant-section">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Gmail 메일 비서 (AI 요약 + 회신 초안)</h2>
        <button
          type="button"
          onClick={handleCheck}
          disabled={loading}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "확인 중... (최대 1분)" : "메일 확인 + AI 초안 작성"}
        </button>
      </div>

      {error && (
        <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">{error}</div>
      )}

      {items && items.length === 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4 text-xs text-gray-500">
          안 읽은 메일이 없습니다.
        </div>
      )}

      {items && items.length > 0 && (
        <div className="space-y-3">
          {items.map((it) => {
            const st = itemState[it.mail_index];
            return (
              <div key={it.mail_index} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-800">{it.subject}</span>
                  {!it.needs_reply && (
                    <span className="rounded bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500">회신 불필요</span>
                  )}
                </div>
                <div className="mt-1 text-xs text-gray-500">{it.from}</div>
                <div className="mt-2 text-xs text-gray-600">{it.summary}</div>

                {it.needs_reply && st && !st.sent && (
                  <div className="mt-3 border-t border-gray-100 pt-3">
                    <textarea
                      className="w-full rounded border border-gray-200 p-2 text-xs"
                      rows={4}
                      value={st.editedBody}
                      onChange={(e) => updateBody(it.mail_index, e.target.value)}
                    />
                    <div className="mt-2 flex items-center justify-end gap-2">
                      {st.error && <span className="text-[11px] text-red-600">{st.error}</span>}
                      <button
                        type="button"
                        onClick={() => handleSend(it.mail_index)}
                        disabled={st.sending}
                        className="rounded-md bg-orange-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-orange-700 disabled:opacity-50"
                      >
                        {st.sending ? "발송 중..." : "이 내용으로 발송"}
                      </button>
                    </div>
                  </div>
                )}
                {st?.sent && <div className="mt-2 text-xs font-medium text-green-700">✓ 발송 완료</div>}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
