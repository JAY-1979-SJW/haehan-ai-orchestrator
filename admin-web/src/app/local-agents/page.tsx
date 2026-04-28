import {
  PageShell,
  FilterBar,
  FilterSelect,
  FilterSpacer,
  KpiCard,
  AdminTable,
  AdminThead,
  AdminTbody,
  AdminTr,
  AdminTh,
  AdminTd,
  EmptyRow,
  StatusBadge,
  EmptyState,
  Btn,
} from "@/components/ui";

// ─── Mock data ────────────────────────────────────────────────────────────────

interface MockAgent {
  agent_id: string;
  host: string;
  os_name: string;
  version: string;
  agent_status: "idle" | "busy" | "offline" | "stale";
  last_seen_at: string;
  active_task_count: number;
  current_task_id: string | null;
}

interface MockTask {
  task_id: string;
  action: string;
  status: string;
  risk_level: "low" | "medium" | "high";
  requested_by: string;
  created_at: string;
  updated_at: string;
  failure_reason: string | null;
}

const MOCK_AGENTS: MockAgent[] = [
  {
    agent_id: "agt-001",
    host: "workstation-dev-01",
    os_name: "Ubuntu 22.04",
    version: "0.5.2",
    agent_status: "idle",
    last_seen_at: "2026-04-28 14:35:01",
    active_task_count: 0,
    current_task_id: null,
  },
  {
    agent_id: "agt-002",
    host: "workstation-dev-02",
    os_name: "Windows 11",
    version: "0.5.2",
    agent_status: "busy",
    last_seen_at: "2026-04-28 14:34:58",
    active_task_count: 1,
    current_task_id: "task-0042",
  },
  {
    agent_id: "agt-003",
    host: "macbook-ci-01",
    os_name: "macOS 14.4",
    version: "0.5.0",
    agent_status: "stale",
    last_seen_at: "2026-04-28 13:50:12",
    active_task_count: 0,
    current_task_id: null,
  },
];

const MOCK_TASKS: MockTask[] = [
  {
    task_id: "task-0038",
    action: "run_script",
    status: "queued",
    risk_level: "low",
    requested_by: "admin",
    created_at: "2026-04-28 14:30:00",
    updated_at: "2026-04-28 14:30:00",
    failure_reason: null,
  },
  {
    task_id: "task-0039",
    action: "deploy_service",
    status: "waiting_approval",
    risk_level: "high",
    requested_by: "admin",
    created_at: "2026-04-28 14:31:00",
    updated_at: "2026-04-28 14:31:00",
    failure_reason: null,
  },
  {
    task_id: "task-0040",
    action: "collect_logs",
    status: "completed",
    risk_level: "low",
    requested_by: "system",
    created_at: "2026-04-28 14:20:00",
    updated_at: "2026-04-28 14:25:00",
    failure_reason: null,
  },
  {
    task_id: "task-0041",
    action: "restart_service",
    status: "failed",
    risk_level: "medium",
    requested_by: "admin",
    created_at: "2026-04-28 14:10:00",
    updated_at: "2026-04-28 14:12:00",
    failure_reason: "Process exited with code 1",
  },
  {
    task_id: "task-0042",
    action: "run_benchmark",
    status: "running",
    risk_level: "medium",
    requested_by: "admin",
    created_at: "2026-04-28 14:34:00",
    updated_at: "2026-04-28 14:34:58",
    failure_reason: null,
  },
  {
    task_id: "task-0043",
    action: "clear_cache",
    status: "cancel_requested",
    risk_level: "low",
    requested_by: "admin",
    created_at: "2026-04-28 14:28:00",
    updated_at: "2026-04-28 14:29:30",
    failure_reason: null,
  },
  {
    task_id: "task-0044",
    action: "sync_files",
    status: "cancelled",
    risk_level: "low",
    requested_by: "system",
    created_at: "2026-04-28 13:55:00",
    updated_at: "2026-04-28 13:56:00",
    failure_reason: null,
  },
];

// ─── KPI 집계 ─────────────────────────────────────────────────────────────────

const kpiTotal = MOCK_AGENTS.length;
const kpiIdle = MOCK_AGENTS.filter((a) => a.agent_status === "idle").length;
const kpiBusy = MOCK_AGENTS.filter((a) => a.agent_status === "busy").length;
const kpiOffline = MOCK_AGENTS.filter(
  (a) => a.agent_status === "offline" || a.agent_status === "stale"
).length;

// ─── Task 액션 버튼 로직 ───────────────────────────────────────────────────────

function TaskActionCell({ status }: { status: string }) {
  if (status === "queued" || status === "waiting_approval") {
    return (
      <Btn variant="danger" size="xs" disabled>
        취소
      </Btn>
    );
  }
  if (status === "delivered" || status === "running") {
    return (
      <Btn variant="secondary" size="xs" disabled>
        취소 요청
      </Btn>
    );
  }
  if (status === "cancel_requested") {
    return (
      <Btn variant="ghost" size="xs" disabled>
        취소 요청됨
      </Btn>
    );
  }
  if (status === "cancelled") {
    return (
      <Btn variant="ghost" size="xs" disabled>
        취소됨
      </Btn>
    );
  }
  return <span className="text-[12px] text-[#9CA3AF]">—</span>;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LocalAgentsPage() {
  const selectedAgent = MOCK_AGENTS[1]; // 정적: agt-002 고정 선택

  return (
    <PageShell
      title="로컬 에이전트"
      description="등록된 로컬 에이전트의 연결 상태와 작업 현황을 관리합니다."
      headerRight={
        <Btn variant="orange" size="sm" disabled>
          새로고침
        </Btn>
      }
    >
      {/* ── KPI 카드 ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="전체 에이전트" value={kpiTotal} />
        <KpiCard
          title="대기"
          value={kpiIdle}
          accentColor="#6B7280"
          description="idle"
        />
        <KpiCard
          title="작업중"
          value={kpiBusy}
          accentColor="#F97316"
          description="busy"
        />
        <KpiCard
          title="오프라인"
          value={kpiOffline}
          accentColor="#9CA3AF"
          description="offline / stale"
        />
      </div>

      {/* ── Agent 상태 필터 ───────────────────────────────────────────────────── */}
      <FilterBar>
        <FilterSelect label="에이전트 상태">
          <option value="">전체</option>
          <option value="idle">대기</option>
          <option value="busy">작업중</option>
          <option value="stale">응답지연</option>
          <option value="offline">오프라인</option>
        </FilterSelect>
        <FilterSpacer />
        <span className="text-[12px] text-[#9CA3AF]">※ 필터 연동은 다음 단계</span>
      </FilterBar>

      {/* ── Agent 목록 테이블 ─────────────────────────────────────────────────── */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] overflow-hidden mb-6">
        <div className="px-5 py-3 border-b border-[#E5E7EB] flex items-center justify-between">
          <span className="text-[13px] font-bold text-[#0F172A]">에이전트 목록</span>
          <span className="text-[12px] text-[#6B7280]">총 {MOCK_AGENTS.length}건</span>
        </div>
        <AdminTable>
          <AdminThead>
            <AdminTr>
              <AdminTh>Agent ID</AdminTh>
              <AdminTh>Host</AdminTh>
              <AdminTh>OS</AdminTh>
              <AdminTh>Version</AdminTh>
              <AdminTh>상태</AdminTh>
              <AdminTh>활성작업</AdminTh>
              <AdminTh>현재작업</AdminTh>
              <AdminTh>최근확인</AdminTh>
              <AdminTh>Actions</AdminTh>
            </AdminTr>
          </AdminThead>
          <AdminTbody>
            {MOCK_AGENTS.length === 0 ? (
              <EmptyRow colSpan={9} message="등록된 에이전트가 없습니다." />
            ) : (
              MOCK_AGENTS.map((agent) => (
                <AdminTr key={agent.agent_id}>
                  <AdminTd className="font-mono text-[12px] text-[#6B7280]">
                    {agent.agent_id}
                  </AdminTd>
                  <AdminTd className="font-semibold">{agent.host}</AdminTd>
                  <AdminTd className="text-[#6B7280]">{agent.os_name}</AdminTd>
                  <AdminTd className="font-mono text-[12px]">{agent.version}</AdminTd>
                  <AdminTd>
                    <StatusBadge status={agent.agent_status} />
                  </AdminTd>
                  <AdminTd className="text-center">{agent.active_task_count}</AdminTd>
                  <AdminTd className="font-mono text-[12px] text-[#6B7280]">
                    {agent.current_task_id ?? "—"}
                  </AdminTd>
                  <AdminTd className="text-[12px] text-[#9CA3AF] whitespace-nowrap">
                    {agent.last_seen_at}
                  </AdminTd>
                  <AdminTd>
                    <div className="flex items-center gap-1">
                      <Btn variant="ghost" size="xs" disabled>
                        작업 보기
                      </Btn>
                      <Btn variant="ghost" size="xs" disabled>
                        화면 캡처
                      </Btn>
                    </div>
                  </AdminTd>
                </AdminTr>
              ))
            )}
          </AdminTbody>
        </AdminTable>
      </div>

      {/* ── 선택된 Agent 작업 목록 ────────────────────────────────────────────── */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] overflow-hidden mb-6">
        <div className="px-5 py-3 border-b border-[#E5E7EB] flex items-center gap-3">
          <span className="text-[13px] font-bold text-[#0F172A]">
            작업 목록
          </span>
          <span className="text-[12px] text-[#6B7280]">
            에이전트:{" "}
            <span className="font-mono font-semibold text-[#F97316]">
              {selectedAgent.agent_id}
            </span>{" "}
            ({selectedAgent.host})
          </span>
          <span className="text-[12px] text-[#9CA3AF] ml-auto">
            ※ 선택 연동은 다음 단계
          </span>
        </div>

        {/* Task 상태 필터 */}
        <div className="px-5 py-2 border-b border-[#E5E7EB]">
          <FilterBar>
            <FilterSelect label="태스크 상태">
              <option value="">전체</option>
              <option value="queued">대기</option>
              <option value="waiting_approval">승인대기</option>
              <option value="running">실행중</option>
              <option value="completed">완료</option>
              <option value="failed">실패</option>
              <option value="cancelled">취소됨</option>
            </FilterSelect>
            <FilterSpacer />
            <span className="text-[12px] text-[#6B7280]">총 {MOCK_TASKS.length}건</span>
          </FilterBar>
        </div>

        <AdminTable>
          <AdminThead>
            <AdminTr>
              <AdminTh>Task ID</AdminTh>
              <AdminTh>Action</AdminTh>
              <AdminTh>Status</AdminTh>
              <AdminTh>Risk</AdminTh>
              <AdminTh>Requested By</AdminTh>
              <AdminTh>Created</AdminTh>
              <AdminTh>Updated</AdminTh>
              <AdminTh>Failure Reason</AdminTh>
              <AdminTh>Actions</AdminTh>
            </AdminTr>
          </AdminThead>
          <AdminTbody>
            {MOCK_TASKS.length === 0 ? (
              <EmptyRow colSpan={9} message="작업 내역이 없습니다." />
            ) : (
              MOCK_TASKS.map((task) => (
                <AdminTr key={task.task_id}>
                  <AdminTd className="font-mono text-[12px] text-[#6B7280]">
                    {task.task_id}
                  </AdminTd>
                  <AdminTd className="font-semibold">{task.action}</AdminTd>
                  <AdminTd>
                    <StatusBadge status={task.status} />
                  </AdminTd>
                  <AdminTd>
                    <StatusBadge status={task.risk_level} />
                  </AdminTd>
                  <AdminTd className="text-[#6B7280]">{task.requested_by}</AdminTd>
                  <AdminTd className="text-[12px] text-[#9CA3AF] whitespace-nowrap">
                    {task.created_at}
                  </AdminTd>
                  <AdminTd className="text-[12px] text-[#9CA3AF] whitespace-nowrap">
                    {task.updated_at}
                  </AdminTd>
                  <AdminTd className="text-[12px] text-[#B91C1C] max-w-[160px] truncate">
                    {task.failure_reason ?? "—"}
                  </AdminTd>
                  <AdminTd>
                    <TaskActionCell status={task.status} />
                  </AdminTd>
                </AdminTr>
              ))
            )}
          </AdminTbody>
        </AdminTable>
      </div>

      {/* ── 빈 상태 예시 ─────────────────────────────────────────────────────── */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] overflow-hidden">
        <div className="px-5 py-3 border-b border-[#E5E7EB]">
          <span className="text-[13px] font-bold text-[#0F172A]">
            EmptyState / Error Placeholder
          </span>
        </div>
        <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-[#E5E7EB]">
          <EmptyState
            title="등록된 에이전트 없음"
            description="로컬 에이전트를 연결하면 이 목록에 표시됩니다."
          />
          <EmptyState
            title="데이터를 불러오지 못했습니다"
            description="API 서버 응답 없음 — 다음 단계에서 실제 연동 예정"
          />
        </div>
      </div>
    </PageShell>
  );
}
