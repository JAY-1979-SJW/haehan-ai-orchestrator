import { ButtonHTMLAttributes } from "react";

type BtnVariant = "orange" | "primary" | "secondary" | "danger" | "success" | "ghost";
type BtnSize = "xs" | "sm" | "md";

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BtnVariant;
  size?: BtnSize;
}

const variantClasses: Record<BtnVariant, string> = {
  orange:    "bg-[#F97316] text-white hover:bg-[#EA580C] border border-[#F97316]",
  primary:   "bg-[#1D4ED8] text-white hover:bg-[#1E40AF] border border-[#1D4ED8]",
  secondary: "bg-white text-[#374151] hover:bg-[#F9FAFB] border border-[#E5E7EB]",
  danger:    "bg-[#B91C1C] text-white hover:bg-[#991B1B] border border-[#B91C1C]",
  success:   "bg-[#059669] text-white hover:bg-[#047857] border border-[#059669]",
  ghost:     "bg-transparent text-[#6B7280] hover:bg-[#F3F4F6] border border-transparent",
};

const sizeClasses: Record<BtnSize, string> = {
  xs: "text-[11px] px-2 py-[3px] rounded",
  sm: "text-[12px] px-3 py-1 rounded",
  md: "text-[13px] px-4 py-[7px] rounded-md",
};

export function Btn({
  variant = "secondary",
  size = "md",
  disabled,
  className = "",
  children,
  ...rest
}: BtnProps) {
  return (
    <button
      disabled={disabled}
      className={[
        "inline-flex items-center justify-center font-semibold transition-colors",
        variantClasses[variant],
        sizeClasses[size],
        disabled ? "opacity-40 cursor-not-allowed pointer-events-none" : "cursor-pointer",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}
