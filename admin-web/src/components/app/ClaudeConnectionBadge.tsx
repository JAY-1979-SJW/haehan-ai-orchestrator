"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

// 데스크톱 앱(Electron)에서만 보이는 Claude MCP 연결 표시 — 화면 오른쪽 아래.
// - 처음(아직 묻지 않음): 안내 카드 "연결 / 나중에" (Windows 기본 대화상자 대신 화면 안에서 묻는다, 대표님 지시 2026-10-08)
// - 연결됨: 초록 점 + "Claude 연결됨" 배지
// - 미연결(나중에 고름): 회색 배지 + "연결" 버튼
// 상태는 webview_preload.js 의 window.haehanLocal(main.js "local-config:claude-*")로 읽고 바꾼다.
// 웹(서버) 모드에는 haehanLocal 이 없으므로 아무것도 그리지 않는다.
// Claude Code 상태 확인은 `claude mcp get` 실행이라 화면을 열 때·창으로 돌아올 때·상태 변경 알림 때만 읽는다.

type SideStatus = { installed: boolean; connected: boolean };
type ClaudeStatus = { desktop: SideStatus; code: SideStatus; consented?: boolean; prompted?: boolean };
type ConnectResult = { ok: boolean; hint?: string; desktop?: { ok: boolean } | null; code?: { ok: boolean; skipped?: boolean } | null };
type ResultNotice = { title: string; ok: boolean; detail: string; hint: string };
type HaehanLocal = {
  getClaudeStatus?: () => Promise<ClaudeStatus>;
  connectClaude?: () => Promise<ConnectResult>;
  claudeLater?: () => Promise<{ ok: boolean }>;
  onClaudeStatusChanged?: (cb: (result: ResultNotice | null) => void) => () => void;
};

function localBridge(): HaehanLocal | undefined {
  return (window as unknown as { haehanLocal?: HaehanLocal }).haehanLocal;
}

function connectedSides(s: ClaudeStatus): string[] {
  const sides: string[] = [];
  if (s.desktop?.connected) sides.push("Claude Desktop");
  if (s.code?.connected) sides.push("Claude Code");
  return sides;
}

const NOTICE_MS = 6000;

export function ClaudeConnectionBadge() {
  const [status, setStatus] = useState<ClaudeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<ResultNotice | null>(null);
  const pathname = usePathname();

  const refresh = useCallback(() => {
    const bridge = localBridge();
    if (!bridge?.getClaudeStatus) return;
    bridge.getClaudeStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener("focus", refresh);
    const off = localBridge()?.onClaudeStatusChanged?.((result) => {
      if (result) setNotice(result);
      refresh();
    });
    return () => {
      window.removeEventListener("focus", refresh);
      off?.();
    };
  }, [refresh]);

  useEffect(() => {
    if (!notice?.ok) return;
    const t = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => window.clearTimeout(t);
  }, [notice]);

  // 첫 실행 등록 화면(/setup)에서는 가리지 않는다 — 이름·이메일 등록이 먼저다
  if (!status || pathname?.startsWith("/setup")) return null;

  const sides = connectedSides(status);
  const connected = sides.length > 0;
  const firstTime = !connected && !status.prompted;

  const connect = async () => {
    const bridge = localBridge();
    if (!bridge?.connectClaude || busy) return;
    setBusy(true);
    setNotice(null);
    try {
      const r = await bridge.connectClaude();
      setNotice(r.ok
        ? { title: "Claude 연결", ok: true, detail: "", hint: "" }
        : { title: "Claude 연결", ok: false, detail: "", hint: r.hint || "연결하지 못했습니다" });
    } catch {
      setNotice({ title: "Claude 연결", ok: false, detail: "", hint: "연결하지 못했습니다" });
    } finally {
      setBusy(false);
      refresh();
    }
  };

  const later = async () => {
    await localBridge()?.claudeLater?.().catch(() => undefined);
    refresh();
  };

  if (firstTime) {
    return (
      <div
        data-testid="claude-connect-card"
        role="dialog"
        aria-labelledby="claude-connect-title"
        className="fixed bottom-4 right-4 z-[200] w-80 rounded-xl border border-gray-200 bg-white p-4 text-sm shadow-lg"
      >
        <p id="claude-connect-title" className="font-semibold text-gray-900">Claude에서 Haehan AI 쓰기</p>
        <p className="mt-1 text-gray-600">
          이 PC의 Claude(Desktop·Code)에 Haehan AI 도구를 연결합니다. 다른 설정은 그대로 두고, 바꾸기 전에 백업을 남깁니다.
        </p>
        {notice && !notice.ok && <p role="alert" className="mt-2 text-red-600">{notice.hint}</p>}
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" onClick={later} disabled={busy} className="rounded-lg px-3 py-1.5 text-gray-600 hover:bg-gray-100 disabled:opacity-50">
            나중에
          </button>
          <button type="button" onClick={connect} disabled={busy} className="rounded-lg bg-orange-500 px-3 py-1.5 font-medium text-white hover:bg-orange-600 disabled:opacity-50">
            {busy ? "연결 중..." : "연결"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="claude-connection-badge"
      data-connected={connected ? "true" : "false"}
      className="fixed bottom-3 right-3 z-[200] flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs shadow-sm"
      title={connected ? `연결됨: ${sides.join(", ")}` : "Claude에서 Haehan AI 도구를 쓰려면 연결하세요"}
    >
      <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-gray-300"}`} />
      {connected ? (
        <span className="font-medium text-green-700">
          Claude 연결됨{notice?.ok ? ` · ${notice.detail || sides.join(" · ")}` : ""}
        </span>
      ) : (
        <>
          <span className="text-gray-500">Claude 미연결</span>
          <button
            type="button"
            onClick={connect}
            disabled={busy}
            className="rounded-full bg-orange-500 px-2 py-0.5 font-medium text-white disabled:opacity-50"
          >
            {busy ? "연결 중..." : "연결"}
          </button>
        </>
      )}
      {notice && !notice.ok && <span role="alert" className="text-red-600">{notice.hint}</span>}
    </div>
  );
}
