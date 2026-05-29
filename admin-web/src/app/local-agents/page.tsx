"use client";
import LocalAgentsClient from "./LocalAgentsClient";
import { PageShell } from "@/components/ui/PageShell";

export default function LocalAgentsPage() {
  return (
    <PageShell title="Local Agents" description="로컬 에이전트 상태 · 관리" chatDomain="default">
      <LocalAgentsClient />
    </PageShell>
  );
}
