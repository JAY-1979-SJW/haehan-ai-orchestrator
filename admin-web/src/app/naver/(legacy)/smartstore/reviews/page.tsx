/** /naver/smartstore/reviews — 리뷰/문의 */
import { PageShell } from "@/components/ui/PageShell";
import ReviewsClient from "./ReviewsClient";

export default function ReviewsPage() {
  return (
    <PageShell title="리뷰/문의" description="고객 리뷰 · 고객 문의 · 자동응답 설정" chatDomain="smartstore">
      <ReviewsClient />
    </PageShell>
  );
}
