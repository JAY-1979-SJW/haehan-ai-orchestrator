"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AdminTable,
  AdminThead,
  AdminTbody,
  AdminTr,
  AdminTh,
  AdminTd,
  EmptyRow,
  StatusBadge,
  Btn,
} from "@/components/ui";
import { Modal } from "@/components/ui/Modal";
import {
  ApiError,
  issueRegistrationCode,
  listRegistrationCodes,
  revokeRegistrationCode,
} from "@/lib/api";
import type { CurrentUser } from "@/types/auth";
import type {
  IssueRegistrationCodeResponse,
  RegistrationAction,
  RegistrationCodeSummary,
} from "@/types/registration-code";

import { TTL_OPTIONS, STATUS_BADGE } from "./registrationCodesData";
function CodeStatusBadge({ status }: { status: string }) {
  const c = STATUS_BADGE[status];
  if (!c) return <StatusBadge status={status} />;
  return (
    <span
      className={[
        "inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full border",
        c.classes,
      ].join(" ")}
    >
      {c.label}
    </span>
  );
}

function authMessage(status: number, role: string | undefined): string {
  if (status === 401) return "로그인이 필요합니다. 브라우저 인증 상태를 확인하세요.";
  if (status === 403) {
    if (role === "viewer") return "조회 전용 권한입니다. admin/owner 권한이 필요합니다.";
    if (!role) return "권한 확인이 필요합니다. admin/owner 권한이 필요합니다.";
    return "권한이 없습니다.";
  }
  return `요청에 실패했습니다. (HTTP ${status})`;
}

function fmtError(err: unknown, role: string | undefined, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 403) return authMessage(err.status, role);
    if (err.status === 400) return "요청이 유효하지 않습니다. (label/expires_in_minutes 확인)";
    if (err.status === 404) return "등록코드를 찾을 수 없습니다.";
    if (err.status === 409) return "이미 처리된 등록코드입니다.";
    return `요청에 실패했습니다. (HTTP ${err.status})`;
  }
  return fallback;
}

function formatExpiresAt(iso: string): string {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("ko-KR");
  } catch {
    return iso;
  }
}

interface IssuedCodePayload {
  code_id: string;
  registration_code: string;
  expires_at: string;
  label: string;
}

interface PanelProps {
  currentUser: CurrentUser | null;
  userLoading: boolean;
  userError: boolean;
}

export default function RegistrationCodesPanel({
  currentUser,
  userLoading,
  userError,
}: PanelProps) {
  const role = currentUser?.role;
  const canManage = !userLoading && (role === "admin" || role === "owner");
  const isViewer = !userLoading && role === "viewer";

  const [codes, setCodes] = useState<RegistrationCodeSummary[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [listAuthBlocked, setListAuthBlocked] = useState<401 | 403 | null>(null);

  const [label, setLabel] = useState("");
  const [ttl, setTtl] = useState<number>(30);
  const [allowOpenUrl, setAllowOpenUrl] = useState(true);
  const [allowCapture, setAllowCapture] = useState(false);
  const [note, setNote] = useState("");
  const [issuing, setIssuing] = useState(false);
  const [issueError, setIssueError] = useState<string | null>(null);

  // Issued-code modal state. registration_code 평문은 modal 닫는 즉시 clear.
  const [issued, setIssued] = useState<IssuedCodePayload | null>(null);
  const [copied, setCopied] = useState(false);

  // Revoke confirm
  const [revokeTarget, setRevokeTarget] = useState<RegistrationCodeSummary | null>(null);
  const [revoking, setRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    setListAuthBlocked(null);
    try {
      const res = await listRegistrationCodes();
      setCodes(res.codes ?? []);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        setListAuthBlocked(err.status);
        setCodes([]);
      } else {
        setListError(fmtError(err, role, "등록코드 목록을 불러오지 못했습니다."));
      }
    } finally {
      setListLoading(false);
    }
  }, [role]);

  useEffect(() => {
    if (userLoading) return;
    if (userError) return;
    if (!canManage && !isViewer) return;
    if (isViewer) return; // viewer는 list endpoint 호출해도 403이므로 호출 자체 생략
    void refresh();
  }, [userLoading, userError, canManage, isViewer, refresh]);

  function resetForm() {
    setLabel("");
    setTtl(30);
    setAllowOpenUrl(true);
    setAllowCapture(false);
    setNote("");
    setIssueError(null);
  }

  async function handleIssue(e: React.FormEvent) {
    e.preventDefault();
    if (!canManage) return;
    const trimmed = label.trim();
    if (!trimmed) {
      setIssueError("label은 필수입니다.");
      return;
    }
    if (trimmed.length > 80) {
      setIssueError("label은 최대 80자입니다.");
      return;
    }
    if (note.length > 200) {
      setIssueError("note는 최대 200자입니다.");
      return;
    }
    const allowed: RegistrationAction[] = [];
    if (allowOpenUrl) allowed.push("open_url");
    if (allowCapture) allowed.push("capture_screenshot");
    if (allowed.length === 0) {
      setIssueError("허용 작업을 1개 이상 선택하세요.");
      return;
    }
    setIssuing(true);
    setIssueError(null);
    try {
      const res: IssueRegistrationCodeResponse = await issueRegistrationCode({
        label: trimmed,
        expires_in_minutes: ttl,
        allowed_actions: allowed,
        note: note.trim() || undefined,
      });
      setIssued({
        code_id: res.code_id,
        registration_code: res.registration_code,
        expires_at: res.expires_at,
        label: res.label,
      });
      resetForm();
      void refresh();
    } catch (err) {
      setIssueError(fmtError(err, role, "발급에 실패했습니다."));
    } finally {
      setIssuing(false);
    }
  }

  function handleCloseIssuedModal() {
    setIssued(null);
    setCopied(false);
  }

  async function handleCopy() {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.registration_code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function handleConfirmRevoke() {
    if (!revokeTarget) return;
    setRevoking(true);
    setRevokeError(null);
    try {
      await revokeRegistrationCode(revokeTarget.code_id);
      setRevokeTarget(null);
      void refresh();
    } catch (err) {
      setRevokeError(fmtError(err, role, "폐기에 실패했습니다."));
    } finally {
      setRevoking(false);
    }
  }

  return (
    <section className="mt-8 border border-[#E5E7EB] rounded-md bg-white">
      <header className="flex items-center justify-between px-4 py-3 border-b border-[#E5E7EB]">
        <div>
          <h2 className="text-[14px] font-bold text-[#0F172A]">데스크톱 Agent 등록코드</h2>
          <p className="text-[11px] text-[#6B7280] mt-0.5">
            등록코드 평문은 발급 직후 1회만 표시됩니다. 페이지에는 저장되지 않습니다.
          </p>
        </div>
        <Btn variant="secondary" size="sm" onClick={() => void refresh()} disabled={listLoading || isViewer}>
          {listLoading ? "불러오는 중…" : "새로고침"}
        </Btn>
      </header>

      {/* 권한/인증 안내 */}
      {userLoading && (
        <div className="px-4 py-3 text-[12px] text-[#6B7280]">권한 확인 중…</div>
      )}
      {!userLoading && userError && (
        <div className="px-4 py-3 text-[12px] text-[#B91C1C] bg-[#FEF2F2] border-b border-[#FECACA]">
          권한 확인에 실패했습니다. 인증 상태를 확인하고 새로고침하세요.
        </div>
      )}
      {!userLoading && !userError && isViewer && (
        <div className="px-4 py-3 text-[12px] text-[#92400E] bg-[#FFFBEB] border-b border-[#FDE68A]">
          조회 전용 권한입니다. 등록코드 발급/폐기는 admin/owner 권한이 필요합니다.
        </div>
      )}
      {listAuthBlocked && (
        <div className="px-4 py-3 text-[12px] text-[#B91C1C] bg-[#FEF2F2] border-b border-[#FECACA]">
          {authMessage(listAuthBlocked, role)}
        </div>
      )}

      {/* 발급 폼 */}
      {canManage && (
        <form onSubmit={handleIssue} className="px-4 py-4 border-b border-[#E5E7EB] space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="block text-[12px] text-[#374151]">
              <span className="block mb-1 font-semibold">label *</span>
              <input
                type="text"
                value={label}
                maxLength={80}
                onChange={(e) => { setLabel(e.target.value); setIssueError(null); }}
                placeholder="예: jay-laptop-2026q2"
                className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-[#F97316]"
              />
              <span className="block mt-1 text-[11px] text-[#9CA3AF]">{label.length}/80</span>
            </label>

            <label className="block text-[12px] text-[#374151]">
              <span className="block mb-1 font-semibold">유효기간</span>
              <select
                value={ttl}
                onChange={(e) => setTtl(Number(e.target.value))}
                className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-[#F97316]"
              >
                {TTL_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>
          </div>

          <fieldset className="text-[12px] text-[#374151]">
            <legend className="font-semibold mb-1">허용 작업 (1개 이상)</legend>
            <div className="flex flex-wrap gap-3">
              <label className="inline-flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={allowOpenUrl}
                  onChange={(e) => setAllowOpenUrl(e.target.checked)}
                />
                <span>open_url</span>
              </label>
              <label className="inline-flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={allowCapture}
                  onChange={(e) => setAllowCapture(e.target.checked)}
                />
                <span>capture_screenshot</span>
              </label>
            </div>
          </fieldset>

          <label className="block text-[12px] text-[#374151]">
            <span className="block mb-1 font-semibold">메모 (선택)</span>
            <textarea
              value={note}
              maxLength={200}
              rows={2}
              onChange={(e) => setNote(e.target.value)}
              placeholder="감사 로그용 짧은 메모"
              className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-[13px] resize-none focus:outline-none focus:ring-1 focus:ring-[#F97316]"
            />
            <span className="block mt-1 text-[11px] text-[#9CA3AF]">{note.length}/200</span>
          </label>

          {issueError && (
            <p className="text-[12px] text-[#B91C1C]">{issueError}</p>
          )}

          <div className="flex justify-end">
            <Btn type="submit" variant="orange" size="sm" disabled={issuing}>
              {issuing ? "발급 중…" : "등록코드 발급"}
            </Btn>
          </div>
        </form>
      )}

      {/* 목록 */}
      <div className="p-4">
        {listError && (
          <p className="mb-2 text-[12px] text-[#B91C1C]">{listError}</p>
        )}
        {!isViewer && (
          <AdminTable>
            <AdminThead>
              <AdminTr>
                <AdminTh>code_id</AdminTh>
                <AdminTh>label</AdminTh>
                <AdminTh>status</AdminTh>
                <AdminTh>allowed_actions</AdminTh>
                <AdminTh>expires_at</AdminTh>
                <AdminTh>used_at</AdminTh>
                <AdminTh>used_by_agent</AdminTh>
                <AdminTh>action</AdminTh>
              </AdminTr>
            </AdminThead>
            <AdminTbody>
              {codes.length === 0 ? (
                <EmptyRow colSpan={8} message={listLoading ? "불러오는 중…" : "등록코드 없음"} />
              ) : (
                codes.map((c) => (
                  <AdminTr key={c.code_id}>
                    <AdminTd className="font-mono text-[12px]">{c.code_id}</AdminTd>
                    <AdminTd>{c.label || "-"}</AdminTd>
                    <AdminTd><CodeStatusBadge status={c.status} /></AdminTd>
                    <AdminTd className="text-[12px]">
                      {c.allowed_actions.length ? c.allowed_actions.join(", ") : "-"}
                    </AdminTd>
                    <AdminTd className="text-[12px]">{formatExpiresAt(c.expires_at)}</AdminTd>
                    <AdminTd className="text-[12px]">{c.used_at ? formatExpiresAt(c.used_at) : "-"}</AdminTd>
                    <AdminTd className="font-mono text-[12px]">{c.used_by_agent_id || "-"}</AdminTd>
                    <AdminTd>
                      {canManage && c.status === "active" ? (
                        <Btn
                          variant="danger"
                          size="xs"
                          onClick={() => { setRevokeTarget(c); setRevokeError(null); }}
                        >
                          폐기
                        </Btn>
                      ) : (
                        <span className="text-[11px] text-[#9CA3AF]">-</span>
                      )}
                    </AdminTd>
                  </AdminTr>
                ))
              )}
            </AdminTbody>
          </AdminTable>
        )}
      </div>

      {/* Issued-code modal — registration_code 평문 1회 표시 */}
      <Modal
        open={issued !== null}
        title="등록코드 발급 완료"
        onClose={handleCloseIssuedModal}
        footer={
          <Btn variant="secondary" size="sm" onClick={handleCloseIssuedModal}>
            닫기 (코드 폐기)
          </Btn>
        }
      >
        {issued && (
          <div className="space-y-3">
            <div className="rounded-md bg-[#FFFBEB] border border-[#FDE68A] px-3 py-2 text-[12px] text-[#92400E]">
              이 코드는 이 화면에서만 한 번 표시됩니다. 닫으면 다시 확인할 수 없습니다.
              <br />
              데스크톱 앱 첫 실행 화면에 이 코드를 입력하세요.
            </div>
            <div className="text-[12px] text-[#374151] space-y-1">
              <div>label: <span className="font-mono">{issued.label}</span></div>
              <div>code_id: <span className="font-mono">{issued.code_id}</span></div>
              <div>expires_at: <span className="font-mono">{formatExpiresAt(issued.expires_at)}</span></div>
            </div>
            <div>
              <label className="block text-[12px] font-semibold text-[#374151] mb-1">
                registration_code
              </label>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={issued.registration_code}
                  className="flex-1 font-mono text-[12px] border border-[#E5E7EB] rounded px-2 py-1 bg-[#F9FAFB]"
                  onFocus={(e) => e.currentTarget.select()}
                />
                <Btn variant="primary" size="sm" onClick={handleCopy}>
                  {copied ? "복사됨" : "복사"}
                </Btn>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Revoke confirm modal */}
      <Modal
        open={revokeTarget !== null}
        title="등록코드 폐기"
        onClose={() => { if (!revoking) { setRevokeTarget(null); setRevokeError(null); } }}
        footer={
          <>
            <Btn variant="secondary" size="sm" onClick={() => { setRevokeTarget(null); setRevokeError(null); }} disabled={revoking}>
              취소
            </Btn>
            <Btn variant="danger" size="sm" onClick={handleConfirmRevoke} disabled={revoking}>
              {revoking ? "폐기 중…" : "폐기"}
            </Btn>
          </>
        }
      >
        {revokeTarget && (
          <div className="space-y-2 text-[12px] text-[#374151]">
            <p>다음 등록코드를 폐기하시겠습니까? 폐기 후 해당 코드로는 더 이상 등록할 수 없습니다.</p>
            <div className="rounded bg-[#F9FAFB] border border-[#E5E7EB] px-3 py-2 space-y-0.5">
              <div>code_id: <span className="font-mono">{revokeTarget.code_id}</span></div>
              <div>label: <span className="font-mono">{revokeTarget.label || "-"}</span></div>
            </div>
            {revokeError && <p className="text-[#B91C1C]">{revokeError}</p>}
          </div>
        )}
      </Modal>
    </section>
  );
}
