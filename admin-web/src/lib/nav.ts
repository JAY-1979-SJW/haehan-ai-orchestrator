export interface NavItem {
  key: string;
  label: string;
  shortLabel: string;
  href: string;
  exact?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "home", label: "Home", shortLabel: "Home", href: "/", exact: true },
  { key: "local-agents", label: "Local Agents", shortLabel: "Agents", href: "/local-agents" },
  { key: "market-research", label: "Market Research", shortLabel: "Market", href: "/market-research" },
  { key: "cad", label: "AI CAD", shortLabel: "CAD", href: "/cad" },
  { key: "file-map", label: "File Map", shortLabel: "Files", href: "/file-map" },
  { key: "browser-approvals", label: "Browser Approvals", shortLabel: "Approve", href: "/browser-approvals" },
];
