"use client";
/**
 * LiveScreen — CDP 브라우저 라이브 화면.
 *
 * AI가 CDP에서 작업하는 실제 브라우저 화면을 ~1.2초마다 갱신해 보여준다.
 * fetch+blob 방식(Authorization 헤더 전달 가능, <img src>의 인증 한계 회피).
 * 204(미연결/탭없음)면 안내 표시.
 */
import { useState, useEffect, useRef } from "react";
import { API_BASE } from "@/lib/assistant/api";

const POLL_MS = 1200;

export function LiveScreen({ className = "" }: { className?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [alive, setAlive] = useState<boolean | null>(null); // null=확인중
  const [ts, setTs] = useState<string>("");

  useEffect(() => {
    let stop = false;
    let objUrl: string | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const getHeaders = () => {
      const tok = typeof window !== "undefined" ? localStorage.getItem("haehan_ai_token") : null;
      return tok ? { Authorization: `Bearer ${tok}` } : {};
    };

    // 초기 연결 상태를 screenshot 폴링 전에 /cdp/status로 빠르게 확인
    fetch(`${API_BASE}/api/v1/cdp/status`, { cache: "no-store", headers: getHeaders() })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (!stop && d) setAlive(!!d.connected); })
      .catch(() => {});

    const tick = async () => {
      try {
        const r = await fetch(`${API_BASE}/api/v1/cdp/screen.jpg`, {
          cache: "no-store",
          headers: getHeaders(),
        });
        if (r.status === 200) {
          const blob = await r.blob();
          if (!stop) {
            if (objUrl) URL.revokeObjectURL(objUrl);
            objUrl = URL.createObjectURL(blob);
            setSrc(objUrl);
            setAlive(true);
            setTs(new Date().toLocaleTimeString("ko-KR"));
          }
        } else if (!stop) {
          setAlive(false);
        }
      } catch {
        if (!stop) setAlive(false);
      }
      if (!stop) timer = setTimeout(tick, POLL_MS);
    };
    tick();

    return () => {
      stop = true;
      if (timer) clearTimeout(timer);
      if (objUrl) URL.revokeObjectURL(objUrl);
    };
  }, []);

  return (
    <div className={`flex flex-col bg-[#0F172A] border border-[#E5E7EB] rounded-2xl overflow-hidden ${className}`}>
      <div className="px-3 h-[44px] flex items-center justify-between shrink-0 bg-[#111827] border-b border-[#1F2937]">
        <span className="text-xs font-bold text-[#E5E7EB]">🖥 실제 작업 화면 (CDP)</span>
        <span className="text-[10px] text-[#9CA3AF]">
          {alive === false ? "● 미연결" : alive ? `● 라이브 ${ts}` : "● 연결 중…"}
        </span>
      </div>
      <div className="flex-1 min-h-0 flex items-center justify-center overflow-hidden">
        {src && alive ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt="CDP 라이브 화면" className="max-w-full max-h-full object-contain" />
        ) : (
          <div className="text-center px-6">
            <p className="text-sm text-[#9CA3AF]">
              {alive === false ? "CDP 브라우저가 연결되지 않았습니다." : "화면을 불러오는 중…"}
            </p>
            <p className="text-[11px] text-[#6B7280] mt-1">
              AI에게 작업을 요청하면 브라우저가 자동으로 뜨고, 여기에서 작업 화면이 실시간으로 보입니다.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
