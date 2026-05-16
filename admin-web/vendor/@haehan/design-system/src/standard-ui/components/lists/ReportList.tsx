/** ReportList — 보고서 목록 */
import React from 'react';

export interface ReportListItem {
  title: string;
  path?: string;
  date?: string;
  category?: string;
  href?: string;
}

export interface ReportListProps {
  items: ReportListItem[];
  emptyMessage?: string;
  onItemClick?: (item: ReportListItem) => void;
}

export function ReportList({ items, emptyMessage = '보고서가 없습니다.', onItemClick }: ReportListProps) {
  if (items.length === 0) {
    return <div style={{ padding: '24px', textAlign: 'center', color: '#6B7280', fontSize: 13 }}>{emptyMessage}</div>;
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {items.map((item, i) => (
        <div
          key={i}
          role={onItemClick ? 'button' : undefined}
          tabIndex={onItemClick ? 0 : undefined}
          onClick={() => onItemClick?.(item)}
          onKeyDown={(e) => { if (onItemClick && (e.key === 'Enter' || e.key === ' ')) onItemClick(item); }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            borderRadius: 6,
            background: '#FFFFFF',
            border: '1px solid #E5E7EB',
            cursor: onItemClick ? 'pointer' : 'default',
            transition: 'background 0.1s',
          }}
          onMouseEnter={(e) => { if (onItemClick) (e.currentTarget as HTMLDivElement).style.background = '#F9FAFB'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = '#FFFFFF'; }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {item.title}
            </div>
            {item.path && (
              <div style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'monospace', marginTop: 2 }}>{item.path}</div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, marginLeft: 12 }}>
            {item.category && (
              <span style={{ fontSize: 10, background: '#EEF2F7', color: '#1E2D4A', padding: '2px 6px', borderRadius: 9999 }}>
                {item.category}
              </span>
            )}
            {item.date && <span style={{ fontSize: 11, color: '#9CA3AF' }}>{item.date}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
