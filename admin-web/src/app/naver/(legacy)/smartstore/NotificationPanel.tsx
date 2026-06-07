"use client";
/**
 * SmartStore 우측 알림 패널
 * - 팝업 자동 승인, 자동 등록, 수집 완료 등 이벤트 실시간 표시
 * - 5초 폴링으로 서버 이벤트 자동 갱신
 * - 벨 아이콘 + 미읽음 뱃지
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { popupStatus, popupPollerStatus } from "@/lib/assistant/api";

interface NotifEvent {
  id: string;
  kind: "layer" | "banner" | "new_tab" | "new_window" | "register" | "collect" | "system";
  ts: string;
  title: string;
  body: string;
  read: boolean;
  meta?: Record<string, unknown>;
}

function kindStyle(kind: NotifEvent["kind"]): { dot: string; bg: string; icon: string } {
  switch (kind) {
    case "layer":    return { dot: "bg-[#16A34A]", bg: "bg-[#F0FDF4] border-[#BBF7D0]", icon: "✅" };
    case "banner":   return { dot: "bg-[#F97316]", bg: "bg-[#FFF7ED] border-[#FED7AA]", icon: "📢" };
    case "new_window": return { dot: "bg-[#DC2626]", bg: "bg-[#FEF2F2] border-[#FECACA]", icon: "🪟" };
    case "new_tab":  return { dot: "bg-[#6B7280]", bg: "bg-[#F9FAFB] border-[#E5E7EB]", icon: "📑" };
    case "register": return { dot: "bg-[#1D4ED8]", bg: "bg-[#EFF6FF] border-[#BFDBFE]", icon: "📦" };
    case "collect":  return { dot: "bg-[#7C3AED]", bg: "bg-[#F5F3FF] border-[#DDD6FE]", icon: "🔄" };
    default:         return { dot: "bg-[#9CA3AF]", bg: "bg-[#F9FAFB] border-[#E5E7EB]", icon: "ℹ️" };
  }
}

function kindLabel(kind: NotifEvent["kind"]): string {
  const m: Record<string, string> = {
    layer: "팝업 처리", banner: "배너 처리", new_window: "새 창",
    new_tab: "새 탭", register: "자동 등록", collect: "데이터 수집", system: "시스템",
  };
  return m[kind] ?? kind;
}

// 서버 이벤트 → NotifEvent 변환
function toNotif(raw: Record<string, unknown>, idx: number): NotifEvent {
  const kind = (raw.kind as NotifEvent["kind"]) ?? "system";
  const ts   = (raw.ts as string) ?? "";

  let title = kindLabel(kind);
  let body  = "";

  if (kind === "layer") {
    const approved  = (raw.approved  as string[]) ?? [];
    const dismissed = (raw.dismissed as string[]) ?? [];
    const closed    = (raw.closed    as number)   ?? 0;
    title = approved.length > 0 ? "팝업 자동 승인" : "팝업 읽음·닫기";
    // 팝업 상세 내용 (popups 배열에 full_text 포함)
    const popups = (raw.popups as Array<{ text: string; full_text?: string; buttons?: string[]; links?: string[]; action?: string }>) ?? [];
    const firstText = approved[0] || dismissed[0] || "";
    body = firstText
      ? `${approved.length > 0 ? "✅ 승인" : "✕ 닫기"} — ${firstText}`
      : `${closed}개 처리`;
  } else if (kind === "banner") {
    const closed = (raw.closed as number) ?? 0;
    body = `배너 ${closed}개 처리`;
  } else if (kind === "new_tab" || kind === "new_window") {
    const url = (raw.url as string) ?? "";
    body = url.length > 50 ? url.slice(-45) : url;
  } else if (kind === "register") {
    body = (raw.name as string) ?? "상품 등록 완료";
  } else if (kind === "collect") {
    body = (raw.note as string) ?? "수집 완료";
  }

  return {
    id:   `${ts}-${idx}`,
    kind,
    ts,
    title,
    body,
    read: false,
    meta: raw as Record<string, unknown>,
  };
}

export default function NotificationPanel() {
  const [open, setOpen]       = useState(false);
  const [notifs, setNotifs]   = useState<NotifEvent[]>([]);
  const [pollerRunning, setPollerRunning] = useState<boolean | null>(null);
  const prevIdsRef = useRef<Set<string>>(new Set());
  const panelRef   = useRef<HTMLDivElement>(null);

  const unread = notifs.filter(n => !n.read).length;

  // 패널 외부 클릭 시 닫기
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const fetchEvents = useCallback(async () => {
    try {
      const [statusRes, pollerRes] = await Promise.all([
        popupStatus(),
        popupPollerStatus(),
      ]);

      setPollerRunning(pollerRes.running ?? false);

      const raw = statusRes.recent_events ?? [];
      const incoming: NotifEvent[] = raw
        .map((e, i) => toNotif(e as Record<string, unknown>, i))
        .filter(n => n.kind !== "new_tab"); // 일반 탭 이벤트는 노이즈 제거

      // 새 이벤트만 추출 (id 기준)
      const newOnes = incoming.filter(n => !prevIdsRef.current.has(n.id));
      if (newOnes.length > 0) {
        prevIdsRef.current = new Set(incoming.map(n => n.id));
        setNotifs(prev => {
          const merged = [...newOnes.map(n => ({ ...n, read: false })),
                          ...prev.filter(p => !newOnes.some(n => n.id === p.id))];
          return merged.slice(0, 50); // 최대 50개 유지
        });
      } else if (prevIdsRef.current.size === 0 && incoming.length > 0) {
        // 첫 로드: 기존 이벤트는 읽음 처리
        prevIdsRef.current = new Set(incoming.map(n => n.id));
        setNotifs(incoming.map(n => ({ ...n, read: true })));
      }
    } catch { /* ignore */ }
  }, []);

  // 5초 폴링
  useEffect(() => {
    fetchEvents();
    const id = setInterval(fetchEvents, 5000);
    return () => clearInterval(id);
  }, [fetchEvents]);

  function markAllRead() {
    setNotifs(prev => prev.map(n => ({ ...n, read: true })));
  }

  function clearAll() {
    setNotifs([]);
    prevIdsRef.current = new Set();
  }

  return (
    <div className="relative" ref={panelRef}>
      {/* 벨 버튼 */}
      <button
        onClick={() => { setOpen(v => !v); if (!open) markAllRead(); }}
        className="relative p-2 rounded-lg hover:bg-[#F3F4F6] transition-colors"
        title="알림"
      >
        <svg className="w-5 h-5 text-[#6B7280]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 11-6 0m6 0H9" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-[#DC2626] text-white text-[10px] font-bold rounded-full flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
        {/* 폴러 동작 중 표시 */}
        {pollerRunning && (
          <span className="absolute bottom-0.5 right-0.5 w-2 h-2 bg-[#16A34A] rounded-full border border-white" title="실시간 감시 중" />
        )}
      </button>

      {/* 드롭다운 패널 */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-white rounded-xl border border-[#E5E7EB] shadow-lg z-50 overflow-hidden">
          {/* 헤더 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB]">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-[#111827]">알림</span>
              {pollerRunning !== null && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold border ${
                  pollerRunning
                    ? "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]"
                    : "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]"
                }`}>
                  {pollerRunning ? "🟢 감시중" : "⚪ 중지"}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {notifs.length > 0 && (
                <button onClick={clearAll}
                  className="text-[10px] text-[#9CA3AF] hover:text-[#6B7280] transition-colors">
                  전체 삭제
                </button>
              )}
            </div>
          </div>

          {/* 알림 목록 */}
          <div className="max-h-[400px] overflow-y-auto">
            {notifs.length === 0 ? (
              <div className="py-10 text-center">
                <p className="text-sm text-[#9CA3AF]">알림 없음</p>
                <p className="text-xs text-[#D1D5DB] mt-1">팝업 처리, 등록 완료 등이 여기에 표시됩니다</p>
              </div>
            ) : (
              notifs.map(n => {
                const { dot, bg, icon } = kindStyle(n.kind);
                return (
                  <div key={n.id}
                    className={`flex gap-3 px-4 py-3 border-b border-[#F3F4F6] last:border-0 transition-colors ${
                      n.read ? "bg-white" : "bg-[#FFFBEB]"
                    }`}
                  >
                    {/* 아이콘 + 읽음 점 */}
                    <div className="relative shrink-0 mt-0.5">
                      <span className="text-base">{icon}</span>
                      {!n.read && (
                        <span className={`absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full ${dot}`} />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${bg}`}>
                          {kindLabel(n.kind)}
                        </span>
                        <span className="text-[10px] text-[#9CA3AF] font-mono">{n.ts}</span>
                      </div>
                      <p className="text-xs font-semibold text-[#111827] mt-1">{n.title}</p>
                      {n.body && (
                        <p className="text-[11px] text-[#6B7280] mt-0.5">{n.body}</p>
                      )}
                      {/* 팝업 전체 내용 펼쳐보기 */}
                      {n.kind === "layer" && (() => {
                        const popups = (n.meta?.popups as Array<{
                          text: string; full_text?: string;
                          buttons?: string[]; links?: string[]; action?: string;
                        }>) ?? [];
                        if (!popups.length) return null;
                        return (
                          <details className="mt-1">
                            <summary className="text-[10px] text-[#9CA3AF] cursor-pointer hover:text-[#6B7280] select-none">
                              팝업 내용 보기 ({popups.length}개)
                            </summary>
                            <div className="mt-1 space-y-1.5">
                              {popups.map((p, i) => (
                                <div key={i} className="bg-[#F9FAFB] border border-[#E5E7EB] rounded p-2 text-[10px]">
                                  <div className="flex items-center gap-1 mb-1">
                                    <span className={`px-1 py-0.5 rounded text-[9px] font-semibold ${
                                      p.action === "confirm" ? "bg-[#F0FDF4] text-[#16A34A]" : "bg-[#F9FAFB] text-[#6B7280]"
                                    }`}>
                                      {p.action === "confirm" ? "✅ 승인" : p.action === "close" ? "✕ 닫기" : "ESC"}
                                    </span>
                                    {p.buttons && p.buttons.length > 0 && (
                                      <span className="text-[#9CA3AF]">버튼: {p.buttons.join(" · ")}</span>
                                    )}
                                  </div>
                                  <p className="text-[#374151] whitespace-pre-wrap leading-relaxed">
                                    {p.full_text || p.text}
                                  </p>
                                  {p.links && p.links.length > 0 && (
                                    <div className="mt-1 pt-1 border-t border-[#E5E7EB]">
                                      {p.links.map((l, j) => (
                                        <p key={j} className="text-[#6B7280] truncate">{l}</p>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </details>
                        );
                      })()}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* 푸터 */}
          <div className="px-4 py-2 border-t border-[#E5E7EB] bg-[#F9FAFB] flex items-center justify-between">
            <span className="text-[10px] text-[#9CA3AF]">총 {notifs.length}개</span>
            <button onClick={fetchEvents}
              className="text-[10px] text-[#6B7280] hover:text-[#374151] transition-colors">
              새로고침
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
