/** 등록코드 — TTL옵션·상태배지 데이터 */

export const TTL_OPTIONS = [
  { value: 10, label: "10분" },
  { value: 30, label: "30분" },
  { value: 60, label: "1시간" },
  { value: 240, label: "4시간" },
  { value: 1440, label: "24시간" },
];

export const STATUS_BADGE: Record<string, { label: string; classes: string }> = {
  active:  { label: "활성",   classes: "bg-[#ECFDF5] text-[#059669] border-[#6EE7B7]" },
  used:    { label: "사용됨", classes: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]" },
  expired: { label: "만료",   classes: "bg-[#F9FAFB] text-[#6B7280] border-[#D1D5DB]" },
  revoked: { label: "폐기",   classes: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" },
};

