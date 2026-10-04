import { PageShell } from "@/components/ui/PageShell";
import { GongmuApp } from "./GongmuApp";

/**
 * 건설업 공무 — 현장·계약을 등록하면 해당되는 공무 업무가 자동으로 생기고, 기한·서류를 한눈에 챙기는 업무판(관리자 전용).
 * 기준서: docs/specs/2026-10-02_construction_gongmu.md (G1)
 */
export default function GongmuPage() {
  return (
    <PageShell title="건설업 공무" description="현장·계약 등록 → 필요한 공무 업무 자동 생성 · 기한과 서류 관리 (외부 사이트 제출은 하지 않음)">
      <GongmuApp />
    </PageShell>
  );
}
