/** /naver/smartstore/marketing — 마케팅/혜택 */
import { PageShell } from "@/components/ui/PageShell";
import MarketingClient from "./MarketingClient";

export default function MarketingPage() {
  return (
    <PageShell title="마케팅/혜택" description="쿠폰·할인 · 프로모션 · SEO 최적화">
      <MarketingClient />
    </PageShell>
  );
}
