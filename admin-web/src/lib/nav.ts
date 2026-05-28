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

export const NAV_GROUPS: NavGroup[] = [
  {
    group: "대시보드",
    items: [
      { key: "home",       label: "Home",     shortLabel: "Home", href: "/", exact: true },
      { key: "assistant",  label: "AI 비서",   shortLabel: "비서", href: "/assistant" },
      { key: "ops",        label: "운영센터",  shortLabel: "운영", href: "/ops" },
    ],
  },
  {
    group: "메일 · 작업",
    items: [
      { key: "inbox",    label: "메일 Inbox",  shortLabel: "메일", href: "/assistant/inbox" },
      { key: "tasks",    label: "작업 목록",    shortLabel: "작업", href: "/assistant/tasks" },
      { key: "approval", label: "승인 게이트",  shortLabel: "승인", href: "/assistant/approval" },
    ],
  },
  {
    group: "카페 · 뉴스",
    items: [
      { key: "cafe",    label: "카페 탐색",   shortLabel: "카페", href: "/assistant/cafe" },
      { key: "news",    label: "뉴스 수집",   shortLabel: "뉴스", href: "/assistant/news" },
      { key: "market",      label: "시장조사",       shortLabel: "시장", href: "/market-research" },
      { key: "blog",        label: "블로그 관리",    shortLabel: "블로그", href: "/naver/blog" },
      { key: "smartstore",  label: "스마트스토어",   shortLabel: "스토어", href: "/naver/smartstore" },
      { key: "keywords",    label: "키워드 검색",    shortLabel: "키워드", href: "/naver/keywords" },
    ],
  },
  {
    group: "외부 연동",
    items: [
      { key: "external-tasks",  label: "외부 업무 현황",  shortLabel: "외부",   href: "/external-tasks" },
      { key: "external-sites",  label: "외부 사이트",     shortLabel: "사이트", href: "/assistant/external-sites" },
      { key: "browser-approvals",label: "브라우저 승인",  shortLabel: "승인",   href: "/browser-approvals" },
    ],
  },
  {
    group: "개발 도구",
    items: [
      { key: "local-agents", label: "Local Agents",  shortLabel: "Agents", href: "/local-agents" },
      { key: "cad",          label: "AI CAD",        shortLabel: "CAD",    href: "/cad" },
      { key: "file-map",     label: "File Map",      shortLabel: "Files",  href: "/file-map" },
      { key: "deployment",   label: "배포 현황",      shortLabel: "배포",   href: "/assistant/deployment" },
      { key: "logs",         label: "시스템 로그",    shortLabel: "로그",   href: "/assistant/logs" },
      { key: "storage",      label: "저장소",         shortLabel: "저장",   href: "/assistant/storage" },
    ],
  },
];

// 기존 flat 목록 — 레거시 호환
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
