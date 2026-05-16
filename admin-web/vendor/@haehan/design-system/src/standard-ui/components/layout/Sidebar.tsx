/** Sidebar — Navy 배경 사이드바 네비게이션 골격 */
import React from 'react';

export interface SidebarNavItem {
  href: string;
  label: string;
  icon?: React.ReactNode;
  active?: boolean;
}

export interface SidebarNavGroup {
  label?: string;
  items: SidebarNavItem[];
}

export interface SidebarProps {
  logo?: React.ReactNode;
  groups: SidebarNavGroup[];
  footer?: React.ReactNode;
  onNavigate?: (href: string) => void;
}

export function Sidebar({ logo, groups, footer, onNavigate }: SidebarProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', color: '#FFFFFF' }}>
      {logo && (
        <div style={{ padding: '20px 16px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          {logo}
        </div>
      )}
      <nav style={{ flex: 1, padding: '8px 0', overflowY: 'auto' }}>
        {groups.map((group, gi) => (
          <div key={gi} style={{ marginBottom: 8 }}>
            {group.label && (
              <div style={{
                fontSize: 10,
                fontWeight: 600,
                color: 'rgba(255,255,255,0.4)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                padding: '8px 16px 4px',
              }}>
                {group.label}
              </div>
            )}
            {group.items.map((item) => (
              <a
                key={item.href}
                href={item.href}
                onClick={(e) => { if (onNavigate) { e.preventDefault(); onNavigate(item.href); } }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 16px',
                  fontSize: 13,
                  fontWeight: item.active ? 600 : 400,
                  color: item.active ? '#F97316' : 'rgba(255,255,255,0.75)',
                  background: item.active ? 'rgba(249,115,22,0.12)' : 'transparent',
                  borderRadius: 6,
                  margin: '1px 8px',
                  textDecoration: 'none',
                  transition: 'background 0.15s, color 0.15s',
                }}
              >
                {item.icon && <span style={{ flexShrink: 0, opacity: item.active ? 1 : 0.7 }}>{item.icon}</span>}
                {item.label}
              </a>
            ))}
          </div>
        ))}
      </nav>
      {footer && (
        <div style={{ padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          {footer}
        </div>
      )}
    </div>
  );
}
