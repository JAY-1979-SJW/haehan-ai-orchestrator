export interface NavItem {
  key: string;
  label: string;
  href: string;
  exact?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "home",         label: "홈",           href: "/",             exact: true },
  { key: "local-agents", label: "로컬 에이전트", href: "/local-agents" },
  { key: "cad",          label: "AI CAD",       href: "/cad" },
];
