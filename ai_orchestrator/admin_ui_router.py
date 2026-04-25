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
    device_token 은 절대 읽거나 표시하지 않는다.
  - 에이전트 필드는 모두 textContent 로만 DOM 에 삽입해 XSS 를 차단한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from .auth import require_role

admin_ui_router = APIRouter(prefix="/admin", tags=["admin-ui"])


# confirm 문구와 성공 안내 문구는 테스트가 substring 으로 검증한다.
# (본 HTML 은 jinja2 를 쓰지 않으므로 중괄호 이스케이프 이슈 없음)
_LOCAL_AGENTS_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>로컬 에이전트 관리 (사전 점검 / 실제 1회)</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
         sans-serif; margin: 24px; color: #222; }
  h1 { font-size: 20px; margin-bottom: 8px; }
  .note { color: #666; margin-bottom: 16px; font-size: 13px; }
  .warn { color: #b00020; font-weight: 600; margin-top: 4px;
          font-size: 12px; }
  table { border-collapse: collapse; width: 100%; max-width: 960px; }
  th, td { border: 1px solid #ddd; padding: 8px 10px; text-align: left;
           font-size: 14px; vertical-align: top; }
  th { background: #f7f7f7; }
  button.dry-run-btn { padding: 6px 10px; border: 1px solid #2a5db0;
                       background: #eaf1ff; color: #2a5db0; cursor: pointer;
                       border-radius: 4px; font-size: 13px; margin-right: 6px; }
  button.real-capture-btn { padding: 6px 10px; border: 1px solid #a00020;
                            background: #fde7ea; color: #a00020;
                            cursor: pointer; border-radius: 4px;
                            font-size: 13px; font-weight: 600; }
  button[disabled] { opacity: 0.55; cursor: progress; }
  .status { margin-top: 6px; font-size: 12px; color: #333; white-space: pre-wrap; }
  .status.ok { color: #1a6d1a; }
  .status.err { color: #b00020; }
  .empty { color: #888; }
</style>
</head>
<body>
<h1>로컬 에이전트 — 화면 캡처 요청</h1>
<p class="note">
  사전 점검 버튼은 <b>dry_run=true</b> 요청만 생성합니다.
  실제 1회 캡처 버튼은 <b>dry_run=false</b> 요청을 생성하며,
  클릭 시 브라우저 확인창(confirm)을 통과해야 합니다.
  서버에는 이미지가 업로드되지 않습니다.
</p>
<p class="warn">
  ※ Google/YouTube 계열은 보안 정책상 화면 캡처 probe 가 차단됩니다.
  브라우저 열기(open_local_browser)만 사용하세요.
</p>

<div id="root">
  <p class="empty">에이전트 목록을 불러오는 중…</p>
</div>

<script>
(function () {
  "use strict";

  // ── 상수 ──────────────────────────────────────────────────────────
  var AGENTS_URL = "/api/v1/local-agents";

  // 사전 점검용 body (기존 버튼, 변경 없음)
  var DRY_RUN_BODY = { dry_run: true, reason: "ui_dry_run_check" };

  // 실제 1회 캡처용 body — dry_run 은 반드시 false 로 명시해서 보낸다.
  // 이 상수는 window.confirm 게이트를 통과한 코드 경로에서만 사용된다.
  var REAL_CAPTURE_BODY = { dry_run: false, reason: "ui_capture_once_request" };

  // window.confirm 에 띄울 경고 문구
  var CONFIRM_REAL_CAPTURE =
    "승인 후 로컬 PC에서 1회 화면 캡처가 실행됩니다." +
    " 서버에는 이미지가 업로드되지 않습니다. 계속하시겠습니까?";

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

  // ── 에이전트 목록 렌더링 ─────────────────────────────────────────
  function renderAgents(root, agents) {
    root.innerHTML = "";
    if (!agents || agents.length === 0) {
      root.appendChild(el("p", { "class": "empty" },
        "등록된 로컬 에이전트가 없습니다."));
      return;
    }

    var table = el("table");
    var thead = el("thead");
    var trh = el("tr");
    ["agent_id", "host", "os", "version", "요청"].forEach(function (h) {
      trh.appendChild(el("th", null, h));
    });
    thead.appendChild(trh);
    table.appendChild(thead);

    var tbody = el("tbody");
    agents.forEach(function (agent) {
      var tr = el("tr");
      tr.appendChild(el("td", null, agent.agent_id || ""));
      tr.appendChild(el("td", null, agent.host || ""));
      tr.appendChild(el("td", null, agent.os_name || ""));
      tr.appendChild(el("td", null, agent.version || ""));

      var tdAction = el("td");

      // 1) 기존 사전 점검 버튼
      var dryBtn = el("button",
        { "class": "dry-run-btn",
          "data-agent-id": agent.agent_id || "" },
        "화면 캡처 사전 점검");

      // 2) 신규 실제 1회 캡처 버튼 (위험 스타일)
      var realBtn = el("button",
        { "class": "real-capture-btn",
          "data-agent-id": agent.agent_id || "" },
        "실제 1회 화면 캡처 요청");

      var warnLine = el("div", { "class": "warn" },
        "※ 실제 1회 캡처는 승인 후 로컬 PC에서 1회만 실행됩니다." +
        " 서버에는 이미지가 업로드되지 않습니다.");

      var statusBox = el("div", { "class": "status" });

      dryBtn.addEventListener("click", function () {
        requestDryRun(dryBtn, statusBox);
      });
      realBtn.addEventListener("click", function () {
        requestRealCapture(realBtn, statusBox);
      });

      tdAction.appendChild(dryBtn);
      tdAction.appendChild(realBtn);
      tdAction.appendChild(warnLine);
      tdAction.appendChild(statusBox);
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    root.appendChild(table);
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
) -> HTMLResponse:
    """관리자 전용 로컬 에이전트 화면.

    본 라우트는 HTML 만 내려주며, 실제 목록/요청 호출은 브라우저 JS 가
    기존 /api/v1/local-agents , /api/v1/local-agents/{id}/capture-screenshot
    엔드포인트로 수행한다. 서버 측 상태 변경은 없다.
    """
    return HTMLResponse(content=_LOCAL_AGENTS_HTML, status_code=200)


__all__ = ["admin_ui_router"]
