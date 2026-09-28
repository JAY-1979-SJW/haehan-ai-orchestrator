import { _electron as electron } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

// 패키징 exe가 있으면 그걸 쓰고(배포본 검증), 없으면 로컬 electron 모듈로
// `electron .` 방식 개발 모드를 대신 띄운다.
// (2026-09-28: PyInstaller 빌드/인스톨러 파이프라인을 복원하지 않아 패키징 exe가
// 없는 상태에서도 e2e를 돌릴 수 있게 — Playwright 공식 문서: executablePath 생략 시
// node_modules/.bin/electron을 쓰고, args로 앱 진입점을 넘긴다.)
const PACKAGED_EXE = path.resolve(
  __dirname,
  "../../../dist-installer/win-unpacked/Haehan AI.exe"
);
const DEV_ROOT = path.resolve(__dirname, ".."); // admin-web/electron

export function launchApp(extraEnv: Record<string, string> = {}) {
  // process.env 값은 string | undefined라 Playwright의 env({[key: string]: string})
  // 타입과 안 맞는다 — undefined 항목을 걸러낸다.
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries({ ...process.env, ...extraEnv })) {
    if (v !== undefined) env[k] = v;
  }
  if (fs.existsSync(PACKAGED_EXE)) {
    return electron.launch({ executablePath: PACKAGED_EXE, env });
  }
  console.log("[e2e] 패키징 exe 없음 — 개발 모드(electron .)로 대체:", DEV_ROOT);
  return electron.launch({ args: ["."], cwd: DEV_ROOT, env });
}
