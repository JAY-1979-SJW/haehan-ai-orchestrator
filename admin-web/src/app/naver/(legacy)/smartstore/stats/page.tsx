/** /naver/smartstore/stats — 데이터 분석 */
import { PageShell } from "@/components/ui/PageShell";
import StatsClient from "./StatsClient";

export default function StatsPage() {
  return (
    <PageShell title="데이터 분석" description="매출 통계 · 방문 통계 · 상품 분석" chatDomain="smartstore">
      <StatsClient />
    </PageShell>
  );
}
