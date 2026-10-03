import { PageShell } from "@/components/ui/PageShell";
import { BulkApp } from "../components/bulk/BulkApp";

/**
 * 메일 대량 발송 — 수신자별로 한 통씩 차례로 보내는 승인서 방식(관리자 전용).
 * 기준서: docs/specs/2026-10-02_mail_bulk_sequential.md
 */
export default function MailBulkPage() {
  return (
    <PageShell title="메일 대량 발송" description="승인한 내용을 한 명씩 간격을 두고 차례로 발송">
      <BulkApp />
    </PageShell>
  );
}
