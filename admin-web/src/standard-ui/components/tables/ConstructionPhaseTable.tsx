/** ConstructionPhaseTable — 공정표 단계별 현황 테이블 */
import React from 'react';
import { StatusBadge, StatusValue } from '../status/StatusBadge';

export interface ConstructionPhaseRow {
  phase: string;
  code?: string;
  status: StatusValue;
  completedAt?: string;
  notes?: string;
}

export interface ConstructionPhaseTableProps {
  rows: ConstructionPhaseRow[];
  emptyMessage?: string;
}

export function ConstructionPhaseTable({ rows, emptyMessage = '공정 데이터가 없습니다.' }: ConstructionPhaseTableProps) {
  return (
    <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid #E5E7EB' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ background: '#F9FAFB', borderBottom: '1px solid #E5E7EB' }}>
            <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: '#374151', fontSize: 12 }}>단계</th>
            <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: '#374151', fontSize: 12 }}>코드</th>
            <th style={{ padding: '10px 14px', textAlign: 'center', fontWeight: 600, color: '#374151', fontSize: 12 }}>상태</th>
            <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: '#374151', fontSize: 12 }}>완료일</th>
            <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: '#374151', fontSize: 12 }}>비고</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: '#6B7280' }}>{emptyMessage}</td></tr>
          ) : rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #F3F4F6' }}>
              <td style={{ padding: '10px 14px', color: '#0F172A', fontWeight: 500 }}>{row.phase}</td>
              <td style={{ padding: '10px 14px', color: '#6B7280', fontFamily: 'monospace', fontSize: 12 }}>{row.code ?? '—'}</td>
              <td style={{ padding: '10px 14px', textAlign: 'center' }}><StatusBadge status={row.status} /></td>
              <td style={{ padding: '10px 14px', color: '#6B7280', fontSize: 12 }}>{row.completedAt ?? '—'}</td>
              <td style={{ padding: '10px 14px', color: '#6B7280', fontSize: 12 }}>{row.notes ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
