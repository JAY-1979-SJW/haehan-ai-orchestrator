/** /naver/smartstore/settlements — 정산 전용 페이지 */
import { PageShell } from "@/components/ui/PageShell";
import SettlementsClient from "./SettlementsClient";

export default function SettlementsPage() {
  return (
    <PageShell title="정산 관리" description="정산 요약 · 정산 내역 · 세금계산서" chatDomain="smartstore">
      <SettlementsClient />
    </PageShell>
  );
}
