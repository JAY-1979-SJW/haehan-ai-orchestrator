/** PageContainer — 페이지 내용 영역 래퍼 */
import React from 'react';

export interface PageContainerProps {
  children: React.ReactNode;
  variant?: 'default' | 'table' | 'form' | 'dashboard';
  className?: string;
}

const variantStyles: Record<string, React.CSSProperties> = {
  default:   { padding: '24px', maxWidth: 1280, margin: '0 auto' },
  table:     { padding: '20px 24px', maxWidth: '100%' },
  form:      { padding: '24px', maxWidth: 800, margin: '0 auto' },
  dashboard: { padding: '20px 24px', maxWidth: '100%' },
};

export function PageContainer({ children, variant = 'default', className }: PageContainerProps) {
  return (
    <div style={variantStyles[variant]} className={className}>
      {children}
    </div>
  );
}
