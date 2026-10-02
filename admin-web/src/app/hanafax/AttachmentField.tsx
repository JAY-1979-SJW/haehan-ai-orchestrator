"use client";

import { useRef, useState } from "react";
import { faxApi, type AttachmentInfo } from "./api";

/**
 * 팩스 첨부 파일 입력 — ① 파일 선택·끌어놓기(앱 전용 폴더에 저장되고 경로가 자동으로 채워진다) ② 경로 직접 입력 + "경로 확인"(형식·크기·허용 폴더를 미리 검사).
 * 형식은 pdf/docx/doc, 10MB 이하. 올린 파일은 앱 폴더(커밋 제외)에 있고, 승인서가 참조하지 않는 30일 지난 업로드는 자동 정리된다.
 * `showCopy` 가 켜지면 "경로 복사" 버튼으로 AI 창에 경로를 붙여 넣어 알려 줄 수 있다.
 */
export function AttachmentField({
  value,
  onChange,
  showCopy = false,
}: {
  value: string;
  onChange: (path: string) => void;
  showCopy?: boolean;
}) {
  const [info, setInfo] = useState<AttachmentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [copied, setCopied] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const saved = await faxApi.uploadAttachment(file);
      setInfo(saved);
      onChange(saved.path);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      if (picker.current) picker.current.value = ""; // 같은 파일을 다시 골라도 동작하게
    }
  }

  async function check() {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const checked = await faxApi.checkAttachment(value.trim().replace(/^"|"$/g, ""));
      setInfo(checked);
      onChange(checked.path);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("복사하지 못했습니다 — 경로를 직접 선택해 복사하세요");
    }
  }

  return (
    <div className="space-y-1" data-testid="fax-attachment-field">
      <div
        className={`rounded border border-dashed p-2 text-center text-xs ${over ? "border-[#2563EB] bg-blue-50" : "border-[#9CA3AF] bg-gray-50"}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          void upload(e.dataTransfer.files?.[0]);
        }}
      >
        팩스로 보낼 파일을 여기로 끌어다 놓거나{" "}
        <button type="button" className="rounded border bg-white px-2 py-0.5 disabled:opacity-50" disabled={busy} onClick={() => picker.current?.click()}>
          {busy ? "처리 중…" : "파일 선택"}
        </button>
        <div className="mt-1 text-gray-500">PDF·Word(docx, doc) · 10MB 이하</div>
        <input ref={picker} type="file" accept=".pdf,.docx,.doc" className="hidden" onChange={(e) => void upload(e.target.files?.[0])} />
      </div>
      <div className="flex gap-1">
        <input
          className="w-full rounded border border-[#D1D5DB] px-2 py-1 text-sm"
          placeholder="또는 파일 경로를 직접 입력 (예: C:\Users\내이름\Documents\공문.pdf)"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setInfo(null);
            setError(null);
          }}
        />
        <button type="button" className="shrink-0 rounded border px-2 py-1 text-xs disabled:opacity-50" disabled={busy || !value.trim()} onClick={check}>
          경로 확인
        </button>
      </div>
      {info && (
        <div className="text-xs text-green-700">
          ✓ {info.name} · {info.size_text} — 첨부할 수 있습니다
          {showCopy && (
            <button type="button" className="ml-2 rounded border bg-white px-2 py-0.5 text-[#111827]" onClick={copy}>
              {copied ? "복사됨" : "경로 복사"}
            </button>
          )}
        </div>
      )}
      {showCopy && !info && value && (
        <button type="button" className="rounded border bg-white px-2 py-0.5 text-xs" onClick={copy}>
          {copied ? "복사됨" : "경로 복사"}
        </button>
      )}
      {error && <div className="text-xs text-red-600">{error}</div>}
    </div>
  );
}
