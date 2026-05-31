import { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** padding 제거 (커스텀 padding이 필요한 경우) */
  noPadding?: boolean;
}

/**
 * 공통 카드 컴포넌트.
 * 스펙: white 배경 + #E5E7EB border + rounded-2xl + p-5
 * 모든 카드는 이 컴포넌트를 사용해 시각적 일관성을 유지합니다.
 */
export function Card({ noPadding = false, className = "", children, ...rest }: CardProps) {
  return (
    <div
      className={[
        "bg-white border border-[#E5E7EB] rounded-2xl",
        noPadding ? "" : "p-5",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </div>
  );
}
