/** WarehouseCard — 공유 창고(Shared Warehouse) 영역 카드 */
import React from 'react';
import { StatusBadge, StatusValue } from '../status/StatusBadge';

export interface WarehouseCardProps {
  title: string;
  path: string;
  status: StatusValue;
  fileCount?: number;
  description?: string;
}

export function WarehouseCard({ title, path, status, fileCount, description }: WarehouseCardProps) {
  return (
    <div style={{
      background: '#FFFFFF',
      border: '1px solid #E5E7EB',
      borderRadius: 8,
      padding: '14px 18px',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>{title}</span>
        <StatusBadge status={status} />
      </div>
      <code style={{ fontSize: 11, color: '#6B7280', background: '#F9FAFB', padding: '2px 6px', borderRadius: 4 }}>
        {path}
      </code>
      {description && <p style={{ fontSize: 12, color: '#6B7280', margin: '8px 0 0', lineHeight: 1.5 }}>{description}</p>}
      {fileCount !== undefined && (
        <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 6 }}>{fileCount}개 파일</div>
      )}
    </div>
  );
}
