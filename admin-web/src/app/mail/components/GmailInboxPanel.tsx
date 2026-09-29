"use client";

import { useState } from "react";

interface GmailInboxItem {
  message_id: string;
  from: string;
  subject: string;
  body_summary: string;
  received_at: string;
}

interface GmailInboxResponse {
  ok: boolean;
  items: GmailInboxItem[];
  count: number;
  duration_ms: number;
  source: string;
}

/**
 * 버튼 클릭 → 실제 에이전트 작업 실행 검증용 패널.
 * GET /api/v1/gmail/inbox (CDP 기존 로그인 세션 재사용, 읽기전용) 를
 * 기존 공용 프록시(/api/proxy/[...path])로 호출한다. 신규 백엔드 로직 없음.
 */
export function GmailInboxPanel() {
  const [items, setItems] = useState<GmailInboxItem[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState<number | null>(null);

  async function handleFetch() {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/api/v1/gmail/inbox?max_results=10&source=cdp");
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`HTTP ${res.status}: ${detail.slice(0, 200)}`);
      }
      const data: GmailInboxResponse = await res.json();
      if (!data.ok) throw new Error("응답에 ok=false");
      setItems(data.items);
      setDurationMs(data.duration_ms);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setItems(null);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section data-testid="gmail-inbox-section">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Gmail 받은편지함 (읽기전용)</h2>
        <button
          type="button"
          onClick={handleFetch}
          disabled={isLoading}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {isLoading ? "조회 중..." : "받은편지함 조회"}
        </button>
      </div>

      {error && (
        <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
          조회 실패: {error}
        </div>
      )}

      {items && (
        <div className="space-y-2">
          {durationMs !== null && (
            <div className="text-[11px] text-gray-400">
              {items.length}건 · {durationMs}ms · CDP 세션 기준
            </div>
          )}
          {items.length === 0 && (
            <div className="rounded-lg border border-gray-200 bg-white p-4 text-xs text-gray-500">
              메일이 없습니다.
            </div>
          )}
          {items.map((mail) => (
            <div
              key={mail.message_id || mail.subject}
              className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-800">{mail.subject}</span>
                <span className="text-[11px] text-gray-400">{mail.received_at}</span>
              </div>
              <div className="mt-1 text-xs text-gray-500">{mail.from}</div>
              {mail.body_summary && (
                <div className="mt-1 text-xs text-gray-400">{mail.body_summary}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
