"use client";
/** 메일함 — 작성 모달(폼→미리보기→완료) */
import { useState } from "react";
import { postNaverMailCompose } from "@/lib/assistant/mutations";
import type { MailComposeResponse } from "@/lib/assistant/mutations";
import type { ComposeStep } from "./inboxShared";

export function ComposeModal({ onClose }: { onClose: () => void }) {
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [step, setStep] = useState<ComposeStep>("form");
  const [preview, setPreview] = useState<MailComposeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [errMsg, setErrMsg] = useState("");

  const handlePreview = async () => {
    if (!to.trim()) { setErrMsg("수신인을 입력하세요."); return; }
    setBusy(true); setErrMsg("");
    try {
      const res = await postNaverMailCompose({ to, cc: cc || undefined, subject, body, dry_run: true });
      setPreview(res);
      setStep("preview");
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "오류");
    } finally {
      setBusy(false);
    }
  };

  const handleSend = async () => {
    setBusy(true); setErrMsg("");
    try {
      await postNaverMailCompose({ to, cc: cc || undefined, subject, body, dry_run: false });
      setStep("done");
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "전송 오류");
      setStep("error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5E7EB]">
          <h2 className="text-sm font-bold text-[#111827]">네이버 메일 쓰기</h2>
          <button onClick={onClose} className="text-[#6B7280] hover:text-[#111827] text-lg leading-none">×</button>
        </div>

        {step === "form" && (
          <div className="p-5 flex flex-col gap-3">
            <div>
              <label className="text-xs font-medium text-[#374151] block mb-1">수신인 *</label>
              <input value={to} onChange={(e) => setTo(e.target.value)}
                placeholder="example@naver.com"
                className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#3B82F6]" />
            </div>
            <div>
              <label className="text-xs font-medium text-[#374151] block mb-1">참조</label>
              <input value={cc} onChange={(e) => setCc(e.target.value)}
                placeholder="선택 입력"
                className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#3B82F6]" />
            </div>
            <div>
              <label className="text-xs font-medium text-[#374151] block mb-1">제목</label>
              <input value={subject} onChange={(e) => setSubject(e.target.value)}
                placeholder="메일 제목"
                className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#3B82F6]" />
            </div>
            <div>
              <label className="text-xs font-medium text-[#374151] block mb-1">본문</label>
              <textarea value={body} onChange={(e) => setBody(e.target.value)}
                rows={6} placeholder="메일 내용을 입력하세요"
                className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#3B82F6] resize-none" />
            </div>
            {errMsg && <p className="text-xs text-red-600">{errMsg}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button onClick={onClose} className="text-xs px-4 py-2 border border-[#E5E7EB] rounded text-[#374151] hover:bg-[#F3F4F6]">취소</button>
              <button onClick={handlePreview} disabled={busy}
                className="text-xs px-4 py-2 bg-[#F97316] text-white rounded hover:bg-[#EA580C] disabled:opacity-50">
                {busy ? "확인 중…" : "다음 — 내용 확인"}
              </button>
            </div>
          </div>
        )}

        {step === "preview" && preview && (
          <div className="p-5 flex flex-col gap-3">
            <div className="p-4 bg-[#F9FAFB] border border-[#E5E7EB] rounded-lg text-sm space-y-2">
              <div><span className="font-semibold text-[#374151]">수신인:</span> {preview.to}</div>
              {preview.cc && <div><span className="font-semibold text-[#374151]">참조:</span> {preview.cc}</div>}
              <div><span className="font-semibold text-[#374151]">제목:</span> {preview.subject}</div>
              <div><span className="font-semibold text-[#374151]">본문(앞100자):</span> {preview.body_preview}</div>
            </div>
            <div className="p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
              ⚠ 실제 네이버 메일이 발송됩니다. 수신인과 내용을 다시 확인하세요.
            </div>
            {errMsg && <p className="text-xs text-red-600">{errMsg}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setStep("form")} className="text-xs px-4 py-2 border border-[#E5E7EB] rounded text-[#374151] hover:bg-[#F3F4F6]">← 수정</button>
              <button onClick={handleSend} disabled={busy}
                className="text-xs px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50">
                {busy ? "발송 중…" : "발송 확인"}
              </button>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="p-8 text-center">
            <div className="text-2xl mb-2">✓</div>
            <p className="text-sm font-semibold text-[#15803D]">메일이 발송되었습니다.</p>
            <button onClick={onClose} className="mt-4 text-xs px-4 py-2 bg-[#F97316] text-white rounded hover:bg-[#EA580C]">닫기</button>
          </div>
        )}

        {step === "error" && (
          <div className="p-8 text-center">
            <p className="text-sm font-semibold text-red-700 mb-2">발송 실패</p>
            <p className="text-xs text-[#6B7280] mb-4">{errMsg}</p>
            <button onClick={() => setStep("form")} className="text-xs px-4 py-2 border border-[#E5E7EB] rounded text-[#374151] hover:bg-[#F3F4F6]">다시 시도</button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 메인 페이지 ──────────────────────────────────────────────────────────────
