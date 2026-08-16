"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-[#F5F7FA]">
      <div className="rounded-2xl border border-[#FCA5A5] bg-white p-8 max-w-md w-full text-center shadow-sm">
        <div className="text-4xl mb-4">⚠️</div>
        <h2 className="text-lg font-bold text-[#111827] mb-2">페이지 오류</h2>
        <p className="text-sm text-[#6B7280] mb-6">{error.message || "예기치 않은 오류가 발생했습니다."}</p>
        <button
          onClick={reset}
          className="px-5 py-2 rounded-lg bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA6C0A] transition-colors"
        >
          다시 시도
        </button>
      </div>
    </div>
  );
}
