export interface NavItem {
  key: string;
  label: string;
  shortLabel: string;
  href: string;
  exact?: boolean;
  adminOnly?: boolean; // owner/admin만 표시
}

export type NavGroup = {
  group: string;
  items: NavItem[];
  adminOnly?: boolean;
};

// 채팅 중심 UI — 좌측 nav는 보고/확인용만. 세부 기능은 채팅으로 요청.
export const NAV_GROUPS: NavGroup[] = [
  {
    group: "홈",
    items: [
      { key: "home", label: "AI 콘솔", shortLabel: "AI", href: "/", exact: true },
      { key: "ops",  label: "운영센터", shortLabel: "운영", href: "/ops" },
      { key: "mail", label: "메일 비서", shortLabel: "메일", href: "/mail" },
      { key: "google", label: "구글 허브", shortLabel: "구글", href: "/google" },
      { key: "login-status", label: "로그인 현황", shortLabel: "로그인", href: "/login-status" },
      { key: "mypage", label: "설정", shortLabel: "설정", href: "/mypage" },
    ],
  },
  {
    group: "스마트스토어",
    items: [
      { key: "ss-home", label: "스토어 AI 채팅", shortLabel: "스토어", href: "/naver/smartstore" },
    ],
  },
  {
    group: "콘텐츠",
    items: [
      { key: "blog", label: "블로그 AI", shortLabel: "블로그", href: "/naver/blog" },
      { key: "marketing", label: "마케팅 자료", shortLabel: "마케팅", href: "/marketing" },
    ],
  },
  {
    group: "업무 현황",
    items: [
      { key: "tasks",    label: "작업 목록",   shortLabel: "작업", href: "/assistant/tasks" },
      { key: "approval", label: "승인 게이트", shortLabel: "승인", href: "/assistant/approval" },
    ],
  },
  {
    group: "관리자",
    adminOnly: true,
    items: [
      { key: "user-approval", label: "회원 승인",     shortLabel: "승인",    href: "/admin/users",    adminOnly: true },
      { key: "licenses",      label: "라이선스 관리", shortLabel: "라이선스", href: "/admin/licenses", adminOnly: true },
    ],
  },
];

// 전체 목록 보존 (복원·참조용 — nav에는 미표시)
export const NAV_GROUPS_ALL: NavGroup[] = [
  {
    group: "홈",
    items: [
      { key: "home",      label: "AI 콘솔",  shortLabel: "AI",  href: "/", exact: true },
      { key: "assistant", label: "AI 비서",  shortLabel: "비서", href: "/assistant" },
      { key: "ops",       label: "운영센터", shortLabel: "운영", href: "/ops" },
      { key: "login-status", label: "로그인 현황", shortLabel: "로그인", href: "/login-status" },
      { key: "mypage",    label: "설정",     shortLabel: "설정", href: "/mypage" },
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
      { key: "youtube",         label: "YouTube 관리", shortLabel: "유튜브", href: "/youtube" },
      { key: "google",          label: "구글 허브",    shortLabel: "구글",   href: "/google" },
      { key: "market-research", label: "시장 조사",    shortLabel: "시장",   href: "/market-research" },
      { key: "news",            label: "뉴스 수집",    shortLabel: "뉴스",   href: "/assistant/news" },
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
      { key: "bid",         label: "나라장터 입찰", shortLabel: "입찰", href: "/bid" },
      { key: "grant-radar", label: "정부 지원사업", shortLabel: "지원", href: "/grant-radar" },
      { key: "tasks",       label: "작업 목록",     shortLabel: "작업", href: "/assistant/tasks" },
      { key: "approval",    label: "승인 게이트",   shortLabel: "승인", href: "/assistant/approval" },
    ],
  },
  {
    group: "외부 연동",
    items: [
      { key: "eum",               label: "EUM 단말기",     shortLabel: "EUM",    href: "/eum" },
      { key: "gabia",             label: "가비아 도메인",  shortLabel: "가비아",  href: "/gabia" },
      { key: "hanafax",           label: "하나팩스",       shortLabel: "팩스",   href: "/hanafax" },
      { key: "dataportal",        label: "공공데이터포털", shortLabel: "공공",   href: "/dataportal" },
      { key: "external-tasks",    label: "외부 업무 현황", shortLabel: "외부",   href: "/external-tasks" },
      { key: "external-sites",    label: "외부 사이트",    shortLabel: "사이트", href: "/assistant/external-sites" },
      { key: "browser-approvals", label: "브라우저 승인",  shortLabel: "승인",   href: "/browser-approvals" },
    ],
  },
  {
    group: "관리자",
    adminOnly: true,
    items: [
      { key: "server",        label: "서버 관리",     shortLabel: "서버",    href: "/server",          adminOnly: true },
      { key: "inquiries",     label: "문의 관리",     shortLabel: "문의",    href: "/admin/inquiries", adminOnly: true },
      { key: "site-settings", label: "사이트 설정",   shortLabel: "사이트",  href: "/settings/sites",  adminOnly: true },
      { key: "user-approval", label: "회원 승인",     shortLabel: "승인",    href: "/admin/users",     adminOnly: true },
      { key: "licenses",      label: "라이선스 관리", shortLabel: "라이선스", href: "/admin/licenses",  adminOnly: true },
    ],
  },
  {
    group: "개발 도구",
    adminOnly: true,
    items: [
      { key: "local-agents", label: "Local Agents", shortLabel: "Agents", href: "/local-agents", adminOnly: true },
      { key: "file-map",     label: "File Map",     shortLabel: "Files",  href: "/file-map",     adminOnly: true },
      { key: "deployment",   label: "배포 현황",    shortLabel: "배포",   href: "/assistant/deployment", adminOnly: true },
      { key: "logs",         label: "시스템 로그",  shortLabel: "로그",   href: "/assistant/logs",       adminOnly: true },
      { key: "storage",      label: "저장소",       shortLabel: "저장",   href: "/assistant/storage",    adminOnly: true },
    ],
  },
];

// 기존 flat 목록 — 레거시 호환
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
