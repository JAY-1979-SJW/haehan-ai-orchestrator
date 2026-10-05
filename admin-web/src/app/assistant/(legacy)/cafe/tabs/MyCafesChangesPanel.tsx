"use client";
/** 카페 탭 — 가입 카페 변동(신규 가입·탈퇴·이름 변경)과 요약. 기준서: docs/specs/2026-10-05_cafe_membership_changes.md */
import type { CafeChangeHistory, CafeChangeResult } from "@/lib/assistant/api";

interface Props {
  latest: CafeChangeResult | null;
  history: CafeChangeHistory | null;
  busy: boolean;
  onConfirm: () => void;
}

const card = "rounded-lg border border-[#E5E7EB] bg-white px-3 py-2";

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className={card}>
      <div className="text-[10px] text-[#6B7280]">{label}</div>
      <div className={`text-base font-semibold ${tone ?? "text-[#111827]"}`}>{value}</div>
    </div>
  );
}

const day = (iso: string) => (iso ? iso.slice(0, 16).replace("T", " ") : "-");

export function MyCafesChangesPanel({ latest, history, busy, onConfirm }: Props) {
  if (!latest && !history) return null;
  const summary = history?.summary;
  const warn = latest && (latest.status === "blocked" || latest.status === "needs_confirmation");
  return (
    <div className="space-y-2 rounded-xl border border-[#E5E7EB] bg-[#F9FAFB] p-3" data-testid="cafe-changes-panel">
      <div className="text-xs font-semibold text-[#111827]">가입 카페 변동</div>
      {warn && latest && (
        <div className="rounded-lg border border-[#FDBA74] bg-[#FFF7ED] p-2 text-xs text-[#9A3412]" role="alert" data-testid="cafe-changes-warning">
          <div>{latest.warning}</div>
          <div className="mt-0.5 text-[11px]">저장된 목록과 이력은 바뀌지 않았습니다.</div>
          {latest.status === "needs_confirmation" && (
            <button
              type="button"
              disabled={busy}
              onClick={onConfirm}
              className="mt-1.5 rounded-lg border border-[#EA580C] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#EA580C] disabled:opacity-50"
            >
              확인했습니다 — 이 결과로 반영
            </button>
          )}
        </div>
      )}
      {latest && latest.status === "baseline" && (
        <p className="text-xs text-[#1D4ED8]">이번 수집을 기준선으로 기록했습니다({latest.total}개). 다음 수집부터 신규 가입·탈퇴가 표시됩니다.</p>
      )}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="총 가입" value={`${summary?.current_total ?? latest?.total ?? 0}개`} />
        <Stat label="이번 신규 가입" value={`${latest && !warn ? latest.new.length : 0}개`} tone="text-[#16A34A]" />
        <Stat label="이번 탈퇴" value={`${latest && !warn ? latest.left.length : 0}개`} tone="text-[#DC2626]" />
        <Stat label="기준선 이후 순증감" value={`${(summary?.net_change_since_first ?? 0) >= 0 ? "+" : ""}${summary?.net_change_since_first ?? 0}`} />
      </div>
      {latest && !warn && (latest.new.length > 0 || latest.left.length > 0 || latest.renamed.length > 0) && (
        <div className="space-y-1 text-xs">
          {latest.new.map((c) => (
            <div key={`n-${c.cafe_id}`} className="text-[#16A34A]">＋ 신규 가입 — {c.name || c.cafe_id}</div>
          ))}
          {latest.left.map((c) => (
            <div key={`l-${c.cafe_id}`} className="text-[#DC2626]">－ 탈퇴 — {c.name || c.cafe_id}</div>
          ))}
          {latest.renamed.map((c) => (
            <div key={`r-${c.cafe_id}`} className="text-[#6B7280]">
              ✎ 이름 변경 — {c.from} → {c.to}
            </div>
          ))}
        </div>
      )}
      {history && history.changes.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-[#6B7280]">최근 변동 기록 {history.changes.length}건 (신규 {summary?.joined_in_log ?? 0} · 탈퇴 {summary?.left_in_log ?? 0})</summary>
          <ul className="mt-1 space-y-0.5">
            {history.changes.map((c) => (
              <li key={c.at} className="text-[11px] text-[#374151]">
                {day(c.at)} · 총 {c.previous_total}→{c.total}개
                {c.new.length > 0 && <span className="text-[#16A34A]"> · 신규 {c.new.map((x) => x.name || x.cafe_id).join(", ")}</span>}
                {c.left.length > 0 && <span className="text-[#DC2626]"> · 탈퇴 {c.left.map((x) => x.name || x.cafe_id).join(", ")}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
