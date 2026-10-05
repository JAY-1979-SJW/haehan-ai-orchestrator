import type { ExtraCard } from "./UniversalChat";
import { SiteMapExploreCard } from "@/components/sitemap/SiteMapExploreCard";

/**
 * 답변 끝의 [[sitemap-explore:<id>]] 를 사이트 탐색 승인 카드로 바꾸는 규칙 — 모든 AI 창이 기본으로 쓴다.
 * AI 는 어느 창에서든 sitemap.explore_request 로 탐색을 요청하고 표식을 내므로(직원 지침 5번) 메일 초안 카드처럼 공용으로 둔다.
 * 승인·취소는 카드 버튼(사람)으로만 된다 — AI 허용 API 에 승인은 없다.
 */
export const SITE_MAP_EXPLORE_CARDS: ExtraCard[] = [
  { mark: /\[\[sitemap-explore:([0-9a-f]{32})\]\]/g, render: (id) => <SiteMapExploreCard requestId={id} /> },
];
