"use client";

import { useEffect, useMemo, useState } from "react";
import { mailboxApi, type AttachmentInfo, type MessageDetail } from "../lib/api";
import { displayAddress, formatFullDate, formatSize } from "../lib/format";
import type { Folder, MessageRow } from "../lib/api";
import { MoveMenu } from "./MoveMenu";

interface Props {
  account: string;
  /** 본문을 받는 동안 목록 정보로 먼저 보여 줄 헤더(클릭 즉시 반응하도록) */
  pending: MessageRow | null;
  detail: MessageDetail | null;
  loading: boolean;
  error: string | null;
  inTrash: boolean;
  folders: Folder[];
  onMove: (dest: Folder) => void;
  onReply: () => void;
  onReplyAll: () => void;
  onForward: () => void;
  onTrash: () => void;
  onToggleSeen: () => void;
}

/** 본문 HTML 은 스크립트·외부 리소스를 막은 격리 iframe 안에서만 보여 준다(앱 화면에 직접 넣지 않는다). */
function buildSrcDoc(html: string, allowRemoteImages: boolean): string {
  // 스크립트·프레임·폼·연결은 항상 막고, 이미지만 선택적으로 연다
  const img = allowRemoteImages ? "data: https: http:" : "data:";
  const csp = `default-src 'none'; img-src ${img}; style-src 'unsafe-inline'; font-src data:`;
  return `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${csp}"><base target="_blank"><style>body{font:14px/1.6 -apple-system,'Malgun Gothic',sans-serif;color:#111827;margin:12px;word-break:break-word}img{max-width:100%;height:auto}</style>${html}`;
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

type Preview = { name: string; kind: "image" | "pdf" | "text"; url: string; text?: string };

const IMAGE_PREF_KEY = "mailbox.showRemoteImages";

function readImagePref(): boolean {
  try {
    return window.localStorage.getItem(IMAGE_PREF_KEY) !== "0"; // 기본: 표시(네이버 메일과 같음)
  } catch {
    return true;
  }
}

export function MessageView({ account, pending, detail, loading, error, inTrash, folders, onMove, onReply, onReplyAll, onForward, onTrash, onToggleSeen }: Props) {
  const [allowImages, setAllowImages] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => {
    setAllowImages(readImagePref());
  }, []);

  useEffect(() => {
    setAttachError(null);
  }, [detail?.uid, detail?.folder]);

  function toggleImages(next: boolean) {
    setAllowImages(next);
    try {
      window.localStorage.setItem(IMAGE_PREF_KEY, next ? "1" : "0");
    } catch {
      /* 저장할 수 없어도 이번 화면에서는 바뀐다 */
    }
  }

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview.url);
    };
  }, [preview]);

  const srcDoc = useMemo(() => (detail?.html ? buildSrcDoc(detail.html, allowImages) : ""), [detail?.html, allowImages]);

  if (error) return <div className="p-6 text-[13px] text-[#B91C1C]">{error}</div>;
  if (loading && !detail) {
    // 본문이 오기 전에도 제목·보낸 사람·날짜는 목록 정보로 바로 보여 준다
    return (
      <article aria-label="메일 읽기" aria-busy="true" className="flex h-full min-h-0 flex-col bg-white">
        <header className="shrink-0 space-y-2 border-b border-[#F3F4F6] p-4">
          <h2 className="text-[16px] font-bold leading-snug text-[#0F172A]">{pending?.subject || (pending ? "(제목 없음)" : "")}</h2>
          {pending && (
            <p className="text-[12px] text-[#4B5563]">
              {displayAddress(pending.from)} · {formatFullDate(pending.date_iso, pending.date)}
            </p>
          )}
        </header>
        <div role="status" className="p-4 text-[13px] text-[#F97316]">본문 불러오는 중…</div>
      </article>
    );
  }
  if (!detail) return <div className="flex h-full items-center justify-center text-[13px] text-[#9CA3AF]">읽을 메일을 선택하세요</div>;

  async function download(a: AttachmentInfo) {
    if (!detail) return;
    setBusy(a.index);
    setAttachError(null);
    try {
      saveBlob(await mailboxApi.attachment(account, detail.folder, detail.uid, a.index, false), a.filename);
    } catch (e) {
      setAttachError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function openPreview(a: AttachmentInfo) {
    if (!detail) return;
    setBusy(a.index);
    setAttachError(null);
    try {
      const blob = await mailboxApi.attachment(account, detail.folder, detail.uid, a.index, true);
      const url = URL.createObjectURL(blob);
      if (a.content_type.startsWith("image/")) setPreview({ name: a.filename, kind: "image", url });
      else if (a.content_type === "application/pdf") setPreview({ name: a.filename, kind: "pdf", url });
      else setPreview({ name: a.filename, kind: "text", url, text: (await blob.text()).slice(0, 200_000) });
    } catch (e) {
      setAttachError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const btn = "rounded-lg border border-[#E5E7EB] bg-white px-3 py-[5px] text-[12px] text-[#374151] transition-colors hover:bg-[#F9FAFB]";

  return (
    <article aria-label="메일 읽기" className="flex h-full min-h-0 flex-col bg-white">
      <header className="shrink-0 space-y-2 border-b border-[#F3F4F6] p-4">
        <h2 className="text-[16px] font-bold leading-snug text-[#0F172A]">{detail.subject || "(제목 없음)"}</h2>
        <dl className="space-y-[2px] text-[12px] text-[#4B5563]">
          <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">보낸 사람</dt><dd className="min-w-0 break-words">{displayAddress(detail.from)}</dd></div>
          <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">받는 사람</dt><dd className="min-w-0 break-words">{detail.to.map(displayAddress).join(", ")}</dd></div>
          {detail.cc.length > 0 && <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">참조</dt><dd className="min-w-0 break-words">{detail.cc.map(displayAddress).join(", ")}</dd></div>}
          <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">날짜</dt><dd>{formatFullDate(detail.date_iso, detail.date)}</dd></div>
        </dl>
        <div className="flex flex-wrap gap-2 pt-1">
          <button type="button" className={btn} onClick={onReply}>↩ 답장</button>
          <button type="button" className={btn} onClick={onReplyAll}>↩↩ 전체답장</button>
          <button type="button" className={btn} onClick={onForward}>➡ 전달</button>
          <button type="button" className={btn} onClick={onToggleSeen}>{detail.seen ? "안 읽음으로 표시" : "읽음으로 표시"}</button>
          <button type="button" className={`${btn} text-[#B91C1C]`} onClick={onTrash} disabled={inTrash} title={inTrash ? "휴지통의 메일은 목록에서 선택해 '영구 삭제'하세요" : "휴지통으로 이동"}>🗑 삭제</button>
          <MoveMenu folders={folders} currentId={detail.folder} onPick={onMove} />
        </div>
      </header>

      {detail.attachments.length > 0 && (
        <section aria-label="첨부 파일" className="shrink-0 border-b border-[#F3F4F6] bg-[#FAFAFA] px-4 py-3">
          <div className="mb-2 text-[12px] font-semibold text-[#374151]">📎 첨부 파일 {detail.attachments.length}개</div>
          <ul className="space-y-1">
            {detail.attachments.map((a) => (
              <li key={a.index} className="flex items-center gap-2 text-[12px]">
                <span className="min-w-0 flex-1 truncate text-[#111827]" title={a.filename}>{a.filename}</span>
                <span className="shrink-0 text-[#9CA3AF]">{formatSize(a.size)}</span>
                {a.previewable && (
                  <button type="button" className={btn} disabled={busy === a.index} onClick={() => openPreview(a)}>미리보기</button>
                )}
                <button type="button" className={btn} disabled={busy === a.index} onClick={() => download(a)}>
                  {busy === a.index ? "받는 중…" : "다운로드"}
                </button>
              </li>
            ))}
          </ul>
          {attachError && <p className="mt-2 text-[12px] text-[#B91C1C]">{attachError}</p>}
        </section>
      )}

      <div className="relative min-h-0 flex-1">
        {detail.html ? (
          <>
            {/<img\b/i.test(detail.html) && (
              <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between gap-2 bg-[#F9FAFB] px-4 py-[3px] text-[11px] text-[#6B7280]">
                <span>{allowImages ? "외부 이미지를 표시하고 있습니다." : "외부 이미지가 차단되었습니다."}</span>
                <button type="button" className="underline" onClick={() => toggleImages(!allowImages)}>{allowImages ? "이미지 차단" : "이미지 표시"}</button>
              </div>
            )}
            <iframe title="메일 본문" sandbox="allow-popups allow-popups-to-escape-sandbox" srcDoc={srcDoc} className="h-full w-full border-0 pt-6" />
          </>
        ) : (
          <pre className="h-full overflow-y-auto whitespace-pre-wrap break-words p-4 font-sans text-[14px] leading-relaxed text-[#111827]">{detail.text || "(본문 없음)"}</pre>
        )}
      </div>

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-label={`${preview.name} 미리보기`} onClick={() => setPreview(null)}>
          <div className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex h-[48px] shrink-0 items-center justify-between border-b border-[#E5E7EB] px-4">
              <span className="truncate text-[13px] font-semibold">{preview.name}</span>
              <button type="button" className="text-[20px] leading-none text-[#9CA3AF] hover:text-[#374151]" aria-label="닫기" onClick={() => setPreview(null)}>×</button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto bg-[#F3F4F6]">
              {preview.kind === "image" && (
                // blob 주소라 next/image 를 쓸 수 없다
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview.url} alt={preview.name} className="mx-auto max-h-[78vh] max-w-full object-contain" />
              )}
              {preview.kind === "pdf" && <iframe title={preview.name} src={preview.url} className="h-[78vh] w-full border-0 bg-white" />}
              {preview.kind === "text" && <pre className="whitespace-pre-wrap break-words bg-white p-4 text-[13px]">{preview.text}</pre>}
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
