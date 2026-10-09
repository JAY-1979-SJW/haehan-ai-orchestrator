Status: LOCKED
Baseline ID: MCP-GATEWAY-BASELINE-01

# MCP Gateway Baseline

This baseline defines how external MCP servers and owned app adapters are
registered into the unified AI agent app.

## Target Shape

```text
admin-web
  -> bounded API/task route
  -> MCP Gateway
  -> registered MCP server or owned app adapter
  -> result artifact / approval request / work record
```

The MCP Gateway is a routing and policy layer. It is not allowed to expose raw
MCP tools directly to the UI.

## Registry

The template registry is:

```text
configs/external_mcp_registry.template.json
```

The registry is a template until a real server is approved. It must not contain
raw tokens, passwords, cookies, bearer tokens, API keys, or private URLs that
grant access. Use environment secret references only.

## Required Server Fields

Every registered MCP server or app adapter must define:

- `id`
- `display_name`
- `kind`
- `enabled`
- `owner_app`
- `allowed_tools`
- `blocked_tools`
- `risk_level`
- `read_only_default`
- `approval_required`
- `ui_surface`
- `result_target`

## Policy

- New MCP entries default to `enabled: false`.
- Read-only tools may be prepared automatically only after audit coverage.
- Write, delete, publish, send, payment, permission change, credential issue,
  or external state change tools require approval.
- A tool call must produce a visible result artifact, report path, or approval
  request id.
- Chat may request MCP work, but execution must resolve through registered
  tools and the result panel.
- The app UI must show MCP Gateway readiness before enabling real MCP calls.

## Activation Checklist

Before enabling a real MCP entry:

- confirm the MCP server or adapter is owned or explicitly approved;
- register only allowed tools needed for the user workflow;
- block risky tools by name;
- reference secrets by environment variable name only;
- add UI surface, result target, and approval behavior;
- run `python tools/audits/agent/audit_mcp_gateway_baseline.py`;
- run `python tools/quality/required_quality_gate.py`.
