"""관리자 UI — 로컬 에이전트 capture_screenshot 요청 버튼 (사전 점검 + 실제 1회).

운영자가 브라우저에서 두 종류의 capture_screenshot 요청을 버튼으로 만들 수
있게 한다. 서버/승인/텔레그램/WS/로컬 실행 로직은 변경하지 않고, 기존
`/api/v1/local-agents/{id}/capture-screenshot` 엔드포인트만 호출한다.

버튼은 두 가지:
  1) 사전 점검 (dry-run)   : body={"dry_run": true,  "reason": "ui_dry_run_check"}
  2) 실제 1회 캡처 요청     : body={"dry_run": false, "reason": "ui_capture_once_request"}

보안/고정 원칙:
  - (2) 는 window.confirm() 게이트를 통과한 뒤에만 fetch 를 호출한다.
    confirm 취소 시 API 호출 없이 "요청이 취소되었습니다." 상태로 종료.
  - 승인 전 실행 없음 — 요청은 항상 waiting_approval 로 시작한다 (서버 구조 유지).
  - 이미지 표시/다운로드/업로드 UI 없음. 전체 경로/파일명/approval token 원문/
    디바이스 토큰 값은 절대 읽거나 표시하지 않는다.
  - 에이전트 필드는 모두 textContent 로만 DOM 에 삽입해 XSS 를 차단한다.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from tools.gates.auth import require_role

admin_ui_router = APIRouter(prefix="/admin", tags=["admin-ui"])


def _legacy_admin_ui_fallback_enabled() -> bool:
    return os.getenv("HAEHAN_ADMIN_LEGACY_UI_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# confirm 문구와 성공 안내 문구는 테스트가 substring 으로 검증한다.
# (본 HTML 은 jinja2 를 쓰지 않으므로 중괄호 이스케이프 이슈 없음)
_LOCAL_AGENTS_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>로컬 에이전트 관리 (사전 점검 / 실제 1회)</title>
<style>
  /* ── 기본 레이아웃 ── */
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
         sans-serif; margin: 0; background: #F0F2F5; color: #111827; }
  .page-wrap { max-width: 1080px; margin: 0 auto; padding: 28px 24px; }
  h1 { font-size: 20px; font-weight: 700; margin: 0 0 4px; color: #111827; }
  h2 { font-size: 15px; font-weight: 700; margin: 0 0 12px; color: #111827; }
  .note { color: #6B7280; margin-bottom: 20px; font-size: 13px; }
  .warn { color: #b00020; font-weight: 600; margin-top: 4px; font-size: 12px; }

  /* ── 카드 ── */
  .card { background: #FFFFFF; border-radius: 8px;
          border: 1px solid #E5E7EB;
          box-shadow: 0 1px 4px rgba(0,0,0,.06);
          margin-bottom: 20px; overflow: hidden; }
  .card-header { padding: 14px 16px; border-bottom: 1px solid #E5E7EB;
                 display: flex; align-items: center; gap: 12px;
                 flex-wrap: wrap; }
  .card-body { padding: 0; }

  /* ── agent 목록 테이블 ── */
  .agent-table { border-collapse: collapse; width: 100%; }
  .agent-table th { background: #F3F4F6; padding: 8px 12px;
                    text-align: left; font-size: 11px; font-weight: 700;
                    color: #374151; border-bottom: 2px solid #E5E7EB; }
  .agent-table td { padding: 10px 12px; font-size: 13px; color: #374151;
                    border-bottom: 1px solid #F3F4F6; vertical-align: top; }
  .agent-table tr:last-child td { border-bottom: none; }
  .agent-table tr:hover td { background: #F9FAFB; }

  /* ── 작업 목록 테이블 ── */
  .task-table { border-collapse: collapse; width: 100%; }
  .task-table th { background: #F3F4F6; padding: 7px 10px;
                   text-align: left; font-size: 11px; font-weight: 700;
                   color: #374151; border-bottom: 2px solid #E5E7EB;
                   white-space: nowrap; }
  .task-table td { padding: 9px 10px; font-size: 12px; color: #374151;
                   border-bottom: 1px solid #F3F4F6; vertical-align: top; }
  .task-table tr:last-child td { border-bottom: none; }
  .task-table tr:hover td { background: #F9FAFB; }
  .task-id-cell { font-family: monospace; font-size: 11px; color: #6B7280; }
  .failure-cell { font-size: 11px; color: #B91C1C; }

  /* ── 배지 공통 ── */
  .badge { display: inline-block; font-size: 11px; font-weight: 600;
           padding: 2px 8px; border-radius: 10px; border: 1px solid; }

  /* status 배지 */
  .badge-queued         { background:#FFFBEB; color:#92400E; border-color:#FDE68A; }
  .badge-waiting_approval { background:#FFFBEB; color:#92400E; border-color:#FDE68A; }
  .badge-delivered      { background:#D1FAE5; color:#065F46; border-color:#6EE7B7; }
  .badge-running        { background:#ECFDF5; color:#16A34A; border-color:#A7F3D0; }
  .badge-completed      { background:#F3F4F6; color:#6B7280; border-color:#D1D5DB; }
  .badge-failed         { background:#FEE2E2; color:#B91C1C; border-color:#F87171; }
  .badge-rejected       { background:#FEE2E2; color:#991B1B; border-color:#F87171; }
  .badge-status-default { background:#F3F4F6; color:#6B7280; border-color:#D1D5DB; }

  /* risk 배지 */
  .badge-low    { background:#F0FDF4; color:#15803D; border-color:#BBF7D0; }
  .badge-medium { background:#FFFBEB; color:#92400E; border-color:#FDE68A; }
  .badge-high   { background:#FFF7ED; color:#C2410C; border-color:#FED7AA; }

  /* agent 상태 배지 */
  .badge-agent-idle    { background:#D1FAE5; color:#065F46; border-color:#6EE7B7; }
  .badge-agent-busy    { background:#FFF7ED; color:#C2410C; border-color:#FED7AA; }
  .badge-agent-stale   { background:#F3F4F6; color:#6B7280; border-color:#D1D5DB; }
  .badge-agent-offline { background:#FEE2E2; color:#B91C1C; border-color:#F87171; }
  .badge-agent-unknown { background:#F3F4F6; color:#6B7280; border-color:#D1D5DB; }

  /* agent 상태 보조 텍스트 */
  .agent-info-sub2 { color:#6B7280; font-size:12px; margin-top:3px; }

  /* ── 버튼 ── */
  button.dry-run-btn { padding: 6px 10px; border: 1px solid #2a5db0;
                       background: #eaf1ff; color: #2a5db0; cursor: pointer;
                       border-radius: 4px; font-size: 13px; margin-right: 6px; }
  button.real-capture-btn { padding: 6px 10px; border: 1px solid #a00020;
                            background: #fde7ea; color: #a00020;
                            cursor: pointer; border-radius: 4px;
                            font-size: 13px; font-weight: 600; }
  button.task-view-btn { padding: 5px 10px; border: 1px solid #E5E7EB;
                         background: #F5F7FA; color: #374151; cursor: pointer;
                         border-radius: 4px; font-size: 12px; font-weight: 600;
                         margin-right: 4px; }
  button.task-view-btn:hover { background: #E5E7EB; }
  button[disabled] { opacity: 0.55; cursor: progress; }

  /* ── 필터 select ── */
  select.status-filter { height: 30px; padding: 0 8px;
                         border: 1px solid #E5E7EB; border-radius: 6px;
                         font-size: 12px; color: #374151; background: #fff;
                         cursor: pointer; }

  /* ── 상태/빈 메시지 ── */
  .status { margin-top: 6px; font-size: 12px; color: #333;
            white-space: pre-wrap; }
  .status.ok  { color: #1a6d1a; }
  .status.err { color: #b00020; }
  .empty-row td { text-align: center; padding: 40px 12px;
                  color: #6B7280; font-size: 13px; }
  .task-loading { text-align: center; padding: 20px; color: #6B7280;
                  font-size: 13px; }
  .task-err { color: #B91C1C; font-size: 13px; padding: 12px; }
  .task-count { font-size: 12px; color: #6B7280; font-weight: 400; }
</style>
</head>
<body>
<div class="page-wrap">
<div style="background:#FEF3C7;border:1px solid #F59E0B;border-radius:8px;
            padding:12px 16px;margin-bottom:20px;font-size:13px;color:#92400E;">
  <strong>이 화면은 legacy 관리 화면입니다.</strong><br>
  표준 관리자 UI는
  <a href="/orchestrator/admin-web/local-agents"
     style="color:#1D4ED8;text-decoration:underline;">
    /orchestrator/admin-web/local-agents
  </a>
  를 사용하세요.<br>
  <small style="color:#78350F;">
    이 화면은 admin-web 장애 시 fallback 용도로 유지됩니다.
    신규 기능은 admin-web에서만 추가됩니다.
  </small>
</div>
<h1>로컬 에이전트 — 화면 캡처 요청</h1>
<p class="note">
  사전 점검 버튼은 <b>dry_run=true</b> 요청만 생성합니다.
  실제 1회 캡처 버튼은 <b>dry_run=false</b> 요청을 생성하며,
  클릭 시 브라우저 확인창(confirm)을 통과해야 합니다.
  서버에는 이미지가 업로드되지 않습니다.
</p>

<div id="root">
  <p style="color:#6B7280;font-size:13px;">에이전트 목록을 불러오는 중…</p>
</div>
</div>

<script>
(function () {
  "use strict";

  // ── 상수 ──────────────────────────────────────────────────────────
  var AGENTS_URL = "/api/v1/local-agents";

  // 사전 점검용 body (기존 버튼, 변경 없음)
  var DRY_RUN_BODY = { dry_run: true, reason: "ui_dry_run_check" };

  // 실제 1회 캡처용 body — dry_run 은 반드시 false 로 명시해서 보낸다.
  var REAL_CAPTURE_BODY = { dry_run: false, reason: "ui_capture_once_request" };

  // window.confirm 에 띄울 경고 문구
  var CONFIRM_REAL_CAPTURE =
    "승인 후 로컬 PC에서 1회 화면 캡처가 실행됩니다." +
    " 서버에는 이미지가 업로드되지 않습니다. 계속하시겠습니까?";

  var STATUS_OPTIONS = [
    "all", "queued", "delivered", "running",
    "completed", "failed", "waiting_approval", "rejected"
  ];

  // ── XSS 방어 ────────────────────────────────────────────────────
  function escapeHtml(v) {
    if (v === null || v === undefined) return "";
    return String(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // ── DOM 유틸 ─────────────────────────────────────────────────────
  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k)) {
          node.setAttribute(k, attrs[k]);
        }
      }
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  function showError(root, msg) {
    root.innerHTML = "";
    var p = el("p", { "class": "status err" }, msg);
    root.appendChild(p);
  }

  function setStatus(box, kind, msg) {
    box.textContent = msg;
    box.className = "status " + (kind || "");
  }

  // ── 배지 헬퍼 ───────────────────────────────────────────────────
  function taskStatusBadge(status) {
    var s = status || "";
    var cls = "badge badge-status-default";
    var knownStatuses = [
      "queued", "waiting_approval", "delivered",
      "running", "completed", "failed", "rejected"
    ];
    if (knownStatuses.indexOf(s) !== -1) {
      cls = "badge badge-" + s;
    }
    return '<span class="' + cls + '">' + escapeHtml(s || "unknown") + "</span>";
  }

  function riskBadge(risk) {
    var r = risk || "";
    var cls = "badge badge-status-default";
    if (r === "low" || r === "medium" || r === "high") {
      cls = "badge badge-" + r;
    }
    return '<span class="' + cls + '">' + escapeHtml(r || "-") + "</span>";
  }

  // ── agent 상태 배지 헬퍼 ─────────────────────────────────────────
  function formatAgentStatusLabel(status) {
    var labels = {
      idle: "대기", busy: "작업중", stale: "응답지연", offline: "오프라인"
    };
    return labels[status] || "알 수 없음";
  }

  function agentStatusBadge(status) {
    var s = status || "unknown";
    var known = ["idle", "busy", "stale", "offline"];
    var cls = known.indexOf(s) !== -1
      ? "badge badge-agent-" + s
      : "badge badge-agent-unknown";
    return '<span class="' + cls + '">'
      + escapeHtml(formatAgentStatusLabel(s)) + "</span>";
  }

  function formatTimestamp(value) {
    if (!value) return "-";
    return String(value).slice(0, 19).replace("T", " ");
  }

  // ── 작업 목록 렌더링 ──────────────────────────────────────────
  function renderTaskTable(container, tasks) {
    container.innerHTML = "";

    if (!tasks || tasks.length === 0) {
      var table = document.createElement("table");
      table.className = "task-table";
      var tbody = document.createElement("tbody");
      var tr = document.createElement("tr");
      tr.className = "empty-row";
      var td = document.createElement("td");
      td.colSpan = 8;
      td.textContent = "최근 작업이 없습니다.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      table.appendChild(tbody);
      container.appendChild(table);
      return;
    }

    var table = document.createElement("table");
    table.className = "task-table";

    var thead = document.createElement("thead");
    var trh = document.createElement("tr");
    ["Task ID", "Action", "Status", "Risk", "Requested By",
     "Created", "Updated", "Failure Reason"].forEach(function (h) {
      var th = document.createElement("th");
      th.textContent = h;
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    tasks.forEach(function (t) {
      var tr = document.createElement("tr");

      // Task ID (monospace, muted)
      var tdId = document.createElement("td");
      tdId.className = "task-id-cell";
      tdId.textContent = t.task_id || "-";
      tr.appendChild(tdId);

      // Action
      var tdAction = document.createElement("td");
      tdAction.textContent = t.action || "-";
      tr.appendChild(tdAction);

      // Status badge (innerHTML 사용 — badge 마크업만, 값은 escapeHtml 처리됨)
      var tdStatus = document.createElement("td");
      tdStatus.innerHTML = taskStatusBadge(t.status);
      tr.appendChild(tdStatus);

      // Risk badge
      var tdRisk = document.createElement("td");
      tdRisk.innerHTML = riskBadge(t.risk_level);
      tr.appendChild(tdRisk);

      // Requested By
      var tdReq = document.createElement("td");
      tdReq.textContent = t.requested_by || "-";
      tr.appendChild(tdReq);

      // Created At
      var tdCreated = document.createElement("td");
      tdCreated.textContent = t.created_at ? t.created_at.slice(0, 19).replace("T", " ") : "-";
      tr.appendChild(tdCreated);

      // Updated At
      var tdUpdated = document.createElement("td");
      tdUpdated.textContent = t.updated_at ? t.updated_at.slice(0, 19).replace("T", " ") : "-";
      tr.appendChild(tdUpdated);

      // Failure Reason
      var tdFail = document.createElement("td");
      tdFail.className = "failure-cell";
      var fr = t.failure_reason || "";
      tdFail.textContent = fr || "-";
      // timed_out_at을 title 보조 텍스트로만 표시
      if (fr && t.timed_out_at) {
        tdFail.title = "timed_out_at: " + t.timed_out_at;
      }
      tr.appendChild(tdFail);

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
  }

  // ── 작업 목록 fetch ──────────────────────────────────────────────
  function loadAgentTasks(agentId, container, status) {
    container.innerHTML = '<p class="task-loading">불러오는 중…</p>';

    var url = "/api/v1/local-agents/" +
              encodeURIComponent(agentId) + "/tasks?limit=50";
    if (status && status !== "all") {
      url += "&status=" + encodeURIComponent(status);
    }

    fetch(url, { credentials: "same-origin" })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("HTTP " + resp.status);
        }
        return resp.json();
      })
      .then(function (data) {
        var tasks = (data && data.tasks) || [];
        var total = (data && data.total) || 0;

        // 헤더 카운트 업데이트
        var countEl = container.parentNode
          && container.parentNode.querySelector(".task-count");
        if (countEl) {
          countEl.textContent = "최근 작업 " + total + "건";
        }

        renderTaskTable(container, tasks);
      })
      .catch(function (e) {
        container.innerHTML =
          '<p class="task-err">작업 목록을 불러오지 못했습니다: ' +
          escapeHtml(e.message) + "</p>";
      });
  }

  // ── 에이전트 목록 렌더링 ─────────────────────────────────────────
  function renderAgents(root, agents) {
    root.innerHTML = "";
    if (!agents || agents.length === 0) {
      root.appendChild(el("p", { style: "color:#6B7280;font-size:13px;" },
        "등록된 로컬 에이전트가 없습니다."));
      return;
    }

    agents.forEach(function (agent) {
      var agentId = agent.agent_id || "";

      var card = document.createElement("div");
      card.className = "card";

      // 카드 헤더: agent 정보 + 캡처 버튼 + 작업 보기 버튼
      var header = document.createElement("div");
      header.className = "card-header";

      var agentInfo = document.createElement("div");
      agentInfo.style.flex = "1";

      // 첫 번째 줄: host + agent_status 배지
      var infoLine1 = document.createElement("div");
      infoLine1.style.cssText = "display:flex;align-items:center;gap:8px;";
      var infoText = document.createElement("span");
      infoText.style.fontWeight = "600";
      infoText.style.fontSize = "14px";
      infoText.textContent = agent.host || agentId;
      var badgeSpan = document.createElement("span");
      badgeSpan.innerHTML = agentStatusBadge(agent.agent_status);
      infoLine1.appendChild(infoText);
      infoLine1.appendChild(badgeSpan);

      // 두 번째 줄: agent_id · os · version
      var infoSub = document.createElement("div");
      infoSub.style.cssText = "color:#6B7280;font-size:12px;margin-top:2px;";
      infoSub.textContent =
        agentId + " · " + (agent.os_name || "") +
        " · v" + (agent.version || "");

      // 세 번째 줄: 최근확인 · 활성작업
      var infoSub2 = document.createElement("div");
      infoSub2.className = "agent-info-sub2";
      var lastSeen = formatTimestamp(agent.last_seen_at);
      var taskCount = (agent.active_task_count !== undefined)
        ? String(agent.active_task_count) : "0";
      infoSub2.textContent =
        "최근확인: " + lastSeen + " · 활성작업: " + taskCount;

      // 네 번째 줄(조건): busy이고 current_task_id가 있을 때
      var currentTaskId = agent.current_task_id || "";
      if (currentTaskId) {
        var infoSub3 = document.createElement("div");
        infoSub3.className = "agent-info-sub2";
        infoSub3.textContent = "현재 작업: " + currentTaskId;
        agentInfo.appendChild(infoLine1);
        agentInfo.appendChild(infoSub);
        agentInfo.appendChild(infoSub2);
        agentInfo.appendChild(infoSub3);
      } else {
        agentInfo.appendChild(infoLine1);
        agentInfo.appendChild(infoSub);
        agentInfo.appendChild(infoSub2);
      }

      // disconnected_at 보조 텍스트 (있을 때만)
      var disconnectedAt = agent.disconnected_at || "";
      if (disconnectedAt) {
        var infoDisc = document.createElement("div");
        infoDisc.className = "agent-info-sub2";
        infoDisc.textContent = "연결종료: " + formatTimestamp(disconnectedAt);
        agentInfo.appendChild(infoDisc);
      }

      header.appendChild(agentInfo);

      var statusBox = el("div", { "class": "status" });

      // 기존 사전 점검 버튼
      var dryBtn = el("button",
        { "class": "dry-run-btn", "data-agent-id": agentId },
        "화면 캡처 사전 점검");
      dryBtn.addEventListener("click", function () {
        requestDryRun(dryBtn, statusBox);
      });

      // 기존 실제 1회 캡처 버튼
      var realBtn = el("button",
        { "class": "real-capture-btn", "data-agent-id": agentId },
        "실제 1회 화면 캡처 요청");
      realBtn.addEventListener("click", function () {
        requestRealCapture(realBtn, statusBox);
      });

      // 작업 보기 버튼
      var taskBtn = el("button", { "class": "task-view-btn" }, "작업 목록 보기");

      header.appendChild(dryBtn);
      header.appendChild(realBtn);
      header.appendChild(taskBtn);

      var warnLine = el("small", { "class": "warn" },
        "※ 실제 1회 캡처는 승인 후 로컬 PC에서 1회만 실행됩니다." +
        " 서버에는 이미지가 업로드되지 않습니다.");
      header.appendChild(warnLine);
      header.appendChild(statusBox);

      card.appendChild(header);

      // 작업 목록 영역 (초기 숨김)
      var taskSection = document.createElement("div");
      taskSection.style.display = "none";
      taskSection.style.borderTop = "1px solid #E5E7EB";
      taskSection.style.padding = "12px 16px 16px";

      // 작업 목록 서브 헤더 (필터 select + 카운트)
      var taskHeader = document.createElement("div");
      taskHeader.style.cssText =
        "display:flex;align-items:center;gap:10px;margin-bottom:10px;";

      var taskTitle = document.createElement("span");
      taskTitle.style.cssText = "font-size:13px;font-weight:700;color:#111827;";
      taskTitle.textContent = "최근 작업";

      var countSpan = document.createElement("span");
      countSpan.className = "task-count";
      countSpan.textContent = "";

      var filterSel = document.createElement("select");
      filterSel.className = "status-filter";
      STATUS_OPTIONS.forEach(function (opt) {
        var o = document.createElement("option");
        o.value = opt;
        o.textContent = opt === "all" ? "전체 상태" : opt;
        filterSel.appendChild(o);
      });

      taskHeader.appendChild(taskTitle);
      taskHeader.appendChild(countSpan);

      var spacer = document.createElement("span");
      spacer.style.flex = "1";
      taskHeader.appendChild(spacer);
      taskHeader.appendChild(filterSel);

      var taskBody = document.createElement("div");

      taskSection.appendChild(taskHeader);
      taskSection.appendChild(taskBody);
      card.appendChild(taskSection);

      // 작업 보기 버튼 토글
      var taskVisible = false;
      taskBtn.addEventListener("click", function () {
        taskVisible = !taskVisible;
        if (taskVisible) {
          taskSection.style.display = "";
          taskBtn.textContent = "작업 목록 닫기";
          loadAgentTasks(agentId, taskBody, filterSel.value);
        } else {
          taskSection.style.display = "none";
          taskBtn.textContent = "작업 목록 보기";
        }
      });

      // 필터 변경 시 재조회
      filterSel.addEventListener("change", function () {
        if (taskVisible) {
          loadAgentTasks(agentId, taskBody, filterSel.value);
        }
      });

      root.appendChild(card);
    });
  }

  // ── 공통 POST 헬퍼 ────────────────────────────────────────────────
  function postCapture(agentId, body, btn, statusBox, onSuccess) {
    btn.disabled = true;
    setStatus(statusBox, "", "요청 중…");

    fetch("/api/v1/local-agents/" + encodeURIComponent(agentId) +
          "/capture-screenshot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body)
    }).then(function (resp) {
      return resp.json().then(function (data) {
        return { status: resp.status, data: data };
      }).catch(function () {
        return { status: resp.status, data: null };
      });
    }).then(function (out) {
      btn.disabled = false;
      if (out.status === 200 && out.data) {
        onSuccess(out.data);
      } else if (out.status === 403) {
        setStatus(statusBox, "err", "권한이 없습니다.");
      } else if (out.status === 404) {
        setStatus(statusBox, "err", "로컬 에이전트를 찾을 수 없습니다.");
      } else {
        setStatus(statusBox, "err",
          "요청 실패 (HTTP " + out.status + ")");
      }
    }).catch(function () {
      btn.disabled = false;
      setStatus(statusBox, "err", "네트워크 오류로 요청하지 못했습니다.");
    });
  }

  // ── dry-run 요청 (기존 버튼 — 동작 유지) ────────────────────────
  function requestDryRun(btn, statusBox) {
    var agentId = btn.getAttribute("data-agent-id") || "";
    if (!agentId) {
      setStatus(statusBox, "err", "agent_id 가 없습니다.");
      return;
    }
    postCapture(agentId, DRY_RUN_BODY, btn, statusBox, function (d) {
      var lines = [
        "요청 생성 완료",
        "task_id: " + (d.task_id || "-"),
        "status: " + (d.status || "-"),
        "dry_run: " + (d.dry_run === true ? "true" : "false"),
        "텔레그램에서 사전 점검 승인이 필요합니다."
      ];
      setStatus(statusBox, "ok", lines.join("\\n"));
    });
  }

  // ── 실제 1회 캡처 요청 (confirm 게이트 필수) ────────────────────
  function requestRealCapture(btn, statusBox) {
    var agentId = btn.getAttribute("data-agent-id") || "";
    if (!agentId) {
      setStatus(statusBox, "err", "agent_id 가 없습니다.");
      return;
    }

    // 확인 게이트 — window.confirm 이 false(취소)면 어떤 fetch 도 호출하지 않는다.
    var confirmed = window.confirm(CONFIRM_REAL_CAPTURE);
    if (!confirmed) {
      setStatus(statusBox, "", "요청이 취소되었습니다.");
      return;
    }

    postCapture(agentId, REAL_CAPTURE_BODY, btn, statusBox, function (d) {
      var lines = [
        "실제 캡처 요청 생성 완료",
        "task_id: " + (d.task_id || "-"),
        "status: " + (d.status || "-"),
        "dry_run: " + (d.dry_run === true ? "true" : "false"),
        "텔레그램에서 실제 1회 캡처 승인이 필요합니다.",
        "승인 후 로컬 PC에서 1회 실행되며 서버에는 이미지가 업로드되지 않습니다."
      ];
      setStatus(statusBox, "ok", lines.join("\\n"));
    });
  }

  // ── 초기 로드 ─────────────────────────────────────────────────────
  function load() {
    var root = document.getElementById("root");
    fetch(AGENTS_URL, { credentials: "same-origin" })
      .then(function (resp) {
        if (resp.status === 403) {
          throw new Error("권한이 없습니다.");
        }
        if (!resp.ok) {
          throw new Error("에이전트 목록을 불러오지 못했습니다 (HTTP " +
            resp.status + ").");
        }
        return resp.json();
      })
      .then(function (data) {
        renderAgents(root, (data && data.agents) || []);
      })
      .catch(function (e) {
        showError(root, e.message || "에이전트 목록을 불러오지 못했습니다.");
      });
  }

  document.addEventListener("DOMContentLoaded", load);
})();
</script>
</body>
</html>
"""


@admin_ui_router.get("/local-agents", response_class=HTMLResponse)
def admin_local_agents_page(
    user: dict = Depends(require_role("admin", "owner")),
) -> Response:
    """관리자 전용 로컬 에이전트 화면.

    레거시 서버렌더 HTML 은 기본 비활성 — admin-web 으로 이전됨. 비활성 시
    구 URL 을 admin-web local-agents 페이지로 303 리다이렉트한다(404 차단 대신 신규 UI 안내).
    HAEHAN_ADMIN_LEGACY_UI_FALLBACK 활성 시에만 구 서버렌더 HTML 을 반환.

    본 라우트는 HTML/리다이렉트만 내려주며, 실제 목록/요청 호출은 브라우저 JS 가
    기존 /api/v1/local-agents , /api/v1/local-agents/{id}/capture-screenshot
    엔드포인트로 수행한다. 서버 측 상태 변경은 없다.
    """
    if not _legacy_admin_ui_fallback_enabled():
        # 레거시 비활성: admin-web local-agents 페이지로 안내(404 대신 303 리다이렉트).
        # 2026-09-30 수정(실측 발견): "/orchestrator/admin-web/local-agents" 로 리다이렉트
        # 하고 있었는데 그 경로 자체가 존재하지 않아 매번 404 — admin-web/src/lib/nav.ts의
        # 실제 라우트는 prefix 없는 "/local-agents"(NAV_GROUPS_ALL의 "Local Agents" 항목,
        # href: "/local-agents"). 실제 엔드포인트 스윕(137개 GET)으로 발견.
        return RedirectResponse(url="/local-agents", status_code=303)
    return HTMLResponse(content=_LOCAL_AGENTS_HTML, status_code=200)


__all__ = ["admin_ui_router"]
