export interface NavItem {
  key: string;
  label: string;
  shortLabel: string;
  href: string;
  exact?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "home", label: "홈", shortLabel: "홈", href: "/", exact: true },
  { key: "local-agents", label: "로컬 에이전트", shortLabel: "에이전트", href: "/local-agents" },
  { key: "cad", label: "AI CAD", shortLabel: "CAD", href: "/cad" },
  { key: "file-map", label: "파일 지도", shortLabel: "파일", href: "/file-map" },
  { key: "browser-approvals", label: "브라우저 승인", shortLabel: "승인", href: "/browser-approvals" },
];
