/** DataTable — 범용 데이터 테이블 */
import React from 'react';

export interface DataTableColumn<T> {
  key: string;
  header: string;
  width?: string | number;
  render?: (row: T, index: number) => React.ReactNode;
  align?: 'left' | 'center' | 'right';
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  keyField?: string;
  emptyMessage?: string;
  loading?: boolean;
  onRowClick?: (row: T) => void;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  keyField = 'id',
  emptyMessage = '데이터가 없습니다.',
  loading = false,
  onRowClick,
}: DataTableProps<T>) {
  return (
    <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid #E5E7EB' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ background: '#F9FAFB', borderBottom: '1px solid #E5E7EB' }}>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  padding: '10px 14px',
                  textAlign: col.align ?? 'left',
                  fontWeight: 600,
                  color: '#374151',
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                  width: col.width,
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={columns.length} style={{ padding: '24px', textAlign: 'center', color: '#6B7280' }}>로딩 중…</td></tr>
          ) : rows.length === 0 ? (
            <tr><td colSpan={columns.length} style={{ padding: '24px', textAlign: 'center', color: '#6B7280' }}>{emptyMessage}</td></tr>
          ) : rows.map((row, i) => (
            <tr
              key={String(row[keyField] ?? i)}
              onClick={() => onRowClick?.(row)}
              style={{
                borderBottom: '1px solid #F3F4F6',
                cursor: onRowClick ? 'pointer' : 'default',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => { if (onRowClick) (e.currentTarget as HTMLTableRowElement).style.background = '#F9FAFB'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = ''; }}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  style={{ padding: '10px 14px', textAlign: col.align ?? 'left', color: '#0F172A' }}
                >
                  {col.render ? col.render(row, i) : String(row[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
