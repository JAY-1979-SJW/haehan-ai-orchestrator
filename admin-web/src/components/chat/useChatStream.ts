"use client";
import { useRef, useCallback } from "react";

export interface StreamEvent {
  event: "text" | "done" | "error";
  data: unknown;
}

export function useChatStream() {
  const abortRef = useRef<AbortController | null>(null);

  const stream = useCallback(
    async (
      url: string,
      body: unknown,
      onEvent: (event: string, data: unknown) => void,
    ) => {
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: abortRef.current.signal,
      });

      if (!res.ok || !res.body) {
        onEvent("error", { message: `서버 오류 (${res.status})` });
        return;
      }

      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const eventLine = part.match(/^event: (.+)/m)?.[1]?.trim();
          const dataLine  = part.match(/^data: (.+)/m)?.[1]?.trim();
          if (eventLine && dataLine) {
            try { onEvent(eventLine, JSON.parse(dataLine)); } catch {}
          }
        }
      }
    },
    [],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  return { stream, abort };
}
