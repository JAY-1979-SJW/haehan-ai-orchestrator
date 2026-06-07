"use client";
/**
 * BlogClient — 네이버 블로그 (thin 패턴)
 *
 * 앱은 "지시창 + 결과 패널"만 제공한다. 실제 작업(제목·본문·태그 생성, 네이버 글쓰기,
 * SEO 분석 등)은 CDP 브라우저에서 AI 에이전트(free_agent)가 수행하고, 결과만 여기에 표시된다.
 * 과거의 수동 에디터(제목/본문/태그/미디어 폼)는 제거됨 — 자연어 지시로 통일.
 *
 * 백엔드: 메시지 → /api/chat → /api/v1/agent-ai/chat → free_agent(CDP). 블로그 관련
 * 자연어는 _needs_agent 가 잡아 자동으로 브라우저 에이전트로 라우팅된다.
 * 외부 발행은 위험 동작이라 확인 후 진행(서버 정책).
 */
import { UniversalChat } from "@/components/chat/UniversalChat";

export default function BlogClient() {
  return (
    <div className="space-y-4">
      {/* 정책 안내 */}
      <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl px-4 py-3 flex items-start gap-3">
        <span className="text-[#F97316] text-base mt-0.5">!</span>
        <div>
          <p className="text-xs font-bold text-[#C2410C]">AI가 CDP 브라우저에서 직접 작성합니다</p>
          <p className="text-xs text-[#78350F] mt-0.5">
            주제·지시만 입력하면 AI가 제목·본문·태그를 생성해 네이버 블로그에 작성합니다.
            생성·임시저장은 자동, <b>외부 발행은 확인 후</b> 진행됩니다. 진행 상황과 결과는 아래에 표시됩니다.
          </p>
        </div>
      </div>

      {/* 지시창 + 결과 패널 (작업은 CDP에서 수행) */}
      <UniversalChat
        domain="blog"
        title="네이버 블로그 AI"
        className="h-[calc(100vh-220px)] min-h-[420px]"
      />
    </div>
  );
}
