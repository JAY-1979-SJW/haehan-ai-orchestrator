/**파일 정리 Python executor 호출.*/

import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

/**
 * repo root 디렉터리 해석.
 * agent 모듈과 admin-web이 모두 존재하는 경로 반환.
 *
 * @returns repo root 경로
 * @throws repo root를 찾을 수 없으면 오류 발생
 */
export function resolveRepoRoot(): string {
  const candidates = [
    process.cwd(),
    path.resolve(process.cwd(), '..'),
  ];

  const found = candidates.find((candidate) =>
    fs.existsSync(path.join(candidate, 'agent', 'local_inventory', 'file_map', 'cleanup_executor_api.py')) &&
    fs.existsSync(path.join(candidate, 'admin-web'))
  );

  if (!found) {
    throw new Error('repo root not found in expected paths');
  }

  return found;
}

/**
 * cleanup_executor_api.py 경로 해석.
 * 고정 후보 경로에서 첫 번째 존재하는 파일 반환.
 *
 * @returns cleanup_executor_api.py 경로
 * @throws 파일을 찾을 수 없으면 오류 발생
 */
export function resolveCleanupExecutorPath(): string {
  const candidates = [
    path.resolve(process.cwd(), 'agent', 'local_inventory', 'file_map', 'cleanup_executor_api.py'),
    path.resolve(process.cwd(), '..', 'agent', 'local_inventory', 'file_map', 'cleanup_executor_api.py'),
  ];

  const found = candidates.find((candidate) => fs.existsSync(candidate));

  if (!found) {
    throw new Error('cleanup_executor_api.py를 찾을 수 없습니다');
  }

  return found;
}

/**
 * Python cleanup_executor_api.py 호출.
 *
 * @param inputData Python으로 전달할 데이터
 * @returns Python의 응답 JSON
 * @throws 실행 실패 시 오류 발생
 */
export function callPythonExecutor(inputData: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    try {
      // Python 스크립트 경로 및 repo root
      const pythonScriptPath = resolveCleanupExecutorPath();
      const repoRoot = resolveRepoRoot();

      const child = spawn('python', [pythonScriptPath], {
        cwd: repoRoot,
        env: {
          ...process.env,
          PYTHONPATH: [
            repoRoot,
            process.env.PYTHONPATH || '',
          ].filter(Boolean).join(path.delimiter),
        },
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      let stdout = '';
      let stderr = '';

      child.stdout?.on('data', (data) => {
        stdout += data.toString();
      });

      child.stderr?.on('data', (data) => {
        stderr += data.toString();
      });

      child.on('close', (code) => {
        if (stderr) {
          console.error('Python stderr:', stderr);
        }

        if (code !== 0) {
          reject(new Error(`Python 실행 실패 (exit code ${code}): ${stderr}`));
          return;
        }

        try {
          const result = JSON.parse(stdout);
          resolve(result);
        } catch (e) {
          reject(new Error(`Python 응답 파싱 실패: ${stdout}`));
        }
      });

      child.on('error', (err) => {
        reject(new Error(`Python 실행 오류: ${err.message}`));
      });

      child.stdin?.write(JSON.stringify(inputData));
      child.stdin?.end();
    } catch (error) {
      reject(error);
    }
  });
}
