/** Select — 표준 셀렉트 */
import React from 'react';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: SelectOption[];
  error?: string;
}

export function Select({ label, options, error, style, id, ...props }: SelectProps) {
  const selectId = id ?? label?.replace(/\s+/g, '-').toLowerCase();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {label && (
        <label htmlFor={selectId} style={{ fontSize: 12, fontWeight: 500, color: '#374151' }}>
          {label}
        </label>
      )}
      <select
        id={selectId}
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
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      {error && <span style={{ fontSize: 11, color: '#DC2626' }}>{error}</span>}
    </div>
  );
}
