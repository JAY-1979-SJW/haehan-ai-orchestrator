"use client";

import { useEffect, useState } from "react";
import { faxApi, type PreviewStatus } from "@/app/hanafax/api";

/**
 * 하나팩스 실제 접수 화면 미리보기 — 수신번호·제목·첨부를 사이트 화면에 채운 스크린샷(전송하지 않음).
 * 보기는 사용자의 선택이다(버튼을 눌러야 만든다). 승인에는 필요하지 않다.
 */
export function FaxSitePreview({ authId }: { authId: string }) {
  const [status, setStatus] = useState<PreviewStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [popup, setPopup] = useState(false);

  useEffect(() => {
    if (!open || !status?.running) return;
    const t = setInterval(async () => {
      try {
        setStatus(await faxApi.previewStatus(authId));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }, 3000);
    return () => clearInterval(t);
  }, [open, status?.running, authId]);

  async function make() {
    setOpen(true);
    setError(null);
    try {
      setStatus(await faxApi.startPreview(authId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const state = status?.state;
  return (
    <div className="space-y-1" data-testid="fax-site-preview">
      <button className="text-[#2563EB] underline" onClick={open ? () => setOpen(false) : make}>
        {open ? "하나팩스 화면 접기" : "하나팩스 실제 화면으로 보기 (선택)"}
      </button>
      {open && (
        <div className="space-y-1 rounded bg-gray-50 p-2">
          {status?.running && <div>하나팩스에 로그인해 화면을 채우는 중… (30~60초, 전송하지 않습니다)</div>}
          {error && <div className="text-red-600">{error}</div>}
          {state && !state.ok && <div className="text-red-600">{state.message}</div>}
          {state?.ok && (
            <>
              <div>
                {state.message}
                {state.total && state.shown && state.total > state.shown
                  ? ` · 수신 ${state.total}곳 중 처음 ${state.shown}곳만 화면에 채웠습니다`
                  : ""}
                {state.missing && state.missing.length > 0 ? ` · 사이트가 받아들이지 않은 번호 ${state.missing.length}건` : ""}
              </div>
              {status?.image_ready && (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={faxApi.previewImageUrl(authId, state.finished_at)}
                    alt="하나팩스 접수 화면 미리보기 (누르면 실제 크기로 팝업)"
                    title="누르면 실제 사이트 크기로 팝업"
                    onClick={() => setPopup(true)}
                    className="max-h-[420px] w-full cursor-zoom-in overflow-auto rounded border object-contain object-top"
                  />
                  <button className="text-[#2563EB] underline" onClick={() => setPopup(true)}>
                    실제 크기로 크게 보기
                  </button>
                  {popup && (
                    <PreviewPopup
                      src={faxApi.previewImageUrl(authId, state.finished_at)}
                      onClose={() => setPopup(false)}
                    />
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** 실제 사이트 크기(원본 픽셀) 팝업 — 안에서 스크롤. 바깥 클릭·ESC·닫기 버튼으로 닫는다. 화면 맞춤 전환 가능. */
function PreviewPopup({ src, onClose }: { src: string; onClose: () => void }) {
  const [fit, setFit] = useState(false); // 기본은 원래 크기

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[1000] flex flex-col bg-black/70 p-3"
      role="dialog"
      aria-label="하나팩스 접수 화면 미리보기"
      onClick={onClose}
      data-testid="fax-preview-popup"
    >
      <div className="mb-2 flex items-center justify-end gap-2 text-[12px]" onClick={(e) => e.stopPropagation()}>
        <button className="rounded bg-white px-3 py-1" onClick={() => setFit((v) => !v)}>
          {fit ? "원래 크기" : "화면 맞춤"}
        </button>
        <button className="rounded bg-white px-3 py-1" onClick={onClose}>
          닫기 (Esc)
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto rounded bg-white" onClick={(e) => e.stopPropagation()}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="하나팩스 접수 화면" className={fit ? "mx-auto h-auto max-w-full" : "mx-auto h-auto max-w-none"} />
      </div>
    </div>
  );
}
