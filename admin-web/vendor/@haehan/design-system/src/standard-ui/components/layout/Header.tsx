/** Header — 페이지 상단 헤더 바 */
import React from 'react';

export interface HeaderProps {
  title?: string;
  left?: React.ReactNode;
  right?: React.ReactNode;
}

export function Header({ title, left, right }: HeaderProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {left}
        {title && (
          <span style={{ fontSize: 15, fontWeight: 600, color: '#0F172A' }}>{title}</span>
        )}
      </div>
      {right && <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>{right}</div>}
    </div>
  );
}
