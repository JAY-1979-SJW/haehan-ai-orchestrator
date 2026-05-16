/** EmptyState — 데이터 없을 때 빈 상태 표시 */
import React from 'react';

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title?: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon, title = '데이터가 없습니다.', description, action }: EmptyStateProps) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '48px 24px',
      gap: 12,
      color: '#6B7280',
      textAlign: 'center',
    }}>
      {icon && <div style={{ fontSize: 40, opacity: 0.4 }}>{icon}</div>}
      <div style={{ fontSize: 14, fontWeight: 500, color: '#374151' }}>{title}</div>
      {description && <div style={{ fontSize: 13, color: '#9CA3AF', maxWidth: 320 }}>{description}</div>}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}
