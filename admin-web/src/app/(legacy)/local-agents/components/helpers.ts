import { ApiError } from "@/lib/api";
import type { CaptureScreenshotResponse } from "@/types/local-agent";

export interface CaptureSuccessInfo {
  task_id: string;
  status: string;
  dry_run: boolean;
  approval_required: boolean;
}

export function roleAwareAuthMessage(status: 401 | 403, role: string | undefined): string {
  if (status === 401) return "로그인이 필요합니다. 브라우저 인증 상태를 확인하세요.";
  if (role === "viewer") return "조회 전용 권한입니다. admin/owner 권한이 필요합니다.";
  if (!role) return "권한 확인이 필요합니다. admin/owner 권한이 필요합니다.";
  return "권한이 없습니다. 서버 권한 정책을 확인하세요.";
}

export function cancelErrorMessage(err: unknown, role?: string): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 400: return "취소 사유는 최대 200자입니다.";
      case 401:
      case 403: return roleAwareAuthMessage(err.status, role);
      case 404: return "작업을 찾을 수 없습니다.";
      case 409: return "이미 취소되었거나 종료된 작업입니다.";
      default: return "취소 요청에 실패했습니다.";
    }
  }
  return "취소 요청에 실패했습니다.";
}

export function approvalErrorMessage(err: unknown, role?: string): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 400: return "요청이 유효하지 않습니다. (작업 상태 또는 token_id 확인 필요)";
      case 401:
      case 403: return roleAwareAuthMessage(err.status, role);
      case 404: return "작업 또는 승인 토큰을 찾을 수 없습니다.";
      case 409: return "이미 처리된 승인 요청입니다.";
      case 410: return "승인 토큰이 만료되었습니다. 새로운 요청을 생성하세요.";
      case 429: return "승인 요청이 너무 많습니다. 잠시 후 재시도하세요.";
      default: return `승인 처리에 실패했습니다. (HTTP ${err.status})`;
    }
  }
  return "승인 처리에 실패했습니다.";
}

export function captureErrorMessage(err: unknown, role?: string): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 401:
      case 403: return roleAwareAuthMessage(err.status, role);
      case 404: return "에이전트를 찾을 수 없습니다.";
      default: return `캡처 요청에 실패했습니다. (HTTP ${err.status})`;
    }
  }
  return "캡처 요청에 실패했습니다.";
}

export function fetchErrorMessage(err: unknown, fallback: string, role?: string): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return roleAwareAuthMessage(401, role);
    if (err.status === 403) return roleAwareAuthMessage(403, role);
    return `API ${err.status}: ${err.message}`;
  }
  return fallback;
}

export function extractCaptureSuccessInfo(res: CaptureScreenshotResponse): CaptureSuccessInfo {
  return {
    task_id: res.task_id,
    status: res.status,
    dry_run: res.dry_run,
    approval_required: res.approval_required,
  };
}

export function formatTime(date: Date): string {
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
