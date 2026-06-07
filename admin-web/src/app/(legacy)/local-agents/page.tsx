"use client";
import LocalAgentsClient from "./LocalAgentsClient";
import { PageShell } from "@/components/ui/PageShell";

export default function LocalAgentsPage() {
  return (
    <PageShell title="로컬 에이전트" description="로컬 에이전트 상태 · 관리" chatDomain="local-agents">
      <LocalAgentsClient />
    </PageShell>
  );
}
