"use client";
import CadClient from "./CadClient";
import { PageShell } from "@/components/ui/PageShell";

export default function CadPage() {
  return (
    <PageShell title="AI CAD" description="도면 분석 · 물량 추출" chatDomain="cad">
      <CadClient />
    </PageShell>
  );
}
