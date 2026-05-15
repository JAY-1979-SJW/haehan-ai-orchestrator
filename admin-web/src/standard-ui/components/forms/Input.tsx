/** Input — 표준 텍스트 입력 */
import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({ label, error, style, id, ...props }: InputProps) {
  const inputId = id ?? label?.replace(/\s+/g, '-').toLowerCase();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {label && (
        <label htmlFor={inputId} style={{ fontSize: 12, fontWeight: 500, color: '#374151' }}>
          {label}
        </label>
      )}
      <input
        id={inputId}
        style={{
          padding: '8px 10px',
          fontSize: 13,
          borderRadius: 6,
          border: `1px solid ${error ? '#DC2626' : '#D1D5DB'}`,
          background: '#FFFFFF',
          color: '#0F172A',
          outline: 'none',
          width: '100%',
          boxSizing: 'border-box',
          ...style,
        }}
        {...props}
      />
      {error && <span style={{ fontSize: 11, color: '#DC2626' }}>{error}</span>}
    </div>
  );
}
