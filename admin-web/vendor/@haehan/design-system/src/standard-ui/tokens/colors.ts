/** 표준 UI 색상 토큰 — 모델하우스(23. 입찰 조회 및 분석) 기준 추출 */
export const colors = {
  // Primary — Orange accent
  primaryOrange:      '#F97316',
  primaryOrangeHover: '#EA580C',
  primaryOrangeSoft:  '#FFF7ED',

  // Primary — Navy
  navyBase:    '#1E2D4A',
  navyHover:   '#253661',
  navySurface: '#1E293B',
  navySoft:    '#EEF2F7',

  // Background
  bgBase:    '#F5F7FA',
  bgHover:   '#F0F2F5',
  bgCard:    '#FFFFFF',
  bgSubtle:  '#F9FAFB',

  // Text
  textPrimary:   '#0F172A',
  textSecondary: '#374151',
  textMuted:     '#6B7280',
  textPlaceholder: '#9CA3AF',

  // Border
  borderDefault: '#E5E7EB',
  borderStrong:  '#D1D5DB',
  borderSoft:    '#F3F4F6',

  // Status — semantic
  success:   '#059669',
  successBg: '#ECFDF5',
  warning:   '#D97706',
  warningBg: '#FFFBEB',
  error:     '#DC2626',
  errorBg:   '#FEF2F2',
  info:      '#2563EB',
  infoBg:    '#EFF6FF',
} as const;

/** 게이트/공정 상태 색상 */
export const statusColors: Record<string, { bg: string; text: string; border?: string }> = {
  PASS:                 { bg: '#ECFDF5', text: '#065F46' },
  DONE:                 { bg: '#ECFDF5', text: '#065F46' },
  WARN:                 { bg: '#FFFBEB', text: '#92400E' },
  PARTIAL:              { bg: '#FFF7ED', text: '#C2410C' },
  FAIL:                 { bg: '#FEF2F2', text: '#B91C1C' },
  MISSING:              { bg: '#F3F4F6', text: '#4B5563' },
  HOLD:                 { bg: '#F3F4F6', text: '#4B5563' },
  BLOCKED:              { bg: '#FEF2F2', text: '#B91C1C' },
  LOCAL_AGENT_REQUIRED: { bg: '#EFF6FF', text: '#1E40AF' },
  USER_DIRECT_REQUIRED: { bg: '#F3F4F6', text: '#374151' },
  READ_ONLY_ALLOWED:    { bg: '#ECFDF5', text: '#065F46' },
  DRAFT_ALLOWED:        { bg: '#FFF7ED', text: '#C2410C' },
};
