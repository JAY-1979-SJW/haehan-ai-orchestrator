/** /naver/keywords — 네이버 키워드 검색 */
import { PageShell } from "@/components/ui/PageShell";
import KeywordsClient from "./KeywordsClient";

export const metadata = { title: "키워드 · 경쟁사 조사 | Haehan AI Admin" };

export default function KeywordsPage() {
  return (
    <PageShell title="키워드 · 경쟁사 조사" description="블로그 검색 수집 · 타업체 쇼핑 경쟁사 조사 · 키워드 도구" chatDomain="naver">
      <KeywordsClient />
    </PageShell>
  );
}
