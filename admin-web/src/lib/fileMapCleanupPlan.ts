/**파일 정리 계획: API 호출 및 변환.*/

import type { FileMapMaskingMode } from '@/lib/fileMapSettings';

export interface CleanupPlanSample {
  maskedName: string;
  filePath: string;
  sizeBytes: number;
  modifiedTime: string;
}

export interface CleanupCategory {
  name: string;
  count: number;
  reason: string;
  suggestedPath: string;
  samples: CleanupPlanSample[];
}

export interface CleanupPlanSummary {
  totalFiles: number;
  archiveCandidates: number;
  documentCandidates: number;
  spreadsheetCandidates: number;
  cadCandidates: number;
  imageCandidates: number;
  sensitiveCandidates: number;
  duplicateReviewCandidates: number;
  holdCandidates: number;
}

export interface CleanupPlan {
  ok: boolean;
  generatedAt: string;
  source: string;
  masked: boolean;
  mode?: FileMapMaskingMode;
  authVerified?: boolean;
  executionEnabled: boolean;
  summary?: CleanupPlanSummary;
  suggestedStructure?: string;
  categories?: Record<string, CleanupCategory>;
  error?: string;
}

/**
 * cleanup-plan API 응답 (snake_case).
 */
interface CleanupPlanApiResponse {
  ok: boolean;
  generated_at: string;
  source: string;
  masked: boolean;
  mode?: FileMapMaskingMode;
  auth_verified?: boolean;
  execution_enabled: boolean;
  summary?: {
    total_files: number;
    archive_candidates: number;
    document_candidates: number;
    spreadsheet_candidates: number;
    cad_candidates: number;
    image_candidates: number;
    sensitive_candidates: number;
    duplicate_review_candidates: number;
    hold_candidates: number;
  };
  suggested_structure?: string;
  categories?: Record<string, {
    name: string;
    count: number;
    reason: string;
    suggested_path: string;
    samples: Array<{
      masked_name: string;
      file_path: string;
      size_bytes: number;
      modified_time: string;
    }>;
  }>;
  error?: string;
}

/**
 * cleanup-plan API 응답을 UI 모델로 변환.
 *
 * @param response API 응답 (snake_case)
 * @returns UI 모델 (camelCase)
 */
function mapApiResponseToModel(response: CleanupPlanApiResponse): CleanupPlan {
  return {
    ok: response.ok,
    generatedAt: response.generated_at,
    source: response.source,
    masked: response.masked,
    mode: response.mode,
    authVerified: response.auth_verified,
    executionEnabled: response.execution_enabled,
    summary: response.summary
      ? {
          totalFiles: response.summary.total_files,
          archiveCandidates: response.summary.archive_candidates,
          documentCandidates: response.summary.document_candidates,
          spreadsheetCandidates: response.summary.spreadsheet_candidates,
          cadCandidates: response.summary.cad_candidates,
          imageCandidates: response.summary.image_candidates,
          sensitiveCandidates: response.summary.sensitive_candidates,
          duplicateReviewCandidates: response.summary.duplicate_review_candidates,
          holdCandidates: response.summary.hold_candidates,
        }
      : undefined,
    suggestedStructure: response.suggested_structure,
    categories: response.categories
      ? Object.fromEntries(
          Object.entries(response.categories).map(([key, cat]) => [
            key,
            {
              name: cat.name,
              count: cat.count,
              reason: cat.reason,
              suggestedPath: cat.suggested_path,
              samples: cat.samples.map((s) => ({
                maskedName: s.masked_name,
                filePath: s.file_path,
                sizeBytes: s.size_bytes,
                modifiedTime: s.modified_time,
              })),
            },
          ])
        )
      : undefined,
    error: response.error,
  };
}

/**
 * 정리 계획 로드.
 *
 * @param mode 마스킹 모드
 * @returns 정리 계획 (UI 모델)
 */
export async function loadCleanupPlan(mode: FileMapMaskingMode): Promise<CleanupPlan> {
  try {
    const response = await fetch(`/api/file-map/cleanup-plan?mode=${mode}`);
    const json: CleanupPlanApiResponse = await response.json();

    if (!json.ok) {
      return {
        ok: false,
        generatedAt: new Date().toISOString(),
        source: 'cleanup-plan-client',
        masked: true,
        executionEnabled: false,
        error: json.error || 'Failed to load cleanup plan',
      };
    }

    return mapApiResponseToModel(json);
  } catch (err) {
    return {
      ok: false,
      generatedAt: new Date().toISOString(),
      source: 'cleanup-plan-client',
      masked: true,
      executionEnabled: false,
      error: err instanceof Error ? err.message : 'Failed to load cleanup plan',
    };
  }
}

/**
 * 정리 카테고리별 통계.
 *
 * @param plan 정리 계획
 * @returns 카테고리별 개수 맵
 */
export function getCategoryStats(plan: CleanupPlan): Record<string, number> {
  if (!plan.categories) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(plan.categories).map(([key, cat]) => [key, cat.count])
  );
}
