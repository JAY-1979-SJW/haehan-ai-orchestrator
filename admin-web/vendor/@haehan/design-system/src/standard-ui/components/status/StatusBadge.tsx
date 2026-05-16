/** StatusBadge — 게이트/공정/운영 상태 배지 */
import React from 'react';
import { statusColors } from '../../tokens/colors';

export type StatusValue =
  | 'PASS' | 'DONE'
  | 'WARN' | 'PARTIAL'
  | 'FAIL' | 'MISSING'
  | 'HOLD' | 'BLOCKED'
  | 'LOCAL_AGENT_REQUIRED'
  | 'USER_DIRECT_REQUIRED'
  | 'READ_ONLY_ALLOWED'
  | 'DRAFT_ALLOWED'
  | string;

const STATUS_LABELS: Partial<Record<string, string>> = {
  PASS:                 'PASS',
  DONE:                 '완료',
  WARN:                 'WARN',
  PARTIAL:              '진행중',
  FAIL:                 'FAIL',
  MISSING:              '누락',
  HOLD:                 'HOLD',
  BLOCKED:              '차단',
  LOCAL_AGENT_REQUIRED: 'LOCAL AGENT',
  USER_DIRECT_REQUIRED: '직접 실행',
  READ_ONLY_ALLOWED:    '읽기 허용',
  DRAFT_ALLOWED:        '초안 허용',
};

export interface StatusBadgeProps {
  status: StatusValue;
  label?: string;
  size?: 'sm' | 'md';
}

export function StatusBadge({ status, label, size = 'md' }: StatusBadgeProps) {
  const style = statusColors[status] ?? { bg: '#F3F4F6', text: '#4B5563' };
  const displayLabel = label ?? STATUS_LABELS[status] ?? status;
  const fontSize = size === 'sm' ? 10 : 11;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: size === 'sm' ? '1px 6px' : '2px 8px',
        borderRadius: 9999,
        fontSize,
        fontWeight: 600,
        whiteSpace: 'nowrap',
        background: style.bg,
        color: style.text,
        letterSpacing: '0.02em',
      }}
    >
      {displayLabel}
    </span>
  );
}
