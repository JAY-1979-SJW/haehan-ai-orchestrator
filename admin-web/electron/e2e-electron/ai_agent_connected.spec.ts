import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { launchApp, waitForShell } from "./launch_helper";

// AI 작업 콘솔이 쓰는 로컬 에이전트(local_agent.agent --auto-connect, /api/v1/local-agents/ws)가
// 앱 시작 뒤 실제로 "연결됨"이 되는지 엄격하게 확인한다.
//
// 2026-10-08 결함(출시 차단): 설치본이 이 에이전트를 번들·기동하지 않아 콘솔이 항상
// "연결된 로컬 에이전트가 없습니다"(POST /api/v1/ai-agent/run 503)였는데, 어떤 E2E도 연결 여부를 보지 않아 잡지 못했다.
// 콘솔의 503 판정은 GET /api/v1/local-agents 의 목록이 비었을 때이고, 실제 연결 상태는 agent_status(idle|busy = 연결, offline = 끊김).
// 유료 호출은 하지 않는다 — 목록 조회(읽기)만 한다.
const BACKEND = "http://127.0.0.1:8401";
const CONNECT_TIMEOUT_MS = 60_000;

test.setTimeout(240_000);

test("앱 시작 후 AI 작업 콘솔 로컬 에이전트가 연결된다", async () => {
  const tmpUserData = fs.mkdtempSync(path.join(os.tmpdir(), "haehan-e2e-userdata-"));
  const app = await launchApp({}, [`--user-data-dir=${tmpUserData}`]);
  try {
    await waitForShell(app);

    const deadline = Date.now() + CONNECT_TIMEOUT_MS;
    let last = "응답 없음";
    let connected: any[] = [];
    while (Date.now() < deadline) {
      try {
        const res = await fetch(`${BACKEND}/api/v1/local-agents`);
        if (res.ok) {
          const agents: any[] = (await res.json()).agents ?? [];
          last = `agents=${agents.length} status=[${agents.map((a) => a.agent_status).join(",")}]`;
          connected = agents.filter((a) => a.agent_status === "idle" || a.agent_status === "busy");
          if (connected.length >= 1) break;
        } else {
          last = `HTTP ${res.status}`;
        }
      } catch (e: any) {
        last = `요청 실패: ${e?.message ?? e}`;
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    expect(
      connected.length,
      `AI 콘솔 로컬 에이전트가 ${CONNECT_TIMEOUT_MS / 1000}초 안에 연결되지 않음(${last}) — userData\logs\local-agent-ai.log·startup.log 확인`
    ).toBeGreaterThanOrEqual(1);
  } finally {
    await app.close();
    for (let i = 0; i < 10; i++) {
      try {
        fs.rmSync(tmpUserData, { recursive: true, force: true });
        break;
      } catch (e: any) {
        if (!["EBUSY", "EPERM", "ENOTEMPTY"].includes(e?.code)) throw e;
        await new Promise((r) => setTimeout(r, 500));
      }
    }
  }
});
