interface KpiCardProps {
  title: string;
  value: string | number;
  description?: string;
  accentColor?: string;
}

export function KpiCard({
  title,
  value,
  description,
  accentColor = "#F97316",
}: KpiCardProps) {
  return (
    <div
      className="bg-white border border-[#E5E7EB] rounded-lg overflow-hidden"
      style={{ borderTop: `3px solid ${accentColor}` }}
    >
      <div className="px-4 py-4">
        <p className="text-[12px] font-semibold text-[#6B7280] mb-1">{title}</p>
        <p className="text-[22px] font-bold text-[#0F172A] leading-tight">{value}</p>
        {description && (
          <p className="text-[11px] text-[#9CA3AF] mt-1">{description}</p>
        )}
      </div>
    </div>
  );
}
