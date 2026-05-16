/** MetricCard — KPI 지표 카드 (icon + label + value + sub) */
import React from 'react';

export interface MetricCardProps {
  icon?: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  accentColor?: string;
  onClick?: () => void;
}

export function MetricCard({ icon, label, value, sub, accentColor = '#F97316', onClick }: MetricCardProps) {
  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => { if (onClick && (e.key === 'Enter' || e.key === ' ')) onClick(); }}
      style={{
        background: '#FFFFFF',
        border: '1px solid #E5E7EB',
        borderRadius: 8,
        padding: '18px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'box-shadow 0.15s',
        userSelect: 'none',
      }}
      onMouseEnter={(e) => { if (onClick) (e.currentTarget as HTMLDivElement).style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.boxShadow = 'none'; }}
    >
      {icon && (
        <div style={{
          width: 42, height: 42, borderRadius: 10,
          background: accentColor + '1A',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <span style={{ color: accentColor }}>{icon}</span>
        </div>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 2 }}>{label}</div>
        <div style={{ fontSize: 22, fontWeight: 700, color: '#0F172A', lineHeight: 1.2 }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: '#6B7280', marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}
