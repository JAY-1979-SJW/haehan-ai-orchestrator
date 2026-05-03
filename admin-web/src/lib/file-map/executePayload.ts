/**파일 정리 실행 요청/응답 및 정규화.*/

export interface ExecuteRequest {
  preflight_id: string;
  package_id: string;
  approval_token: string;
  user_confirmed_execution: boolean;
  dry_run?: boolean;
  plans?: Array<any>;
  base_target_dir?: string;
  include_sensitive?: boolean;
}

export interface ExecuteResponse {
  ok: boolean;
  run_id?: string;
  package_id?: string;
  timestamp?: string;
  success_count?: number;
  failed_count?: number;
  skipped_count?: number;
  conflict_count?: number;
  succeeded?: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    category: string;
    file_size_bytes: number;
    dry_run: boolean;
  }>;
  failed?: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    error: string;
  }>;
  skipped?: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    reason: string;
  }>;
  conflicts?: Array<{
    operation_id: string;
    source_path: string;
    target_path: string;
    reason: string;
  }>;
  error?: string;
}

/**
 * plans 배열 정규화: 각 항목이 필수 필드를 갖도록 보정.
 *
 * Python run_preflight()가 기대하는 구조:
 * {operation_id, path, category, file_size_bytes, file_name}
 *
 * @param plans 원본 plans 배열
 * @returns 정규화된 plans 배열
 */
export function normalizePlans(plans: unknown[]): Record<string, unknown>[] {
  if (!Array.isArray(plans)) {
    return [];
  }

  return plans.map((plan, index) => {
    // 문자열인 경우: {path: <string>, operation_id: uuid, category: "unknown"}로 변환
    if (typeof plan === 'string') {
      return {
        operation_id: `plan-${index}-${Date.now()}`,
        path: plan,
        category: 'unknown',
        file_size_bytes: 0,
        file_name: plan.split(/[\\\/]/).pop() || 'unknown',
      };
    }

    // 객체인 경우: 필수 필드 보정
    if (typeof plan === 'object' && plan !== null) {
      const obj = plan as Record<string, unknown>;
      return {
        operation_id: obj.operation_id || `plan-${index}-${Date.now()}`,
        path: obj.path || '',
        category: obj.category || 'unknown',
        file_size_bytes: obj.file_size_bytes || 0,
        file_name: obj.file_name || '',
      };
    }

    // 기타: 기본값으로 변환
    return {
      operation_id: `plan-${index}-${Date.now()}`,
      path: '',
      category: 'unknown',
      file_size_bytes: 0,
      file_name: '',
    };
  });
}
