"use client";

import { ReactNode, useEffect } from "react";

interface ModalProps {
  open: boolean;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
}

export function Modal({ open, title, children, footer, onClose }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-[12px] shadow-xl w-full max-w-[480px] mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 h-[52px] border-b border-[#E5E7EB]">
          <span className="text-[14px] font-bold text-[#0F172A]">{title}</span>
          <button
            onClick={onClose}
            className="text-[#9CA3AF] hover:text-[#374151] text-[18px] leading-none transition-colors"
            aria-label="닫기"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 text-[13px] text-[#374151]">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex justify-end gap-2 px-5 py-3 border-t border-[#E5E7EB] bg-[#F9FAFB]">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
