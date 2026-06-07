"use client";
import { KEYWORD_TOOLS } from "./constants";

export function ToolsTab() {
  return (
    <div className="space-y-3">
      <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl px-4 py-3 flex items-start gap-3">
        <span className="text-[#F97316] text-base mt-0.5">!</span>
        <div>
          <p className="text-xs font-bold text-[#C2410C]">외부 도구 이용 안내</p>
          <p className="text-xs text-[#78350F] mt-0.5">
            아래 도구들은 네이버 외부 사이트로 이동합니다. 네이버 계정 로그인이 필요할 수 있습니다.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {KEYWORD_TOOLS.map((tool) => (
          <div key={tool.key} className="border border-[#E5E7EB] rounded-xl p-4 bg-white flex flex-col gap-3">
            <div>
              <p className="text-sm font-bold text-[#111827]">{tool.label}</p>
              <p className="text-xs text-[#6B7280] mt-1">{tool.description}</p>
            </div>
            <a
              href={tool.href}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-auto inline-block px-4 py-2 bg-[#F97316] text-white text-xs font-semibold rounded-lg hover:bg-[#EA6C0A] transition-colors text-center"
            >
              바로가기
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
