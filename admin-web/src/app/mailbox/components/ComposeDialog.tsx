"use client";

import { useRef, useState } from "react";
import { mailboxApi, type PreparedSend } from "../lib/api";
import { formatSize, type ComposeDraft } from "../lib/format";
import { RichEditor, type RichEditorHandle } from "./RichEditor";

interface Props {
  account: string;
  initial: ComposeDraft;
  onClose: () => void;
  onSent: (recipients: string[]) => void;
}

const MAX_FILES = 10;
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const MAX_TOTAL_BYTES = 25 * 1024 * 1024;
const BLOCKED = new Set(["exe", "bat", "cmd", "com", "scr", "pif", "msi", "msp", "dll", "sys", "lnk", "cpl", "js", "jse", "vbs", "vbe", "wsf", "wsh", "ps1", "psm1", "jar", "reg", "hta", "apk"]);

function fileProblem(file: File, current: File[]): string | null {
  if (file.name.toLowerCase().split(".").slice(1).some((p) => BLOCKED.has(p))) return `보낼 수 없는 형식입니다: ${file.name}`;
  if (file.size === 0) return `빈 파일입니다: ${file.name}`;
  if (file.size > MAX_FILE_BYTES) return `파일 하나는 20MB 이하여야 합니다: ${file.name}`;
  if (current.length >= MAX_FILES) return `첨부는 최대 ${MAX_FILES}개입니다`;
  if (current.reduce((s, f) => s + f.size, 0) + file.size > MAX_TOTAL_BYTES) return "첨부 합계는 25MB 이하여야 합니다";
  return null;
}

/**
 * 메일 쓰기 창. 입력창은 폼 너비를 가득 채우고, 본문(서식 편집기)은 남은 높이를 모두 차지한다(사용자 요청 2026-10-01).
 * "보내기" → 서버 검증(prepare) → 받는 사람·제목·첨부를 보여 주는 확인 창 → "전송"을 눌러야 실제로 나간다.
 */
export function ComposeDialog({ account, initial, onClose, onSent }: Props) {
  const [to, setTo] = useState(initial.to);
  const [cc, setCc] = useState(initial.cc);
  const [bcc, setBcc] = useState(initial.bcc);
  const [showCc, setShowCc] = useState(Boolean(initial.cc || initial.bcc));
  const [subject, setSubject] = useState(initial.subject);
  const [bodyEmpty, setBodyEmpty] = useState(true);
  const editor = useRef<RichEditorHandle>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [keepIdx, setKeepIdx] = useState<number[]>(initial.source?.attachments.map((a) => a.index) ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [prepared, setPrepared] = useState<PreparedSend | null>(null);
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  function addFiles(list: FileList | File[]) {
    let next = [...files];
    const problems: string[] = [];
    Array.from(list).forEach((f) => {
      const problem = fileProblem(f, next);
      if (problem) problems.push(problem);
      else next = [...next, f];
    });
    setFiles(next);
    setError(problems.length ? problems.join(" / ") : null);
  }

  async function prepare() {
    setBusy(true);
    setError(null);
    try {
      const forward = initial.source && keepIdx.length ? { folder: initial.source.folder, uid: initial.source.uid, indices: keepIdx } : null;
      setPrepared(await mailboxApi.prepareSend({ account, to, cc, bcc, subject, body: "", html: editor.current?.getHtml() ?? "", inReplyTo: initial.inReplyTo, references: initial.references, forward, files }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!prepared) return;
    setBusy(true);
    setError(null);
    try {
      const done = await mailboxApi.confirmSend(prepared.token);
      onSent(done.recipients);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPrepared(null);
    } finally {
      setBusy(false);
    }
  }

  async function backToEdit() {
    if (prepared) await mailboxApi.cancelSend(prepared.token).catch(() => undefined);
    setPrepared(null);
  }

  const field = "w-full min-w-0 rounded-lg border border-[#E5E7EB] px-3 py-[8px] text-[13px] outline-none focus:border-[#F97316]";
  const label = "w-16 shrink-0 text-[12px] text-[#6B7280]";
  const title = { new: "메일 쓰기", reply: "답장", replyAll: "전체답장", forward: "전달" }[initial.mode];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3" role="dialog" aria-label={title} aria-modal="true">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void prepare();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        className="relative flex h-[min(88vh,820px)] w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
      >
        <div className="flex h-[48px] shrink-0 items-center justify-between border-b border-[#E5E7EB] px-4">
          <span className="text-[14px] font-bold text-[#0F172A]">{title}</span>
          <button type="button" onClick={onClose} className="text-[20px] leading-none text-[#9CA3AF] hover:text-[#374151]" aria-label="닫기">×</button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-2 p-4">
          <div className="flex items-center gap-2">
            <span className={label}>받는 사람</span>
            <input aria-label="받는 사람" value={to} onChange={(e) => setTo(e.target.value)} placeholder="주소를 쉼표로 구분 (최대 20명)" className={field} />
            {!showCc && <button type="button" onClick={() => setShowCc(true)} className="shrink-0 text-[12px] text-[#6B7280] underline">참조/숨은참조</button>}
          </div>
          {showCc && (
            <>
              <div className="flex items-center gap-2"><span className={label}>참조</span><input aria-label="참조" value={cc} onChange={(e) => setCc(e.target.value)} className={field} /></div>
              <div className="flex items-center gap-2"><span className={label}>숨은참조</span><input aria-label="숨은참조" value={bcc} onChange={(e) => setBcc(e.target.value)} className={field} /></div>
            </>
          )}
          <div className="flex items-center gap-2">
            <span className={label}>제목</span>
            <input aria-label="제목" value={subject} onChange={(e) => setSubject(e.target.value)} className={field} />
          </div>

          {/* 본문: 서식 편집기 — 폼 너비 전체, 남은 높이를 모두 차지 */}
          <RichEditor ref={editor} initialHtml={initial.html} onEmptyChange={setBodyEmpty} />

          {initial.source && initial.source.attachments.length > 0 && (
            <div className="shrink-0 rounded-lg bg-[#FAFAFA] p-2 text-[12px]">
              <div className="mb-1 font-semibold text-[#374151]">원본 첨부 함께 전달</div>
              {initial.source.attachments.map((a) => (
                <label key={a.index} className="flex items-center gap-2 py-[2px]">
                  <input type="checkbox" checked={keepIdx.includes(a.index)} onChange={(e) => setKeepIdx(e.target.checked ? [...keepIdx, a.index] : keepIdx.filter((i) => i !== a.index))} />
                  <span className="min-w-0 flex-1 truncate">{a.filename}</span>
                  <span className="text-[#9CA3AF]">{formatSize(a.size)}</span>
                </label>
              ))}
            </div>
          )}

          <div className="shrink-0">
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => picker.current?.click()} className="rounded-lg border border-[#E5E7EB] px-3 py-[5px] text-[12px] text-[#374151] hover:bg-[#F9FAFB]">📎 파일 첨부</button>
              <span className="text-[11px] text-[#9CA3AF]">파일을 이 창으로 끌어 놓아도 됩니다 · 파일당 20MB, 합계 25MB, 최대 {MAX_FILES}개</span>
              <input ref={picker} type="file" multiple hidden onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
            </div>
            {files.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-2">
                {files.map((f, i) => (
                  <li key={`${f.name}-${i}`} className="flex items-center gap-1 rounded-full bg-[#F3F4F6] py-[3px] pl-3 pr-2 text-[12px]">
                    <span className="max-w-[220px] truncate">{f.name}</span>
                    <span className="text-[#9CA3AF]">{formatSize(f.size)}</span>
                    <button type="button" aria-label={`${f.name} 첨부 취소`} className="px-1 text-[#9CA3AF] hover:text-[#B91C1C]" onClick={() => setFiles(files.filter((_, k) => k !== i))}>×</button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {error && <p role="alert" className="shrink-0 text-[12px] text-[#B91C1C]">{error}</p>}
        </div>

        <div className="flex h-[56px] shrink-0 items-center justify-between border-t border-[#E5E7EB] px-4">
          <span className="text-[11px] text-[#9CA3AF]">보내는 계정: {account}@naver.com</span>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="rounded-xl border border-[#E5E7EB] px-4 py-[7px] text-[13px] text-[#374151] hover:bg-[#F9FAFB]">취소</button>
            <button type="submit" disabled={busy || !to.trim() || !subject.trim() || bodyEmpty} className="rounded-xl bg-[#F97316] px-5 py-[7px] text-[13px] font-semibold text-white hover:bg-[#EA580C] disabled:opacity-50">
              {busy && !prepared ? "확인 중…" : "보내기"}
            </button>
          </div>
        </div>

        {dragging && <div className="pointer-events-none absolute inset-0 flex items-center justify-center border-4 border-dashed border-[#F97316] bg-[#FFF7ED]/80 text-[15px] font-semibold text-[#C2410C]">여기에 놓으면 첨부됩니다</div>}

        {prepared && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40 p-4" role="alertdialog" aria-label="전송 확인">
            <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl">
              <h3 className="text-[15px] font-bold text-[#0F172A]">이 메일을 보낼까요?</h3>
              <dl className="mt-3 space-y-1 text-[13px]">
                <div className="flex gap-2"><dt className="w-16 shrink-0 text-[#9CA3AF]">보내는 사람</dt><dd>{prepared.summary.from}</dd></div>
                <div className="flex gap-2"><dt className="w-16 shrink-0 text-[#9CA3AF]">받는 사람</dt><dd className="break-words">{prepared.summary.to.join(", ")}</dd></div>
                {prepared.summary.cc.length > 0 && <div className="flex gap-2"><dt className="w-16 shrink-0 text-[#9CA3AF]">참조</dt><dd className="break-words">{prepared.summary.cc.join(", ")}</dd></div>}
                {prepared.summary.bcc.length > 0 && <div className="flex gap-2"><dt className="w-16 shrink-0 text-[#9CA3AF]">숨은참조</dt><dd className="break-words">{prepared.summary.bcc.join(", ")}</dd></div>}
                <div className="flex gap-2"><dt className="w-16 shrink-0 text-[#9CA3AF]">제목</dt><dd className="break-words font-semibold">{prepared.summary.subject}</dd></div>
                <div className="flex gap-2"><dt className="w-16 shrink-0 text-[#9CA3AF]">본문</dt><dd className="line-clamp-3 break-words text-[#4B5563]">{prepared.summary.body_preview}</dd></div>
                <div className="flex gap-2">
                  <dt className="w-16 shrink-0 text-[#9CA3AF]">첨부</dt>
                  <dd>{prepared.summary.attachments.length === 0 ? "없음" : prepared.summary.attachments.map((a) => `${a.filename} (${formatSize(a.size)})`).join(", ")}</dd>
                </div>
              </dl>
              {error && <p role="alert" className="mt-2 text-[12px] text-[#B91C1C]">{error}</p>}
              <div className="mt-4 flex justify-end gap-2">
                <button type="button" onClick={() => void backToEdit()} disabled={busy} className="rounded-xl border border-[#E5E7EB] px-4 py-[7px] text-[13px] text-[#374151] hover:bg-[#F9FAFB]">돌아가서 수정</button>
                <button type="button" onClick={() => void confirm()} disabled={busy} className="rounded-xl bg-[#F97316] px-5 py-[7px] text-[13px] font-semibold text-white hover:bg-[#EA580C] disabled:opacity-50">{busy ? "전송 중…" : "전송"}</button>
              </div>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
