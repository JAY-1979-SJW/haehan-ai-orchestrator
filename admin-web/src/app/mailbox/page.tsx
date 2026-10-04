import { PageShell } from "@/components/ui/PageShell";
import { MailboxApp } from "./components/MailboxApp";

/**
 * 메일함 — 네이버 메일(IMAP/SMTP) 목차 · 목록 · 읽기 · 첨부 · 쓰기.
 * 기준서: docs/specs/2026-10-01_naver_mailbox_tab.md (Gmail 용 "메일 비서"(/mail)와 별개)
 */
export default function MailboxPage() {
  return (
    <PageShell title="메일함" description="네이버 메일 · 폴더 · 첨부 파일 · 쓰기">
      <MailboxApp />
    </PageShell>
  );
}
