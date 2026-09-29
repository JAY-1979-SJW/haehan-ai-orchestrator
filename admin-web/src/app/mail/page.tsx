import { PageShell } from "@/components/ui/PageShell";
import { GmailInboxPanel } from "./components/GmailInboxPanel";
import { MailAssistantPanel } from "./components/MailAssistantPanel";

/**
 * 메일 비서 — Gmail 조회 + AI 요약/회신초안 + 승인발송.
 * 2026-09-29 구조 재설계(docs/specs/2026-09-29_app_purpose_and_structure_redesign.md):
 * "운영센터"(상태 화면)에 섞여있던 실행형 패널을 도메인별 화면으로 분리.
 */
export default function MailPage() {
  return (
    <PageShell title="메일 비서" description="Gmail 조회 · AI 요약/회신초안 · 승인 후 발송" chatDomain="mail">
      <div className="space-y-8">
        <GmailInboxPanel />
        <MailAssistantPanel />
      </div>
    </PageShell>
  );
}
