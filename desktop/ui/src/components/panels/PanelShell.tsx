import { cn } from '@/lib/utils'

interface PanelShellProps {
  title: string
  desc: string
  children: React.ReactNode
  className?: string
}

export function PanelShell({ title, desc, children, className }: PanelShellProps) {
  return (
    <div className={cn('flex-1 overflow-y-auto scrollbar-thin bg-[#FAFAFA]', className)}>
      <div className="max-w-2xl px-8 py-8">
        <div className="mb-6 pb-5 border-b border-zinc-200">
          <h2 className="text-[17px] font-bold text-zinc-900 mb-1.5">{title}</h2>
          <p className="text-[13px] text-zinc-500 leading-relaxed">{desc}</p>
        </div>
        {children}
      </div>
    </div>
  )
}

export function EmptyState({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="py-12">
      <p className="text-[14px] font-semibold text-zinc-500 mb-1.5">{title}</p>
      <p className="text-[12px] text-zinc-400 leading-relaxed">{desc}</p>
    </div>
  )
}

export function HelpSection({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-white border border-zinc-200 rounded-lg p-5 shadow-sm">
      {children}
    </div>
  )
}

export function HelpTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold uppercase tracking-widest text-zinc-400 mb-3">
      {children}
    </p>
  )
}

export function HelpList({ items }: { items: string[] }) {
  return (
    <ul className="mt-3 space-y-1.5 pl-4">
      {items.map(item => (
        <li key={item} className="text-[13px] text-zinc-700 italic list-disc marker:text-[#f97316]">
          "{item}"
        </li>
      ))}
    </ul>
  )
}

export function HelpNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] text-zinc-400 mt-3 leading-relaxed">{children}</p>
  )
}

export function StatusCard({ rows }: { rows: { label: string; value: string; id?: string }[] }) {
  return (
    <div className="bg-white border border-zinc-200 rounded-lg overflow-hidden shadow-sm">
      {rows.map((row, i) => (
        <div key={row.label} className={cn(
          'flex items-center justify-between px-4 py-3 text-[13px]',
          i < rows.length - 1 && 'border-b border-zinc-100'
        )}>
          <span className="text-zinc-500">{row.label}</span>
          <span id={row.id} className="text-zinc-900 font-medium tabular-nums">{row.value}</span>
        </div>
      ))}
    </div>
  )
}
