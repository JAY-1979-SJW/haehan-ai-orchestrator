/** /naver/smartstore/orders — 주문/정산 */
import { PageShell } from "@/components/ui/PageShell";
import OrdersClient from "./OrdersClient";

export default function OrdersPage() {
  return (
    <PageShell title="주문/정산" description="주문 현황 · 정산 내역 · 배송 처리">
      <OrdersClient />
    </PageShell>
  );
}
