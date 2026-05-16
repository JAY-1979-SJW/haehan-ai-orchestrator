/** Button — 표준 버튼 컴포넌트 */
import React from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'navy';
export type ButtonSize = 'xs' | 'sm' | 'md';

const BASE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 6,
  borderRadius: 6,
  fontWeight: 500,
  border: '1px solid transparent',
  cursor: 'pointer',
  transition: 'background 0.15s, box-shadow 0.15s',
  userSelect: 'none',
  whiteSpace: 'nowrap',
};

const VARIANTS: Record<ButtonVariant, React.CSSProperties> = {
  primary:   { background: '#F97316', color: '#FFFFFF', borderColor: '#F97316' },
  secondary: { background: '#FFFFFF', color: '#374151', borderColor: '#D1D5DB' },
  ghost:     { background: 'transparent', color: '#6B7280', borderColor: '#E5E7EB' },
  navy:      { background: '#1E2D4A', color: '#FFFFFF', borderColor: '#1E2D4A' },
};

const SIZES: Record<ButtonSize, React.CSSProperties> = {
  xs: { padding: '4px 8px',  fontSize: 11 },
  sm: { padding: '5px 10px', fontSize: 12 },
  md: { padding: '8px 14px', fontSize: 13 },
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: React.ReactNode;
}

export function Button({ variant = 'primary', size = 'md', loading = false, disabled, children, style, ...props }: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      style={{
        ...BASE,
        ...VARIANTS[variant],
        ...SIZES[size],
        opacity: (disabled || loading) ? 0.45 : 1,
        cursor: (disabled || loading) ? 'not-allowed' : 'pointer',
        ...style,
      }}
      {...props}
    >
      {loading && <span style={{ fontSize: 12 }}>…</span>}
      {children}
    </button>
  );
}
