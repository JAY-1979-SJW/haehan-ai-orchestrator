import { PageShell } from "@/components/ui/PageShell";
import { ServerClient } from "./ServerClient";

export default function ServerPage() {
  return (
    <PageShell title="서버 관리" description="인스턴스 상태 · 헬스 · 배포 (IXcloud R2 / haehan-ai)" chatDomain="default">
      <ServerClient />
    </PageShell>
  );
}
