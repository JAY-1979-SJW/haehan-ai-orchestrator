interface EmptyStateProps {
  title: string;
  description?: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      <div className="text-[36px] mb-3 select-none text-[#D1D5DB]">—</div>
      <p className="text-[14px] font-semibold text-[#374151]">{title}</p>
      {description && (
        <p className="text-[12px] text-[#9CA3AF] mt-1 max-w-xs">{description}</p>
      )}
    </div>
  );
}
