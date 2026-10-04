"use client";

import { useEffect, useRef } from "react";
import { mailboxApi } from "./api";

const VISIBLE_MS = 30_000;
const HIDDEN_MS = 120_000;
const MAX_BACKOFF_MS = 600_000;

export interface NewMailEvent {
  count: number;
  label: string;
  /** 이번 확인 직전의 UIDNEXT — 이 번호 이상이 새로 온 메일이다 */
  sinceUid: number;
  unseen: number;
}

/**
 * 받은편지함 새 메일 감시(주기 확인). 서버는 STATUS 한 줄만 쓰고 읽음 표시·AI 기준점을 바꾸지 않는다.
 * 탭이 보이면 30초, 숨겨지면 120초, 연속 실패하면 2배씩(최대 10분). 첫 확인은 기준만 잡고 알리지 않는다.
 * 기준서: docs/specs/2026-10-02_mailbox_new_mail_alert.md
 */
export function useNewMailWatch(account: string, enabled: boolean, onNew: (e: NewMailEvent) => void) {
  const cb = useRef(onNew);
  cb.current = onNew;

  useEffect(() => {
    if (!account || !enabled) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let prev: { uidnext: number; uidvalidity: number } | null = null;
    let failures = 0;

    const delay = () => {
      const base = document.visibilityState === "visible" ? VISIBLE_MS : HIDDEN_MS;
      return Math.min(base * 2 ** failures, MAX_BACKOFF_MS);
    };

    const tick = async () => {
      try {
        const r = await mailboxApi.inboxWatch(account, prev);
        failures = 0;
        if (!r.reset && r.new_count > 0 && prev) {
          cb.current({ count: r.new_count, label: r.new_label, sinceUid: prev.uidnext, unseen: r.unseen });
        } else if (r.reset && prev === null) {
          cb.current({ count: 0, label: "0", sinceUid: r.uidnext, unseen: r.unseen });
        }
        prev = { uidnext: r.uidnext, uidvalidity: r.uidvalidity };
      } catch {
        failures = Math.min(failures + 1, 5);
      }
      if (!stopped) timer = setTimeout(() => void tick(), delay());
    };

    void tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [account, enabled]);
}
