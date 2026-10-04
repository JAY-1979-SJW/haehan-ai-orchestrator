import { PageShell } from "@/components/ui/PageShell";
import { SiteMapApp } from "./SiteMapApp";

/**
 * 사이트 업무 지도 — 앱이 탐색해 업무 단위로 저장한 사이트 구조를 보고, 업무 이름·목적·분류를 확정한다(관리자 전용).
 * 기준서: docs/specs/2026-10-03_site_task_map.md (M4)
 */
export default function SiteMapPage() {
  return (
    <PageShell title="사이트 업무 지도" description="탐색한 사이트를 업무 단위로 저장 · 에이전트가 이 지도를 읽고 같은 방식으로 처리 (제출·신고 업무는 사람 승인 없이 실행하지 않음)">
      <SiteMapApp />
    </PageShell>
  );
}
