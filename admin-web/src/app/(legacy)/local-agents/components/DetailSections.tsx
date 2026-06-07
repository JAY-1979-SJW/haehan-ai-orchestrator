import type { ObserveSummary, AuditSummary } from "@/types/local-agent";

export interface DetailRowProps {
  label: string;
  value: string;
  mono?: boolean;
  danger?: boolean;
}

export function DetailRow({ label, value, mono, danger }: DetailRowProps) {
  return (
    <div className="flex items-start gap-2">
      <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">{label}</div>
      <div
        className={[
          "flex-1 break-all",
          mono ? "font-mono text-[12px]" : "text-[13px]",
          danger ? "text-[#B91C1C]" : "text-[#111827]",
        ].join(" ")}
      >
        {value}
      </div>
    </div>
  );
}

const _STATUS_BADGE_COLOR: Record<string, string> = {
  ok: "bg-[#D1FAE5] text-[#065F46]",
  blocked: "bg-[#FEE2E2] text-[#B91C1C]",
  failed: "bg-[#FEE2E2] text-[#B91C1C]",
};

const _PSC_KEYS = [
  "headings", "links", "buttons", "inputs", "forms", "tables",
] as const;

export function ObserveSummarySection({ obs }: { obs: ObserveSummary }) {
  const statusColor =
    _STATUS_BADGE_COLOR[obs.status_category ?? ""] ??
    "bg-[#F3F4F6] text-[#6B7280]";

  const psc = obs.page_structure_counts;
  const pscItems =
    psc && typeof psc === "object"
      ? _PSC_KEYS.flatMap((k) => {
          const v = psc[k];
          return typeof v === "number" ? [{ k, v }] : [];
        })
      : [];

  return (
    <div className="mt-3 pt-3 border-t border-[#E5E7EB]">
      <div className="mb-2 text-[12px] font-semibold text-[#374151]">관찰 요약</div>
      <div className="space-y-1.5">
        {obs.status_category && (
          <div className="flex items-start gap-2">
            <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">상태</div>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${statusColor}`}
            >
              {obs.status_category}
            </span>
          </div>
        )}
        {obs.title && (
          <DetailRow label="페이지 제목" value={obs.title} />
        )}
        {obs.url_category && (
          <DetailRow label="URL 분류" value={obs.url_category} mono />
        )}
        {obs.final_url_sanitized && (
          <DetailRow label="최종 URL" value={obs.final_url_sanitized} mono />
        )}
        {obs.login_required_hint === true && (
          <DetailRow label="로그인 감지" value="로그인 필요 가능성 있음" />
        )}
        {obs.pages_observed_count !== null &&
          obs.pages_observed_count !== undefined && (
          <DetailRow
            label="관찰 페이지"
            value={String(obs.pages_observed_count)}
          />
        )}
        {obs.modal_candidates_count !== null &&
          obs.modal_candidates_count !== undefined && (
          <DetailRow
            label="모달 후보"
            value={String(obs.modal_candidates_count)}
          />
        )}
        {typeof obs.html_truncated === "boolean" && (
          <DetailRow
            label="HTML 축약"
            value={obs.html_truncated ? "예" : "아니오"}
          />
        )}
        {pscItems.length > 0 && (
          <div className="flex items-start gap-2">
            <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">
              페이지 구조
            </div>
            <div className="flex flex-wrap gap-1.5">
              {pscItems.map(({ k, v }) => (
                <span
                  key={k}
                  className="font-mono text-[11px] bg-[#F3F4F6] text-[#374151] px-1.5 py-0.5 rounded"
                >
                  {k}={v}
                </span>
              ))}
            </div>
          </div>
        )}
        {obs.error_category && (
          <DetailRow label="오류 분류" value={obs.error_category} danger />
        )}
        {obs.blocked_reason && (
          <DetailRow label="차단 사유" value={obs.blocked_reason} danger />
        )}
        {obs.observed_at && (
          <DetailRow label="관찰 시각" value={obs.observed_at} />
        )}
      </div>
    </div>
  );
}

const _AUDIT_DICT_KEYS = ["policy_decision_counts", "target_kind_counts", "action_kind_counts"] as const;

export function AuditSummarySection({ audit }: { audit: AuditSummary }) {
  const countFields = [
    { label: "감사 이벤트", key: "audit_event_count" as const },
    { label: "허용됨", key: "allowed_event_count" as const },
    { label: "차단됨", key: "blocked_event_count" as const },
    { label: "거절됨", key: "denied_event_count" as const },
    { label: "오류", key: "error_event_count" as const },
  ];

  const countItems = countFields.flatMap(({ label, key }) => {
    const v = audit[key];
    return typeof v === "number" ? [{ label, value: v }] : [];
  });

  const categories = Array.isArray(audit.audit_event_categories)
    ? audit.audit_event_categories.filter((c) => typeof c === "string")
    : [];

  const dictItems = _AUDIT_DICT_KEYS.flatMap((key) => {
    const dict = audit[key];
    if (!dict || typeof dict !== "object") return [];
    const pairs = Object.entries(dict)
      .filter(([_, v]) => typeof v === "number")
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    return pairs.length > 0 ? [{ label: key.replace(/_/g, " "), pairs }] : [];
  });

  return (
    <div className="mt-3 pt-3 border-t border-[#E5E7EB]">
      <div className="mb-2 text-[12px] font-semibold text-[#374151]">감사 요약</div>
      <div className="space-y-1.5">
        {(audit.audit_window_started_at || audit.audit_window_ended_at) && (
          <>
            {audit.audit_window_started_at && (
              <DetailRow label="감사 시작" value={audit.audit_window_started_at} />
            )}
            {audit.audit_window_ended_at && (
              <DetailRow label="감사 종료" value={audit.audit_window_ended_at} />
            )}
          </>
        )}

        {countItems.length > 0 && (
          <div className="flex items-start gap-2">
            <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">
              이벤트 수
            </div>
            <div className="flex flex-wrap gap-2">
              {countItems.map(({ label, value }) => (
                <span
                  key={label}
                  className="font-mono text-[11px] bg-[#F3F4F6] text-[#374151] px-1.5 py-0.5 rounded"
                >
                  {label}: {value}
                </span>
              ))}
            </div>
          </div>
        )}

        {audit.last_event_category && (
          <DetailRow label="마지막 분류" value={audit.last_event_category} mono />
        )}
        {audit.last_event_status && (
          <DetailRow label="마지막 상태" value={audit.last_event_status} mono />
        )}

        {categories.length > 0 && (
          <div className="flex items-start gap-2">
            <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">
              분류 목록
            </div>
            <div className="flex flex-wrap gap-1.5">
              {categories.map((cat) => (
                <span
                  key={cat}
                  className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#F3F4F6] text-[#374151]"
                >
                  {cat}
                </span>
              ))}
            </div>
          </div>
        )}

        {dictItems.length > 0 && (
          dictItems.map(({ label, pairs }) => (
            <div key={label} className="flex items-start gap-2">
              <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">
                {label}
              </div>
              <div className="font-mono text-[11px] bg-[#F3F4F6] text-[#374151] px-2 py-1 rounded break-all">
                {pairs}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
