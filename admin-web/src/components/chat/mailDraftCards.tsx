import type { ExtraCard } from "./UniversalChat";
import { MailDraftCard } from "@/app/mailbox/components/MailDraftCard";

/**
 * 답변 끝의 [[mail-draft:<id>]] 를 메일 발송 승인 카드로 바꾸는 규칙 — 모든 AI 창이 기본으로 쓴다.
 * AI 는 어느 창에서든 mailbox.draft 로 초안을 만들 수 있고 표식을 내므로(직원 지침 6번), 팩스 카드처럼 공용으로 둔다.
 * 보내기는 카드 버튼(사람)으로만 된다 — AI 허용 API 에 send 는 없다.
 * (MailDraftCard 는 메일함 화면 소속이지만 초안 id 만으로 서버에서 읽는 자립형이라 그대로 가져다 쓴다.)
 */
export const MAIL_DRAFT_CARDS: ExtraCard[] = [
  { mark: /\[\[mail-draft:([0-9a-f]{32})\]\]/g, render: (id) => <MailDraftCard draftId={id} /> },
];
