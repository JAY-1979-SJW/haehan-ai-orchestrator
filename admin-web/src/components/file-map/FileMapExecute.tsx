'use client';

import { useState, useEffect } from 'react';
import { generateApprovalToken, getTokenRemainingTime } from '@/lib/fileMapApproval';
import { executeMoves, type ExecuteMoveResult } from '@/lib/fileMapExecutor';

interface FileMapExecuteProps {
  preflightId: string;
  packageId: string;
  okCount: number;
  onExecuteComplete?: (result: ExecuteMoveResult) => void;
}

export function FileMapExecute({
  preflightId,
  packageId,
  okCount,
  onExecuteComplete,
}: FileMapExecuteProps) {
  const [approvalToken, setApprovalToken] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmPermanent, setConfirmPermanent] = useState(false);
  const [confirmNoRollback, setConfirmNoRollback] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tokenRemaining, setTokenRemaining] = useState<number | null>(null);

  useEffect(() => {
    if (approvalToken) {
      const timer = setInterval(() => {
        const remaining = getTokenRemainingTime();
        setTokenRemaining(remaining);
        if (remaining < 0) {
          setApprovalToken(null);
          clearInterval(timer);
        }
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [approvalToken]);

  const handleGenerateToken = () => {
    const token = generateApprovalToken();
    setApprovalToken(token);
    setError(null);
  };

  const handleExecute = async () => {
    if (!approvalToken) {
      setError('승인 토큰이 필요합니다');
      return;
    }

    if (!confirmDelete || !confirmPermanent || !confirmNoRollback) {
      setError('모든 확인 항목에 동의해야 합니다');
      return;
    }

    setExecuting(true);
    setError(null);

    try {
      const result = await executeMoves({
        preflightId,
        packageId,
        approvalToken,
        userConfirmedExecution: true,
        dryRun,
      });

      if (!result.ok) {
        setError(result.error || '실행 실패');
        return;
      }

      onExecuteComplete?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '오류 발생');
    } finally {
      setExecuting(false);
    }
  };

  const isReady = confirmDelete && confirmPermanent && confirmNoRollback && approvalToken;

  return (
    <div className="space-y-6">
      <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
        <p className="text-sm text-amber-800">
          ⚠️ 파일 이동은 되돌릴 수 없습니다. 신중하게 진행하세요.
        </p>
      </div>

      {!approvalToken ? (
        <button
          onClick={handleGenerateToken}
          className="w-full px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700"
        >
          승인 토큰 생성 (15분 유효)
        </button>
      ) : (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
          ✓ 토큰 생성됨 ({tokenRemaining}초 남음)
        </div>
      )}

      <div className="space-y-3">
        <label className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg hover:bg-gray-50">
          <input
            type="checkbox"
            checked={confirmDelete}
            onChange={(e) => setConfirmDelete(e.target.checked)}
            className="mt-1"
          />
          <span className="text-sm">
            삭제 금지: 이 작업은 파일을 삭제하지 않으며, 이동만 수행합니다.
          </span>
        </label>

        <label className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg hover:bg-gray-50">
          <input
            type="checkbox"
            checked={confirmPermanent}
            onChange={(e) => setConfirmPermanent(e.target.checked)}
            className="mt-1"
          />
          <span className="text-sm">
            영구성: 이동된 파일은 원본 위치에서 삭제되고, 새 위치에만 존재합니다.
          </span>
        </label>

        <label className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg hover:bg-gray-50">
          <input
            type="checkbox"
            checked={confirmNoRollback}
            onChange={(e) => setConfirmNoRollback(e.target.checked)}
            className="mt-1"
          />
          <span className="text-sm">
            롤백: 자동 롤백은 지원하지 않습니다. 필요 시 수동으로만 복구 가능합니다.
          </span>
        </label>
      </div>

      <label className="flex items-center gap-3 p-3 border border-gray-200 rounded-lg">
        <input
          type="checkbox"
          checked={dryRun}
          onChange={(e) => setDryRun(e.target.checked)}
          className="w-4 h-4"
        />
        <span className="text-sm">테스트 모드 (실제 파일 이동 안 함)</span>
      </label>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
          {error}
        </div>
      )}

      <button
        onClick={handleExecute}
        disabled={!isReady || executing || okCount === 0}
        className="w-full px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-400 font-medium"
      >
        {executing ? '실행 중...' : '승인 후 이동 실행'}
      </button>

      {!isReady && (
        <p className="text-xs text-center text-gray-500">
          {okCount === 0
            ? '준비된 항목이 없습니다'
            : '모든 확인 항목에 동의하고 토큰을 생성한 후 진행하세요'}
        </p>
      )}
    </div>
  );
}
