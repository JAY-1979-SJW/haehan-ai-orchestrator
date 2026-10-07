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

// CI에서는 빌드 산출물(portable 압축 해제본 또는 --dir unpacked)의 실제 경로를
// 환경변수로 넘긴다 — dist 폴더 이름(dist-electron-new)·버전별 하위 경로가 매
// 빌드 달라져서 상대경로 하나로는 못 맞춘다.
const EXE_FROM_ENV = process.env.HAEHAN_E2E_EXE_PATH;

export function launchApp(
  extraEnv: Record<string, string> = {},
  extraArgs: string[] = []
) {
  // process.env 값은 string | undefined라 Playwright의 env({[key: string]: string})
  // 타입과 안 맞는다 — undefined 항목을 걸러낸다.
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries({ ...process.env, ...extraEnv })) {
    if (v !== undefined) env[k] = v;
  }
  const packagedExe = EXE_FROM_ENV && fs.existsSync(EXE_FROM_ENV) ? EXE_FROM_ENV : PACKAGED_EXE;
  if (fs.existsSync(packagedExe)) {
    return electron.launch({ executablePath: packagedExe, args: extraArgs, env });
  }
  console.log("[e2e] 패키징 exe 없음 — 개발 모드(electron .)로 대체:", DEV_ROOT);
  return electron.launch({ args: [".", ...extraArgs], cwd: DEV_ROOT, env });
}
