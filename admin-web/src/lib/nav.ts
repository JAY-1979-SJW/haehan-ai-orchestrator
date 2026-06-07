export interface NavItem {
  key: string;
  label: string;
  shortLabel: string;
  href: string;
  exact?: boolean;
}

export type NavGroup = {
  group: string;
  items: NavItem[];
};

// 전체 탭 목록(보존) — 단일 AI 콘솔로 단순화하며 숨김. 복원 시 NAV_GROUPS = NAV_GROUPS_ALL.
export const NAV_GROUPS_ALL: NavGroup[] = [
  {
    group: "홈",
    items: [
      { key: "home",      label: "대시보드",   shortLabel: "홈",   href: "/", exact: true },
      { key: "assistant", label: "AI 비서",    shortLabel: "비서", href: "/assistant" },
      { key: "ops",       label: "운영센터",   shortLabel: "운영", href: "/ops" },
    ],
  },
  {
    group: "스마트스토어",
    items: [
      { key: "ss-home",        label: "스토어 AI 채팅", shortLabel: "채팅",   href: "/naver/smartstore" },
      { key: "ss-products",    label: "상품 관리",      shortLabel: "상품",   href: "/naver/smartstore/products" },
      { key: "ss-orders",      label: "주문 관리",      shortLabel: "주문",   href: "/naver/smartstore/orders" },
      { key: "ss-settlements", label: "정산 관리",      shortLabel: "정산",   href: "/naver/smartstore/settlements" },
      { key: "ss-reviews",     label: "리뷰/문의",      shortLabel: "리뷰",   href: "/naver/smartstore/reviews" },
      { key: "ss-stats",       label: "데이터 분석",    shortLabel: "통계",   href: "/naver/smartstore/stats" },
      { key: "ss-marketing",   label: "마케팅/혜택",    shortLabel: "마케팅", href: "/naver/smartstore/marketing" },
    ],
  },
  {
    group: "콘텐츠",
    items: [
      { key: "youtube",  label: "YouTube 관리", shortLabel: "유튜브", href: "/youtube" },
      { key: "google",   label: "구글 허브",    shortLabel: "구글",   href: "/google" },
      { key: "market-research", label: "시장 조사", shortLabel: "시장", href: "/market-research" },
      { key: "blog",     label: "블로그 관리",  shortLabel: "블로그", href: "/naver/blog" },
      { key: "cafe",     label: "카페 탐색",    shortLabel: "카페",   href: "/assistant/cafe" },
      { key: "community", label: "커뮤니티 레이더", shortLabel: "레이더", href: "/community" },
      { key: "agent",    label: "원격 브라우저",  shortLabel: "원격",   href: "/agent" },
      { key: "news",     label: "뉴스 수집",    shortLabel: "뉴스",   href: "/assistant/news" },
    ],
  },
  {
    group: "네이버",
    items: [
      { key: "keywords",      label: "키워드 검색", shortLabel: "키워드", href: "/naver/keywords" },
      { key: "naver-session", label: "로그인 세션", shortLabel: "세션",   href: "/naver/session" },
    ],
  },
  {
    group: "업무",
    items: [
      { key: "bid",      label: "나라장터 입찰", shortLabel: "입찰", href: "/bid" },
      { key: "grant-radar", label: "정부 지원사업", shortLabel: "지원", href: "/grant-radar" },
      { key: "inbox",    label: "메일 Inbox",    shortLabel: "메일", href: "/assistant/inbox" },
      { key: "tasks",    label: "작업 목록",     shortLabel: "작업", href: "/assistant/tasks" },
      { key: "approval", label: "승인 게이트",   shortLabel: "승인", href: "/assistant/approval" },
    ],
  },
  {
    group: "외부 연동",
    items: [
      { key: "gabia",             label: "가비아 도메인",  shortLabel: "가비아", href: "/gabia" },
      { key: "hanafax",           label: "하나팩스",       shortLabel: "팩스",  href: "/hanafax" },
      { key: "dataportal",        label: "공공데이터포털", shortLabel: "공공",  href: "/dataportal" },
      { key: "external-tasks",    label: "외부 업무 현황", shortLabel: "외부",  href: "/external-tasks" },
      { key: "external-sites",    label: "외부 사이트",    shortLabel: "사이트", href: "/assistant/external-sites" },
      { key: "browser-approvals", label: "브라우저 승인",  shortLabel: "승인",  href: "/browser-approvals" },
    ],
  },
  {
    group: "관리자",
    items: [
      { key: "server", label: "서버 관리", shortLabel: "서버", href: "/server" },
      { key: "inquiries", label: "문의 관리", shortLabel: "문의", href: "/admin/inquiries" },
      { key: "site-settings", label: "사이트 설정", shortLabel: "사이트", href: "/settings/sites" },
      { key: "user-approval", label: "회원 승인", shortLabel: "승인", href: "/admin/users" },
      { key: "licenses", label: "라이선스 관리", shortLabel: "라이선스", href: "/admin/licenses" },
    ],
  },
  {
    group: "개발 도구",
    items: [
      { key: "local-agents", label: "Local Agents", shortLabel: "Agents", href: "/local-agents" },
      { key: "file-map",     label: "File Map",     shortLabel: "Files",  href: "/file-map" },
      { key: "deployment",   label: "배포 현황",    shortLabel: "배포",   href: "/assistant/deployment" },
      { key: "logs",         label: "시스템 로그",  shortLabel: "로그",   href: "/assistant/logs" },
      { key: "storage",      label: "저장소",       shortLabel: "저장",   href: "/assistant/storage" },
    ],
  },
];

// 콘솔 중심 모드: 좌측엔 기본 항목만 노출, 모든 작업은 AI 콘솔(채팅)에서. 나머지 탭은
// 숨김(코드/라우트는 보존 — URL 직접 접근 가능). 전체 복원: NAV_GROUPS = NAV_GROUPS_ALL.
export const NAV_GROUPS: NavGroup[] = [
  {
    group: "메뉴",
    items: [
      { key: "home",          label: "AI 콘솔",    shortLabel: "AI",   href: "/", exact: true },
      { key: "naver-session", label: "로그인 세션", shortLabel: "세션", href: "/naver/session" },
      { key: "approval",      label: "승인 게이트", shortLabel: "승인", href: "/assistant/approval" },
      { key: "ops",           label: "운영센터",   shortLabel: "운영", href: "/ops" },
      { key: "mypage",        label: "설정",       shortLabel: "설정", href: "/mypage" },
    ],
  },
];

// 기존 flat 목록 — 레거시 호환
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
