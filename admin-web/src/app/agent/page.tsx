import { PageShell } from "@/components/ui/PageShell";
import { AgentClient } from "./AgentClient";

export default function AgentPage() {
  return (
    <PageShell title="원격 브라우저" description="AI가 내 PC의 로그인된 브라우저를 운전해 작업 수행" chatDomain="default">
      <AgentClient />
    </PageShell>
  );
}
