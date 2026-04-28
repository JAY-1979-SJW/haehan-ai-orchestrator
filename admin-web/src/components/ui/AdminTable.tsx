import { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

export function AdminTable({ className = "", children, ...rest }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table
        className={["w-full border-collapse text-left border border-[#E5E7EB]", className].join(" ")}
        {...rest}
      >
        {children}
      </table>
    </div>
  );
}

export function AdminThead({ className = "", children, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead className={["bg-[#F3F4F6]", className].join(" ")} {...rest}>
      {children}
    </thead>
  );
}

export function AdminTbody({ className = "", children, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody className={className} {...rest}>
      {children}
    </tbody>
  );
}

export function AdminTr({ className = "", children, ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={[
        "border-b border-[#E5E7EB] hover:bg-[#F9FAFB] transition-colors",
        className,
      ].join(" ")}
      {...rest}
    >
      {children}
    </tr>
  );
}

export function AdminTh({
  className = "",
  children,
  ...rest
}: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={[
        "text-[11px] font-bold text-[#374151] px-3 py-[10px] whitespace-nowrap",
        className,
      ].join(" ")}
      {...rest}
    >
      {children}
    </th>
  );
}

export function AdminTd({
  className = "",
  children,
  ...rest
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={["text-[13px] text-[#374151] px-3 py-[10px]", className].join(" ")} {...rest}>
      {children}
    </td>
  );
}

export function EmptyRow({ colSpan, message = "데이터 없음" }: { colSpan: number; message?: string }) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className="text-center text-[13px] text-[#9CA3AF] px-3 py-8"
      >
        {message}
      </td>
    </tr>
  );
}
