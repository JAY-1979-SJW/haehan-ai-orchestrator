"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

export interface RichEditorHandle {
  /** 편집기의 현재 HTML — 서버가 보내기 전에 한 번 더 정제한다. */
  getHtml: () => string;
}

interface Props {
  /** 초기 HTML. 반드시 서버가 정제한 인용문(quote_html)이거나 앱이 직접 만든 마크업이어야 한다. */
  initialHtml: string;
  onEmptyChange: (empty: boolean) => void;
}

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];
const FONT_SIZES: { label: string; value: string }[] = [
  { label: "작게", value: "2" },
  { label: "보통", value: "3" },
  { label: "크게", value: "4" },
  { label: "더 크게", value: "5" },
  { label: "아주 크게", value: "6" },
];

// Tailwind 의 기본 초기화가 목록·인용 모양을 없애므로 편집 영역 안에서만 되살린다
const EDITOR_CSS = `
.mail-editor ul{list-style:disc;padding-left:1.6em;margin:.3em 0}
.mail-editor ol{list-style:decimal;padding-left:1.6em;margin:.3em 0}
.mail-editor blockquote{margin:.5em 0;padding-left:12px;border-left:3px solid #e5e7eb;color:#4b5563}
.mail-editor a{color:#2563eb;text-decoration:underline}
.mail-editor img{max-width:100%;height:auto}
.mail-editor hr{border:0;border-top:1px solid #d1d5db;margin:.8em 0}
.mail-editor h1,.mail-editor h2,.mail-editor h3{font-weight:700;margin:.4em 0}
`;

function isEmptyDom(root: HTMLElement): boolean {
  return !root.innerText.replace(/​/g, "").trim() && !root.querySelector("img,hr");
}

export const RichEditor = forwardRef<RichEditorHandle, Props>(function RichEditor({ initialHtml, onEmptyChange }, ref) {
  const editor = useRef<HTMLDivElement>(null);
  const imagePicker = useRef<HTMLInputElement>(null);
  const saved = useRef<Range | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("https://");
  const [error, setError] = useState<string | null>(null);

  useImperativeHandle(ref, () => ({ getHtml: () => editor.current?.innerHTML ?? "" }));

  useEffect(() => {
    const el = editor.current;
    if (!el) return;
    el.innerHTML = initialHtml || "<div><br></div>";
    document.execCommand("styleWithCSS", false, "true");
    onEmptyChange(isEmptyDom(el));
    // 답장이면 인용문 위(맨 앞)에서 쓰기 시작한다
    el.focus();
    const range = document.createRange();
    range.setStart(el, 0);
    range.collapse(true);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
    // 초기 HTML 은 한 번만 넣는다(이후 입력은 편집기가 가진다)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const notify = useCallback(() => {
    if (editor.current) onEmptyChange(isEmptyDom(editor.current));
  }, [onEmptyChange]);

  function remember() {
    const sel = window.getSelection();
    if (sel && sel.rangeCount && editor.current?.contains(sel.anchorNode)) saved.current = sel.getRangeAt(0).cloneRange();
  }

  function restore() {
    editor.current?.focus();
    const sel = window.getSelection();
    if (saved.current && sel) {
      sel.removeAllRanges();
      sel.addRange(saved.current);
    }
  }

  function exec(cmd: string, value?: string) {
    editor.current?.focus();
    document.execCommand(cmd, false, value);
    notify();
  }

  function insertImageFile(file: File) {
    if (!IMAGE_TYPES.includes(file.type)) return setError("PNG·JPEG·GIF·WEBP 이미지만 넣을 수 있습니다");
    if (file.size > MAX_IMAGE_BYTES) return setError("이미지 하나는 5MB 이하여야 합니다");
    setError(null);
    const reader = new FileReader();
    reader.onload = () => {
      restore();
      document.execCommand("insertImage", false, String(reader.result));
      notify();
    };
    reader.readAsDataURL(file);
  }

  function applyLink() {
    let url = linkUrl.trim();
    if (!url) return setLinkOpen(false);
    if (!/^(https?:\/\/|mailto:)/i.test(url)) url = `https://${url}`;
    restore();
    document.execCommand("createLink", false, url);
    setLinkOpen(false);
    setLinkUrl("https://");
    notify();
  }

  const tool = "flex h-7 min-w-7 items-center justify-center rounded px-[6px] text-[13px] text-[#374151] hover:bg-[#F3F4F6]";
  // 눌러도 편집 영역의 선택이 풀리지 않게 한다
  const keep = (e: React.MouseEvent) => e.preventDefault();
  const sep = <span aria-hidden="true" className="mx-1 h-5 w-px bg-[#E5E7EB]" />;

  return (
    <div className="flex min-h-[160px] w-full flex-1 flex-col overflow-hidden rounded-lg border border-[#E5E7EB] focus-within:border-[#F97316]">
      <style>{EDITOR_CSS}</style>
      <div role="toolbar" aria-label="서식 도구" className="flex shrink-0 flex-wrap items-center gap-[2px] border-b border-[#E5E7EB] bg-[#FAFAFA] px-2 py-1">
        <select
          aria-label="글자 크기"
          defaultValue="3"
          onChange={(e) => exec("fontSize", e.target.value)}
          className="h-7 rounded border border-[#E5E7EB] bg-white px-1 text-[12px]"
        >
          {FONT_SIZES.map((f) => (
            <option key={f.value} value={f.value}>{f.label}</option>
          ))}
        </select>
        {sep}
        <button type="button" title="굵게" aria-label="굵게" className={`${tool} font-bold`} onMouseDown={keep} onClick={() => exec("bold")}>B</button>
        <button type="button" title="기울임" aria-label="기울임" className={`${tool} italic`} onMouseDown={keep} onClick={() => exec("italic")}>I</button>
        <button type="button" title="밑줄" aria-label="밑줄" className={`${tool} underline`} onMouseDown={keep} onClick={() => exec("underline")}>U</button>
        <button type="button" title="취소선" aria-label="취소선" className={`${tool} line-through`} onMouseDown={keep} onClick={() => exec("strikeThrough")}>S</button>
        <label title="글자 색" className={`${tool} cursor-pointer gap-1`} onMouseDown={remember}>
          <span className="font-bold underline decoration-[#F97316] decoration-2">A</span>
          <input type="color" aria-label="글자 색" defaultValue="#000000" className="h-0 w-0 opacity-0" onChange={(e) => { restore(); exec("foreColor", e.target.value); }} />
        </label>
        <label title="배경 색" className={`${tool} cursor-pointer gap-1`} onMouseDown={remember}>
          <span className="rounded bg-[#FEF08A] px-[3px] font-bold">A</span>
          <input type="color" aria-label="배경 색" defaultValue="#fef08a" className="h-0 w-0 opacity-0" onChange={(e) => { restore(); exec("hiliteColor", e.target.value); }} />
        </label>
        {sep}
        <button type="button" title="왼쪽 정렬" aria-label="왼쪽 정렬" className={tool} onMouseDown={keep} onClick={() => exec("justifyLeft")}>⯇</button>
        <button type="button" title="가운데 정렬" aria-label="가운데 정렬" className={tool} onMouseDown={keep} onClick={() => exec("justifyCenter")}>≡</button>
        <button type="button" title="오른쪽 정렬" aria-label="오른쪽 정렬" className={tool} onMouseDown={keep} onClick={() => exec("justifyRight")}>⯈</button>
        {sep}
        <button type="button" title="글머리 목록" aria-label="글머리 목록" className={tool} onMouseDown={keep} onClick={() => exec("insertUnorderedList")}>• ≡</button>
        <button type="button" title="번호 목록" aria-label="번호 목록" className={tool} onMouseDown={keep} onClick={() => exec("insertOrderedList")}>1.≡</button>
        <button type="button" title="내어쓰기" aria-label="내어쓰기" className={tool} onMouseDown={keep} onClick={() => exec("outdent")}>⇤</button>
        <button type="button" title="들여쓰기" aria-label="들여쓰기" className={tool} onMouseDown={keep} onClick={() => exec("indent")}>⇥</button>
        <button type="button" title="인용" aria-label="인용" className={tool} onMouseDown={keep} onClick={() => exec("formatBlock", "blockquote")}>❝</button>
        {sep}
        <button type="button" title="링크" aria-label="링크" className={tool} onMouseDown={() => remember()} onClick={() => setLinkOpen((v) => !v)}>🔗</button>
        <button type="button" title="이미지 넣기" aria-label="이미지 넣기" className={tool} onMouseDown={() => remember()} onClick={() => imagePicker.current?.click()}>🖼</button>
        <button type="button" title="구분선" aria-label="구분선" className={tool} onMouseDown={keep} onClick={() => exec("insertHorizontalRule")}>―</button>
        {sep}
        <button type="button" title="서식 지우기" aria-label="서식 지우기" className={tool} onMouseDown={keep} onClick={() => exec("removeFormat")}>Tx</button>
        <button type="button" title="실행 취소" aria-label="실행 취소" className={tool} onMouseDown={keep} onClick={() => exec("undo")}>↶</button>
        <button type="button" title="다시 실행" aria-label="다시 실행" className={tool} onMouseDown={keep} onClick={() => exec("redo")}>↷</button>
        <input
          ref={imagePicker}
          type="file"
          accept={IMAGE_TYPES.join(",")}
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) insertImageFile(f);
            e.target.value = "";
          }}
        />
      </div>

      {linkOpen && (
        <div className="flex shrink-0 items-center gap-2 border-b border-[#E5E7EB] bg-white px-2 py-1">
          <input
            aria-label="링크 주소"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                applyLink();
              }
            }}
            className="min-w-0 flex-1 rounded border border-[#E5E7EB] px-2 py-[3px] text-[12px] outline-none focus:border-[#F97316]"
          />
          <button type="button" onClick={applyLink} className="rounded bg-[#F97316] px-3 py-[3px] text-[12px] text-white">적용</button>
          <button type="button" onClick={() => setLinkOpen(false)} className="text-[12px] text-[#6B7280]">닫기</button>
        </div>
      )}

      {/* 본문 편집 영역 — 남은 높이를 모두 차지한다 */}
      <div
        ref={editor}
        role="textbox"
        aria-multiline="true"
        aria-label="본문"
        contentEditable
        suppressContentEditableWarning
        onInput={notify}
        onKeyUp={remember}
        onMouseUp={remember}
        onBlur={remember}
        onPaste={(e) => {
          const file = Array.from(e.clipboardData.files).find((f) => IMAGE_TYPES.includes(f.type));
          if (file) {
            e.preventDefault();
            insertImageFile(file);
          }
        }}
        className="mail-editor min-h-0 w-full flex-1 overflow-y-auto break-words p-3 text-[14px] leading-relaxed text-[#111827] outline-none"
      />
      {error && <p role="alert" className="shrink-0 border-t border-[#FEE2E2] bg-[#FEF2F2] px-3 py-1 text-[12px] text-[#B91C1C]">{error}</p>}
    </div>
  );
});
