/** /naver/blog — 네이버 블로그 관리 */
import { PageShell } from "@/components/ui/PageShell";
import BlogClient from "./BlogClient";

export default function BlogPage() {
  return (
    <PageShell title="블로그 관리" description="네이버 블로그 현황 조회 및 글쓰기 요청" chatDomain="naver">
      <BlogClient />
    </PageShell>
  );
}
