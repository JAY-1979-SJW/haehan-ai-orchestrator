import type { SafetyPolicyNotice } from "../lib/types";

const LEVEL_STYLE: Record<SafetyPolicyNotice["level"], string> = {
  block: "border-red-200 bg-red-50",
  warn: "border-yellow-200 bg-yellow-50",
  info: "border-blue-200 bg-blue-50",
};

const LEVEL_ICON: Record<SafetyPolicyNotice["level"], string> = {
  block: "🔒",
  warn: "⚠️",
  info: "ℹ️",
};

const LEVEL_TITLE_COLOR: Record<SafetyPolicyNotice["level"], string> = {
  block: "text-red-800",
  warn: "text-yellow-800",
  info: "text-blue-800",
};

export function SafetyPolicyBanner({ policies }: { policies: SafetyPolicyNotice[] }) {
  return (
    <section data-testid="safety-policy-section">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">안전 정책 고지</h2>
      <div className="space-y-2">
        {policies.map((p) => (
          <div
            key={p.id}
            className={`rounded-lg border p-3 ${LEVEL_STYLE[p.level]}`}
          >
            <div className={`flex items-center gap-1.5 text-xs font-semibold ${LEVEL_TITLE_COLOR[p.level]}`}>
              <span>{LEVEL_ICON[p.level]}</span>
              <span>{p.title}</span>
            </div>
            <p className="mt-1 text-xs text-gray-600">{p.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
