/** TopAccentLine — 페이지 상단 4px Orange Accent Line */
import React from 'react';

export function TopAccentLine() {
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: 4,
        background: '#F97316',
        zIndex: 9999,
      }}
      aria-hidden
    />
  );
}
