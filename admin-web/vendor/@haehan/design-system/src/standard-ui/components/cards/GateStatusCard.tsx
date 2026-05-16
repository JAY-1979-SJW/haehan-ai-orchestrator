/** GateStatusCard — 게이트 판정 결과 카드 */
import React from 'react';
import { StatusBadge, StatusValue } from '../status/StatusBadge';

export interface GateStatusCardProps {
  gateName: string;
  decision: StatusValue;
  reason?: string;
  count?: number;
  detail?: string;
}

export function GateStatusCard({ gateName, decision, reason, count, detail }: GateStatusCardProps) {
  return (
    <div style={{
      background: '#FFFFFF',
      border: '1px solid #E5E7EB',
      borderRadius: 8,
      padding: '14px 18px',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>{gateName}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {count !== undefined && (
            <span style={{ fontSize: 12, fontWeight: 700, color: '#0F172A' }}>{count}</span>
          )}
          <StatusBadge status={decision} />
        </div>
      </div>
      {reason && <p style={{ fontSize: 12, color: '#6B7280', margin: 0 }}>{reason}</p>}
      {detail && <p style={{ fontSize: 11, color: '#9CA3AF', margin: 0 }}>{detail}</p>}
    </div>
  );
}
