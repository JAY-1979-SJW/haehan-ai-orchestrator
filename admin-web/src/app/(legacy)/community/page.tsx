import { PageShell } from "@/components/ui/PageShell";
import { CommunityClient } from "./CommunityClient";

export default function CommunityPage() {
  return (
    <PageShell title="커뮤니티 레이더" description="사이트 등록 → 수집 → AI 트렌드·수익 분석" chatDomain="default">
      <CommunityClient />
    </PageShell>
  );
}
