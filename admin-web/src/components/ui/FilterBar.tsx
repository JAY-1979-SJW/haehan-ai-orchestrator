import { ReactNode, SelectHTMLAttributes } from "react";

export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      {children}
    </div>
  );
}

interface FilterSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
}

export function FilterSelect({ label, className = "", children, ...rest }: FilterSelectProps) {
  return (
    <label className="flex items-center gap-1.5">
      {label && (
        <span className="text-[12px] text-[#6B7280] whitespace-nowrap">{label}</span>
      )}
      <select
        className={[
          "text-[12px] text-[#374151] bg-white border border-[#E5E7EB] rounded px-2 py-1",
          "focus:outline-none focus:ring-1 focus:ring-[#F97316]",
          className,
        ].join(" ")}
        {...rest}
      >
        {children}
      </select>
    </label>
  );
}

interface FilterPillProps {
  active?: boolean;
  onClick?: () => void;
  children: ReactNode;
}

export function FilterPill({ active = false, onClick, children }: FilterPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "text-[12px] font-semibold px-3 py-1 rounded-full border transition-colors",
        active
          ? "bg-[#F97316] text-white border-[#F97316]"
          : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F9FAFB]",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export function FilterSpacer() {
  return <div className="flex-1" />;
}
