/** DomainUnitCard — 도메인 세대/유닛 요약 카드 (이름 + 상태 + 설명 + 메트릭) */
import React from 'react';
import { StatusBadge, StatusValue } from '../status/StatusBadge';

export interface DomainUnitCardProps {
  name: string;
  status: StatusValue;
  description?: string;
  metrics?: Array<{ label: string; value: string | number }>;
  actions?: React.ReactNode;
  onClick?: () => void;
}

export function DomainUnitCard({ name, status, description, metrics, actions, onClick }: DomainUnitCardProps) {
  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      style={{
        background: '#FFFFFF',
        border: '1px solid #E5E7EB',
        borderRadius: 8,
        padding: '16px 20px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'box-shadow 0.15s',
      }}
      onMouseEnter={(e) => { if (onClick) (e.currentTarget as HTMLDivElement).style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.boxShadow = 'none'; }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#0F172A' }}>{name}</span>
        <StatusBadge status={status} />
      </div>
      {description && (
        <p style={{ fontSize: 12, color: '#6B7280', margin: '0 0 10px', lineHeight: 1.5 }}>{description}</p>
      )}
      {metrics && metrics.length > 0 && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 8 }}>
          {metrics.map((m, i) => (
            <div key={i} style={{ fontSize: 11, color: '#6B7280' }}>
              <span style={{ color: '#0F172A', fontWeight: 600, marginRight: 4 }}>{m.value}</span>
              {m.label}
            </div>
          ))}
        </div>
      )}
      {actions && <div style={{ marginTop: 12 }}>{actions}</div>}
    </div>
  );
}
