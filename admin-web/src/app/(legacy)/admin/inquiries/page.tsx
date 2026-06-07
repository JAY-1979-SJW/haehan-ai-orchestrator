import { PageShell } from "@/components/ui/PageShell";
import { InquiriesClient } from "./InquiriesClient";

export default function InquiriesPage() {
  return (
    <PageShell title="문의 관리" description="사이트 방문자 문의 접수·답변 관리" chatDomain="default">
      <InquiriesClient />
    </PageShell>
  );
}
