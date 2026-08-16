import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-[#F5F7FA]">
      <div className="rounded-2xl border border-[#E5E7EB] bg-white p-8 max-w-md w-full text-center shadow-sm">
        <div className="text-5xl font-bold text-[#F97316] mb-2">404</div>
        <h2 className="text-lg font-bold text-[#111827] mb-2">페이지를 찾을 수 없습니다</h2>
        <p className="text-sm text-[#6B7280] mb-6">요청한 페이지가 존재하지 않습니다.</p>
        <Link
          href="/"
          className="px-5 py-2 rounded-lg bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA6C0A] transition-colors"
        >
          홈으로
        </Link>
      </div>
    </div>
  );
}
