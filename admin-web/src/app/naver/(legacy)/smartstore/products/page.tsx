/** /naver/smartstore/products — 상품 관리 */
import { PageShell } from "@/components/ui/PageShell";
import ProductsClient from "./ProductsClient";

export default function ProductsPage() {
  return (
    <PageShell title="상품 관리" description="상품 목록 · 등록 · 일괄 등록" chatDomain="smartstore">
      <ProductsClient />
    </PageShell>
  );
}
