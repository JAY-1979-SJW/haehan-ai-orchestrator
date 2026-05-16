/** AppShell — 전체 레이아웃 컨테이너 (TopAccentLine + Sidebar + Header + content) */
import React from 'react';
import { TopAccentLine } from './TopAccentLine';

export interface AppShellProps {
  sidebar: React.ReactNode;
  header?: React.ReactNode;
  children: React.ReactNode;
  sidebarWidth?: string;
}

export function AppShell({
  sidebar,
  header,
  children,
  sidebarWidth = '224px',
}: AppShellProps) {
  return (
    <>
      <TopAccentLine />
      <div style={{ display: 'flex', minHeight: '100vh', paddingTop: 4 }}>
        <aside
          style={{
            width: sidebarWidth,
            flexShrink: 0,
            background: '#1E2D4A',
            display: 'flex',
            flexDirection: 'column',
            position: 'fixed',
            top: 4,
            bottom: 0,
            left: 0,
            zIndex: 100,
            overflowY: 'auto',
          }}
        >
          {sidebar}
        </aside>
        <div style={{ marginLeft: sidebarWidth, flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {header && (
            <header
              style={{
                height: 52,
                background: '#FFFFFF',
                borderBottom: '1px solid #E5E7EB',
                display: 'flex',
                alignItems: 'center',
                padding: '0 24px',
                position: 'sticky',
                top: 4,
                zIndex: 50,
              }}
            >
              {header}
            </header>
          )}
          <main style={{ flex: 1, background: '#F5F7FA' }}>
            {children}
          </main>
        </div>
      </div>
    </>
  );
}
