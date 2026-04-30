/**
 * Risk badge for browser actions (BROWSER-4I)
 *
 * Displays risk level with color coding:
 * - low (green): 낮음
 * - medium (yellow): 보통
 * - high (orange): 높음
 * - critical (red): 위험
 */

interface RiskBadgeProps {
  level: "low" | "medium" | "high" | "critical";
  label?: string;
}

const RISK_CONFIG = {
  low:      { label: "낮음",   emoji: "🟢", classes: "bg-[#ECFDF5] text-[#059669] border-[#6EE7B7]" },
  medium:   { label: "보통",   emoji: "🟡", classes: "bg-[#FFFBEB] text-[#D97706] border-[#FDE68A]" },
  high:     { label: "높음",   emoji: "🟠", classes: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" },
  critical: { label: "위험",   emoji: "🔴", classes: "bg-[#FEE2E2] text-[#991B1B] border-[#FECACA]" },
};

export function RiskBadge({ level, label }: RiskBadgeProps) {
  const config = RISK_CONFIG[level];
  return (
    <span
      className={[
        "inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border",
        config.classes,
      ].join(" ")}
      title={`Risk level: ${level}`}
    >
      <span>{config.emoji}</span>
      <span>{label ?? config.label}</span>
    </span>
  );
}
