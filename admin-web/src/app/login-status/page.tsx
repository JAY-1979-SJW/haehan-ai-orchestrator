"use client";
import { PageShell } from "@/components/ui/PageShell";
import SessionStatusPanel from "@/components/SessionStatusPanel";

export default function SessionStatusPage() {
  return (
    <PageShell title="로그인 세션 현황" description="지금 로그인돼 있는 사이트를 한눈에 확인합니다" chatDomain="admin">
      <SessionStatusPanel />
    </PageShell>
  );
}
