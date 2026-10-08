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

    // 2026-10-08 agent_error 사고: 연결만 보고 실제 작업 실행은 안 봐서 못 잡았다(frozen exe 가
    // --mcp-config 로 존재하지 않는 경로를 넘겨 claude CLI 가 즉시 종료). 짧은 프롬프트로 실제 한 건을
    // 돌려 "agent_error" 같은 뭉뚱그린 사유가 아니라 구체적인 결과/오류가 나오는지 확인한다.
    // HAEHAN_E2E_SKIP_PAID_API=1(CI 기본)이면 claude CLI 가 실제로 있을 가능성(향후 이미지 변경 등)에
    // 대비해 유료 호출 자체를 쏘지 않는다 — user_flow.spec.ts의 AI 채팅 스킵과 같은 원칙.
    if (process.env.HAEHAN_E2E_SKIP_PAID_API === "1") {
      console.log("⏭️ 실제 작업 실행 — HAEHAN_E2E_SKIP_PAID_API=1, 유료 API 스킵(연결 확인만으로 종료)");
      return;
    }
    const runRes = await fetch(`${BACKEND}/api/v1/ai-agent/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "1+1은? 숫자만 답해.", timeout: 60, max_budget_usd: 0.2 }),
    });
    expect(runRes.ok, `POST /ai-agent/run 실패: HTTP ${runRes.status}`).toBe(true);
    const runBody: any = await runRes.json();
    const { agent_id: taskAgentId, task_id: taskId } = runBody;
    expect(taskAgentId && taskId, `작업 큐잉 응답에 agent_id/task_id 없음: ${JSON.stringify(runBody)}`).toBeTruthy();

    const taskDeadline = Date.now() + 60_000;
    let task: any = null;
    while (Date.now() < taskDeadline) {
      const r = await fetch(`${BACKEND}/api/v1/local-agents/${taskAgentId}/tasks/${taskId}`);
      if (r.ok) {
        task = await r.json();
        if (["completed", "failed", "timed_out", "cancelled"].includes(task.status)) break;
      }
      await new Promise((res) => setTimeout(res, 1000));
    }
    expect(task, "작업 상태를 끝까지 못 받음(타임아웃)").not.toBeNull();
    console.log("[ai-agent run] status=%s failure_reason=%s error_summary=%s", task.status, task.failure_reason, task.error_summary);
    // "agent_error" 뭉뚱그림이 아니라(UniversalChat.tsx 가 error_summary 를 우선하도록도 고쳤지만,
    // 서버가 애초에 failure_reason 을 쓸모없는 값으로만 남기고 있지 않은지도 여기서 같이 본다).
    if (task.status !== "completed") {
      expect(
        task.error_summary && task.error_summary !== "agent_error",
        `실패 사유가 구체적이지 않음(agent_error 뭉뚱그림): ${JSON.stringify(task)}`
      ).toBeTruthy();
    } else {
      expect(task.result_summary, "완료인데 결과 요약이 비어 있음").toBeTruthy();
    }
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
