/** ApprovalQueueList — 승인 대기 큐 목록 */
import React from 'react';
import { StatusBadge, StatusValue } from '../status/StatusBadge';

export interface ApprovalQueueItem {
  id: string;
  title: string;
  status: StatusValue;
  requestedAt?: string;
  requester?: string;
  description?: string;
}

export interface ApprovalQueueListProps {
  items: ApprovalQueueItem[];
  emptyMessage?: string;
  onItemClick?: (item: ApprovalQueueItem) => void;
}

export function ApprovalQueueList({ items, emptyMessage = '대기 항목이 없습니다.', onItemClick }: ApprovalQueueListProps) {
  if (items.length === 0) {
    return <div style={{ padding: '24px', textAlign: 'center', color: '#6B7280', fontSize: 13 }}>{emptyMessage}</div>;
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {items.map((item) => (
        <div
          key={item.id}
          role={onItemClick ? 'button' : undefined}
          tabIndex={onItemClick ? 0 : undefined}
          onClick={() => onItemClick?.(item)}
          style={{
            padding: '12px 16px',
            borderRadius: 6,
            background: '#FFFFFF',
            border: '1px solid #E5E7EB',
            cursor: onItemClick ? 'pointer' : 'default',
            transition: 'background 0.1s',
          }}
          onMouseEnter={(e) => { if (onItemClick) (e.currentTarget as HTMLDivElement).style.background = '#F9FAFB'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = '#FFFFFF'; }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: '#0F172A' }}>{item.title}</span>
            <StatusBadge status={item.status} />
          </div>
          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#9CA3AF' }}>
            {item.requester && <span>요청자: {item.requester}</span>}
            {item.requestedAt && <span>{item.requestedAt}</span>}
          </div>
          {item.description && (
            <p style={{ fontSize: 12, color: '#6B7280', margin: '6px 0 0', lineHeight: 1.5 }}>{item.description}</p>
          )}
        </div>
      ))}
    </div>
  );
}
