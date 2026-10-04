import { PageShell } from "@/components/ui/PageShell";
import { HanafaxApp } from "./HanafaxApp";

/**
 * 하나팩스 — 팩스 발송 승인·발송·이력 + AI 창 연동.
 * 기준서: docs/specs/2026-10-02_hanafax_auto_send.md (§10 화면·AI 연동)
 */
export default function HanafaxPage() {
  return (
    <PageShell title="하나팩스" description="발송 전 승인 필수 · AI 창에 첨부 파일 경로를 알려주면 승인 대기로 올라옵니다">
      <HanafaxApp />
    </PageShell>
  );
}
