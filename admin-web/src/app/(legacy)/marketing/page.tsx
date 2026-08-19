import { PageShell } from "@/components/ui/PageShell";
import MarketingOpsClient from "./MarketingOpsClient";

export const metadata = {
  title: "마케팅 운영실 | Haehan AI Admin",
};

export default function MarketingPage() {
  return (
    <PageShell
      title="마케팅 운영실"
      description="실측 데이터 기반 주제 선정 → 블로그·유튜브·쇼츠·인스타 콘텐츠 생성 → 승인 → 발행"
      chatDomain="marketing"
    >
      <MarketingOpsClient />
    </PageShell>
  );
}
