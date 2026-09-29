"use client";
/**
 * HomePage — 단일 AI 작업 콘솔.
 *
 * 앱 = "AI에게 작업을 요청하는 콘솔 1개". 실제 작업(사이트 로그인·작성·수집·분석 등)은
 * CDP 브라우저에서 AI 에이전트가 수행하고, 진행·결과는 이 콘솔에 출력된다.
 * 복잡한 탭별 수동 UI는 숨김. (2026-09-30 정정: 예전 주석은 "코드/라우트 보존"이라 했으나 실제로는
 * 2026-09-23 대청소(docs/deleted_code_index.md)에서 대부분 삭제됨 — nav.ts의 구 NAV_GROUPS_ALL도
 * 그 죽은 참조만 들고 있어 같이 삭제함. 복원은 deleted_code_index.md의 git checkout 절차 참고.)
 */
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { PageShell } from "@/components/ui/PageShell";
import { getMe, type UserInfo } from "@/lib/userAuth";
import { UniversalChat } from "@/components/chat/UniversalChat";

export default function HomePage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const router = useRouter();

  useEffect(() => {
    getMe()
      .then((u) => { setUser(u); setAuthChecked(true); })
      .catch(() => { setAuthChecked(true); });
  }, []);

  useEffect(() => {
    if (authChecked && !user) router.replace("/about");
  }, [authChecked, user, router]);

  if (!authChecked || !user) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center">
        <div className="text-sm text-[#9CA3AF]">로딩 중...</div>
      </div>
    );
  }

  return (
    <PageShell title="Haehan AI 콘솔" description="AI에게 작업을 요청하세요 · 실제 작업은 브라우저(CDP)에서 수행됩니다">
      <div
        data-testid="ai-agent-console"
        className="h-[calc(100dvh-150px)] min-h-[460px]"
      >
        <UniversalChat domain="default" title="AI 작업 콘솔" className="h-full min-h-[300px]" />
      </div>
    </PageShell>
  );
}
