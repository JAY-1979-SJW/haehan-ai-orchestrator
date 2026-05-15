/** Alert — 알림/경고 메시지 박스 */
import React from 'react';

export type AlertType = 'success' | 'warning' | 'error' | 'info';

const STYLES: Record<AlertType, { bg: string; border: string; text: string }> = {
  success: { bg: '#ECFDF5', border: '#059669', text: '#065F46' },
  warning: { bg: '#FFFBEB', border: '#D97706', text: '#92400E' },
  error:   { bg: '#FEF2F2', border: '#DC2626', text: '#B91C1C' },
  info:    { bg: '#EFF6FF', border: '#2563EB', text: '#1E40AF' },
};

export interface AlertProps {
  type: AlertType;
  title?: string;
  children: React.ReactNode;
  onClose?: () => void;
}

export function Alert({ type, title, children, onClose }: AlertProps) {
  const s = STYLES[type];
  return (
    <div
      role="alert"
      style={{
        background: s.bg,
        border: `1px solid ${s.border}`,
        borderRadius: 8,
        padding: '12px 16px',
        color: s.text,
        fontSize: 13,
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
      }}
    >
      <div style={{ flex: 1 }}>
        {title && <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>}
        {children}
      </div>
      {onClose && (
        <button
          onClick={onClose}
          aria-label="닫기"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: s.text, padding: 0, fontSize: 16, lineHeight: 1 }}
        >
          ×
        </button>
      )}
    </div>
  );
}
