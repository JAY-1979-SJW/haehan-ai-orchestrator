"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  Alert,
  AppShell,
  Button,
  DataTable,
  Header,
  MetricCard,
  ReportList,
  Sidebar,
  StatusBadge,
} from "@/standard-ui";

type FlowRow = {
  id: string;
  layer: string;
  role: string;
  surface: string;
  gate: string;
  status: string;
};

type ToolRow = {
  id: string;
  tool: string;
  route: string;
  execution: string;
  policy: string;
  status: string;
};

type ActionRow = {
  id: string;
  action: string;
  target: string;
  input: string;
  outcome: string;
  href: string;
  status: string;
};

const navGroups = [
  {
    label: "Operate",
    items: [
      { href: "/", label: "Dashboard", active: true },
      { href: "/market-research", label: "Market Research" },
      { href: "/local-agents", label: "Local Agents" },
      { href: "/browser-approvals", label: "Approvals" },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/cad", label: "AI CAD" },
      { href: "/file-map", label: "File Map" },
      { href: "/assistant/tasks", label: "Tasks" },
      { href: "/external-tasks", label: "External Tasks" },
    ],
  },
  {
    label: "Govern",
    items: [
      { href: "/ops", label: "Ops Center" },
      { href: "/assistant/logs", label: "Work Logs" },
      { href: "/assistant/deployment", label: "Deployment" },
    ],
  },
];

const metrics = [
  { label: "App surfaces", value: "9", sub: "admin-web routes registered", accentColor: "#2563EB" },
  { label: "Execution path", value: "Gated", sub: "UI -> API -> task -> approval", accentColor: "#F97316" },
  { label: "Local runtime", value: "Bounded", sub: "browser and desktop work stay local", accentColor: "#059669" },
  { label: "MCP Gateway", value: "Ready", sub: "registry template disabled by default", accentColor: "#7C3AED" },
];

const flowRows: FlowRow[] = [
  {
    id: "app",
    layer: "App UI",
    role: "Command, approval, report review",
    surface: "admin-web",
    gate: "bounded forms",
    status: "PASS",
  },
  {
    id: "server",
    layer: "Server",
    role: "Route tasks and enforce policy",
    surface: "API routes / backend",
    gate: "allowlisted endpoints",
    status: "PASS",
  },
  {
    id: "local",
    layer: "Local Agent",
    role: "Use browser, files, and desktop tools",
    surface: "loopback runtime",
    gate: "user-present session",
    status: "PASS",
  },
  {
    id: "ai",
    layer: "AI Orchestration",
    role: "Plan, prepare, verify, summarize",
    surface: "scripts and task queue",
    gate: "approval before final action",
    status: "PASS",
  },
];

const toolRows: ToolRow[] = [
  {
    id: "market",
    tool: "Market Research",
    route: "/market-research",
    execution: "YouTube search, rank, topic report",
    policy: "read/prepare",
    status: "PASS",
  },
  {
    id: "agents",
    tool: "Local Agents",
    route: "/local-agents",
    execution: "agent registration and task status",
    policy: "loopback only",
    status: "PASS",
  },
  {
    id: "approval",
    tool: "Browser Approvals",
    route: "/browser-approvals",
    execution: "final browser action review",
    policy: "user approval",
    status: "PASS",
  },
  {
    id: "files",
    tool: "File Map",
    route: "/file-map",
    execution: "report, cleanup plan, rollback package",
    policy: "approval-gated execution",
    status: "PASS",
  },
  {
    id: "cad",
    tool: "AI CAD",
    route: "/cad",
    execution: "CAD assistant workflow",
    policy: "local desktop boundary",
    status: "PARTIAL",
  },
  {
    id: "mcp",
    tool: "External MCP Gateway",
    route: "/",
    execution: "Registered MCP servers and owned app adapters",
    policy: "disabled-by-default; approval-gated writes",
    status: "PARTIAL",
  },
];

const quickActionRows: ActionRow[] = [
  {
    id: "smartstore-research",
    action: "Analyze SmartStore market",
    target: "Market Research",
    input: "Preset keyword set",
    outcome: "Ranked videos, comments, and summary report",
    href: "/market-research",
    status: "READ_ONLY_ALLOWED",
  },
  {
    id: "approval-review",
    action: "Review final actions",
    target: "Browser Approvals",
    input: "No typing",
    outcome: "Approve, reject, or inspect exact submit boundary",
    href: "/browser-approvals",
    status: "USER_DIRECT_REQUIRED",
  },
  {
    id: "agent-health",
    action: "Check local runtime",
    target: "Local Agents",
    input: "No typing",
    outcome: "Agent connection, tasks, and diagnostics",
    href: "/local-agents",
    status: "PASS",
  },
  {
    id: "file-map",
    action: "Open file map result",
    target: "File Map",
    input: "No typing",
    outcome: "Latest report, cleanup plan, and gated execution",
    href: "/file-map",
    status: "PASS",
  },
];

const reports = [
  {
    title: "AI agent app structure baseline",
    path: "docs/baseline/AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE.md",
    date: "2026-05-27",
    category: "LOCKED",
  },
  {
    title: "AI agent UI structure blueprint",
    path: "docs/baseline/AI_AGENT_UI_STRUCTURE_BLUEPRINT.md",
    date: "2026-05-27",
    category: "LOCKED",
  },
  {
    title: "Site work function baseline",
    path: "docs/baseline/SITE_WORK_FUNCTION_BASELINE.md",
    date: "2026-05-27",
    category: "LOCKED",
  },
  {
    title: "Latest YouTube market research",
    path: "data/youtube_market_research_latest.json",
    date: "2026-05-27",
    category: "REPORT",
  },
  {
    title: "MCP gateway baseline",
    path: "docs/baseline/MCP_GATEWAY_BASELINE.md",
    date: "2026-05-27",
    category: "LOCKED",
  },
  {
    title: "MCP registry template",
    path: "configs/external_mcp_registry.template.json",
    date: "2026-05-27",
    category: "TEMPLATE",
  },
];

const latestResults = [
  ["Market report", "data/youtube_market_research_latest.json", "Open report or rerun preset"],
  ["Approval queue", "/browser-approvals", "Review user-final actions"],
  ["Runtime state", "/local-agents", "Check agent and task health"],
  ["Structure baseline", "docs/baseline/AI_AGENT_APP_STRUCTURE_DESIGN_BASELINE.md", "Audit locked UI contract"],
  ["UI blueprint", "docs/baseline/AI_AGENT_UI_STRUCTURE_BLUEPRINT.md", "Follow result-first tool screen template"],
  ["MCP Gateway readiness", "configs/external_mcp_registry.template.json", "Register MCP servers before enabling calls"],
];

const flowColumns = [
  { key: "layer", header: "Layer", width: 140 },
  { key: "role", header: "Role" },
  { key: "surface", header: "Surface", width: 190 },
  { key: "gate", header: "Gate", width: 180 },
  {
    key: "status",
    header: "Status",
    width: 100,
    render: (row: FlowRow) => <StatusBadge status={row.status} label={row.status} size="sm" />,
  },
];

const toolColumns = [
  { key: "tool", header: "Tool", width: 160 },
  { key: "route", header: "Route", width: 160 },
  { key: "execution", header: "Execution" },
  { key: "policy", header: "Policy", width: 180 },
  {
    key: "status",
    header: "Status",
    width: 100,
    render: (row: ToolRow) => <StatusBadge status={row.status} label={row.status} size="sm" />,
  },
];

const quickActionColumns = [
  { key: "action", header: "Button-first action", width: 190 },
  { key: "target", header: "Tool", width: 150 },
  { key: "input", header: "Input", width: 150 },
  { key: "outcome", header: "Immediate result" },
  {
    key: "status",
    header: "Gate",
    width: 140,
    render: (row: ActionRow) => <StatusBadge status={row.status} label={row.status} size="sm" />,
  },
  {
    key: "href",
    header: "Open",
    width: 90,
    render: (row: ActionRow) => (
      <Link href={row.href}>
        <Button variant="secondary" size="xs">Open</Button>
      </Link>
    ),
  },
];

function Panel({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section
      style={{
        background: "#FFFFFF",
        border: "1px solid #E5E7EB",
        borderRadius: 8,
        padding: 18,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 14,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#0F172A" }}>{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export default function Home() {
  return (
    <AppShell
      sidebar={
        <Sidebar
          logo={
            <div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>HAEHAN AI</div>
              <div style={{ marginTop: 4, fontSize: 11, color: "rgba(255,255,255,0.62)" }}>
                Unified AI Agent App
              </div>
            </div>
          }
          groups={navGroups}
          footer={
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.62)", lineHeight: 1.5 }}>
              Server + Local + App
              <br />
              approval-gated runtime
            </div>
          }
        />
      }
      header={
        <Header
          title="AI Agent Operations"
          right={
            <>
              <StatusBadge status="PASS" label="BASELINE LOCKED" />
              <StatusBadge status="READ_ONLY_ALLOWED" label="PREPARE ALLOWED" />
            </>
          }
        />
      }
    >
      <div data-testid="ai-agent-app-dashboard" style={{ padding: 24, maxWidth: 1320, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, lineHeight: 1.25, color: "#0F172A" }}>
              Server, local agent, app UI, and AI orchestration are operated as one gated system.
            </h1>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#6B7280", maxWidth: 820 }}>
              The user gives the instruction, AI prepares and verifies the work, the local runtime performs bounded
              actions, and final state-changing actions stop at the approval gate. Most work starts from buttons and
              presets; natural-language input is the fallback for unusual work.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            <Link href="/market-research">
              <Button variant="secondary">Open Research</Button>
            </Link>
            <Link href="/browser-approvals">
              <Button variant="primary">Review Approvals</Button>
            </Link>
          </div>
        </div>

        <Alert type="info" title="Operating contract">
          All tool work must enter through a registered app surface, a bounded API or task route, and a documented
          approval policy before it can change external state. The default UX is low-input: click a preset, see the
          latest result, and approve only final state-changing work.
        </Alert>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
            gap: 12,
            marginTop: 18,
          }}
        >
          {metrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} />
          ))}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1.45fr) minmax(320px, 0.9fr)",
            gap: 16,
            marginTop: 16,
            alignItems: "start",
          }}
        >
          <div style={{ display: "grid", gap: 16 }}>
            <Panel title="Quick Actions And Immediate Results" right={<StatusBadge status="PASS" label="LOW INPUT" size="sm" />}>
              <DataTable columns={quickActionColumns} rows={quickActionRows} keyField="id" />
            </Panel>

            <Panel title="Runtime Integration Flow" right={<StatusBadge status="PASS" label="GATED" size="sm" />}>
              <DataTable columns={flowColumns} rows={flowRows} keyField="id" />
            </Panel>

            <Panel title="Current App Tool Surfaces" right={<StatusBadge status="PARTIAL" label="EXPANDING" size="sm" />}>
              <DataTable columns={toolColumns} rows={toolRows} keyField="id" />
            </Panel>
          </div>

          <div style={{ display: "grid", gap: 16 }}>
            <Panel title="Chat And Result Workspace" right={<StatusBadge status="PARTIAL" label="SHELL READY" size="sm" />}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(240px, 0.9fr) minmax(0, 1.1fr)",
                  gap: 12,
                }}
              >
                <div style={{ border: "1px solid #E5E7EB", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>Instruction panel</div>
                  <p style={{ margin: "6px 0 10px", fontSize: 12, color: "#6B7280", lineHeight: 1.45 }}>
                    Use chat for exceptions. Common work should start from buttons and presets.
                  </p>
                  <textarea
                    data-testid="ai-agent-chat-input"
                    aria-label="AI instruction"
                    placeholder="Example: summarize the latest SmartStore research and prepare approval items."
                    rows={4}
                    disabled
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      resize: "vertical",
                      minHeight: 86,
                      border: "1px solid #D1D5DB",
                      borderRadius: 6,
                      padding: "8px 10px",
                      fontSize: 12,
                      color: "#374151",
                      background: "#F9FAFB",
                    }}
                  />
                  <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                    <Button variant="primary" size="sm" disabled title="Chat execution is enabled after task API wiring.">
                      Send
                    </Button>
                    <Button variant="secondary" size="sm" disabled title="Preset conversion is enabled after task API wiring.">
                      Convert to preset
                    </Button>
                  </div>
                </div>

                <div data-testid="ai-agent-result-panel" style={{ border: "1px solid #E5E7EB", borderRadius: 8, padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>Latest result panel</div>
                    <StatusBadge status="READ_ONLY_ALLOWED" label="RESULT FIRST" size="sm" />
                  </div>
                  <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
                    {latestResults.map(([name, path, next]) => (
                      <div
                        key={name}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "130px minmax(0, 1fr)",
                          gap: 8,
                          padding: "8px 10px",
                          border: "1px solid #F3F4F6",
                          borderRadius: 6,
                        }}
                      >
                        <div style={{ fontSize: 12, fontWeight: 700, color: "#0F172A" }}>{name}</div>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 12, color: "#374151", overflowWrap: "anywhere" }}>{path}</div>
                          <div style={{ marginTop: 2, fontSize: 11, color: "#6B7280" }}>{next}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Panel>

            <Panel title="Next Development Focus">
              <div style={{ display: "grid", gap: 10 }}>
                {[
                  ["Tool catalog", "List every Google, Naver, SmartStore, YouTube, CAD, and Ops capability in UI."],
                  ["MCP Gateway readiness", "Register multiple MCP servers and owned app adapters before enabling calls."],
                  ["Work records", "Persist AI work logs so another session can resume from the last verified state."],
                  ["Approval console", "Expose pending user-final actions with risk, source, and exact submit boundary."],
                  ["Runtime health", "Show server, container, local agent, drift, and gate status in one panel."],
                ].map(([title, body]) => (
                  <div key={title} style={{ border: "1px solid #E5E7EB", borderRadius: 8, padding: "10px 12px" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{title}</div>
                    <div style={{ marginTop: 3, fontSize: 12, color: "#6B7280", lineHeight: 1.45 }}>{body}</div>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Baseline Artifacts">
              <ReportList items={reports} />
            </Panel>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
