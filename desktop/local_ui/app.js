/* Haehan AI Desktop — 메인 앱 로직 */
"use strict";

const App = (() => {
  // ── 기본 메뉴 항목 (서버 미연결 시 즉시 렌더) ────────────────────────────
  const DEFAULT_MENU = [
    { id: "chat",       label: "대화",         icon: "💬", visible: true  },
    { id: "task_queue", label: "작업 큐",       icon: "📋", visible: true  },
    { id: "approval",   label: "승인 대기",     icon: "✅", visible: true  },
    { id: "news",       label: "뉴스",          icon: "📰", visible: true  },
    { id: "eum",        label: "EUM 단말기",    icon: "🏗️", visible: true  },
    { id: "browser",   label: "브라우저 상태", icon: "🌐", visible: true  },
    { id: "screenshot", label: "최근 스크린샷", icon: "📸", visible: false },
    { id: "logs",       label: "로그",          icon: "📊", visible: true  },
    { id: "settings",   label: "설정",          icon: "⚙️", visible: true  },
  ];

  // ── 상태 ──────────────────────────────────────────────────────────────────
  let ws = null;
  let wsReady = false;
  let currentPanel = "chat";
  let menuItems = DEFAULT_MENU.map(m => ({ ...m }));
  let dragSrcIdx = null;
  let sidebarCollapsed = false;

  const user = {
    id:   localStorage.getItem("user_id")   || "default",
    role: localStorage.getItem("user_role") || "any",
    name: localStorage.getItem("user_name") || "사용자",
  };

  // ── DOM ───────────────────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);

  const sidebar         = $("sidebar");
  const sidebarNav      = $("sidebar-nav");
  const btnCollapse     = $("btn-collapse");
  const btnExpand       = $("btn-expand");
  const btnNewChat      = $("btn-new-chat");
  const btnEditMenu     = $("btn-edit-menu");
  const connDot         = $("conn-dot");
  const connText        = $("conn-text");
  const chatInput       = $("chat-input");
  const btnSend         = $("btn-send");
  const chatMessages    = $("chat-messages");
  const chatEmpty       = $("chat-empty");
  const drawerOverlay   = $("menu-drawer-overlay");
  const drawer          = $("menu-drawer");
  const drawerList      = $("drawer-list");
  const btnDrawerClose  = $("btn-drawer-close");
  const btnDrawerCancel = $("btn-drawer-cancel");
  const btnDrawerSave   = $("btn-drawer-save");
  const sbAvatar        = $("sb-avatar");
  const sbUserName      = $("user-name");
  const sbUserRole      = $("user-role");

  // ── WebSocket ─────────────────────────────────────────────────────────────
  function connectWS() {
    const url = localStorage.getItem("server_url_local") || "ws://127.0.0.1:8765/ws/ui";
    ws = new WebSocket(url);

    ws.onopen = () => {
      wsReady = true;
      setConnStatus(true);
      ws.send(JSON.stringify({ action: "load_menu", user_id: user.id, role: user.role }));
    };

    ws.onclose = () => {
      wsReady = false;
      setConnStatus(false);
      setTimeout(connectWS, 3000);
    };

    ws.onerror = () => {
      wsReady = false;
      setConnStatus(false);
    };

    ws.onmessage = e => {
      try { handleMessage(JSON.parse(e.data)); } catch (_) {}
    };
  }

  function send(obj) {
    if (wsReady) ws.send(JSON.stringify(obj));
  }

  // ── 메시지 처리 ───────────────────────────────────────────────────────────
  function handleMessage(msg) {
    switch (msg.type) {
      case "menu":
        // 서버에서 받은 메뉴로 업데이트
        if (Array.isArray(msg.items) && msg.items.length > 0) {
          menuItems = msg.items;
          renderNav();
        }
        break;
      case "menu_saved":
        closeDrawer();
        break;
      case "chat":
        appendChat(msg.role, msg.text, msg.ts);
        break;
      case "system":
        appendSystem(msg.text);
        break;
      case "task":
        appendTask(msg);
        break;
      case "browser_status":
        updateBrowserStatus(msg);
        break;
    }
  }

  // ── 연결 상태 ─────────────────────────────────────────────────────────────
  function setConnStatus(ok) {
    if (ok) {
      connDot.classList.add("on");
      connText.textContent = "연결됨";
    } else {
      connDot.classList.remove("on");
      connText.textContent = "연결 중…";
    }
  }

  // ── 사이드바 접기/펼치기 ──────────────────────────────────────────────────
  function collapseSidebar() {
    sidebarCollapsed = true;
    sidebar.classList.add("collapsed");
    localStorage.setItem("sb_collapsed", "1");
  }

  function expandSidebar() {
    sidebarCollapsed = false;
    sidebar.classList.remove("collapsed");
    localStorage.setItem("sb_collapsed", "0");
  }

  btnCollapse.onclick = () => sidebarCollapsed ? expandSidebar() : collapseSidebar();
  btnExpand.onclick   = expandSidebar;

  // ── 새 대화 ──────────────────────────────────────────────────────────────
  btnNewChat.onclick = () => {
    // 메시지 초기화 (empty 상태 복원)
    chatMessages.innerHTML = "";
    if (chatEmpty) {
      chatMessages.appendChild(chatEmpty);
      chatEmpty.style.display = "";
    }
    navigateTo("chat");
  };

  // ── 네비게이션 렌더링 ──────────────────────────────────────────────────────
  function renderNav() {
    sidebarNav.innerHTML = "";
    const visible = menuItems.filter(m => m.visible !== false);

    visible.forEach((item, idx) => {
      const el = document.createElement("button");
      el.className = "nav-item" + (item.id === currentPanel ? " active" : "");
      el.dataset.id  = item.id;
      el.dataset.idx = idx;
      el.draggable   = true;
      el.type        = "button";
      el.innerHTML = `
        <span class="nav-icon">${item.icon}</span>
        <span class="nav-label">${item.label}</span>
        ${item.id === "approval"   ? '<span class="badge" id="badge-approval" style="display:none">0</span>' : ""}
        ${item.id === "task_queue" ? '<span class="badge" id="badge-task"     style="display:none">0</span>' : ""}
        <span class="drag-handle" title="드래그로 순서 변경">⠿</span>`;

      el.addEventListener("click", () => navigateTo(item.id));

      // 드래그 앤 드롭
      el.addEventListener("dragstart", e => {
        dragSrcIdx = idx;
        e.dataTransfer.effectAllowed = "move";
        el.classList.add("dragging");
      });
      el.addEventListener("dragover", e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        el.classList.add("drag-over");
      });
      el.addEventListener("dragleave", () => el.classList.remove("drag-over"));
      el.addEventListener("drop", e => {
        e.preventDefault();
        el.classList.remove("drag-over");
        if (dragSrcIdx === null || dragSrcIdx === idx) return;
        const vis    = menuItems.filter(m => m.visible !== false);
        const hidden = menuItems.filter(m => m.visible === false);
        const moved  = vis.splice(dragSrcIdx, 1)[0];
        vis.splice(idx, 0, moved);
        menuItems = [...vis, ...hidden];
        renderNav();
      });
      el.addEventListener("dragend", () => {
        dragSrcIdx = null;
        sidebarNav.querySelectorAll(".nav-item").forEach(n => {
          n.classList.remove("dragging", "drag-over");
        });
      });

      sidebarNav.appendChild(el);
    });
  }

  // ── 패널 전환 ─────────────────────────────────────────────────────────────
  function navigateTo(id) {
    currentPanel = id;

    // 패널 활성화
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    const panel = document.getElementById("panel-" + id);
    if (panel) panel.classList.add("active");

    // 사이드바 활성 상태
    sidebarNav.querySelectorAll(".nav-item").forEach(n => {
      n.classList.toggle("active", n.dataset.id === id);
    });
  }

  // ── 채팅 유틸 ─────────────────────────────────────────────────────────────
  function hideChatEmpty() {
    if (chatEmpty) chatEmpty.style.display = "none";
  }

  function scrollToBottom() {
    const scroll = $("chat-scroll");
    if (scroll) requestAnimationFrame(() => { scroll.scrollTop = scroll.scrollHeight; });
  }

  function appendChat(role, text, ts) {
    hideChatEmpty();
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;
    const time   = ts ? new Date(ts * 1000).toLocaleTimeString("ko", { hour: "2-digit", minute: "2-digit" }) : "";
    const avatar = role === "user" ? "👤" : role === "assistant" ? "🤖" : "ℹ️";
    wrap.innerHTML = `
      <div class="msg-avatar">${avatar}</div>
      <div class="msg-body">
        <div class="msg-text">${escHtml(text)}</div>
        ${time ? `<div class="msg-time">${time}</div>` : ""}
      </div>`;
    chatMessages.appendChild(wrap);
    scrollToBottom();
    navigateTo("chat");
  }

  function appendSystem(text) {
    hideChatEmpty();
    const wrap = document.createElement("div");
    wrap.className = "msg system";
    wrap.innerHTML = `
      <div class="msg-avatar">ℹ️</div>
      <div class="msg-body"><div class="msg-text">${escHtml(text)}</div></div>`;
    chatMessages.appendChild(wrap);
    scrollToBottom();
  }

  function appendTask(msg) {
    hideChatEmpty();
    const wrap    = document.createElement("div");
    wrap.className = "task-card";
    const riskCls = { low: "risk-low", medium: "risk-medium", high: "risk-high" }[msg.risk_level] || "risk-low";
    wrap.innerHTML = `
      <div class="task-header">
        <span class="task-badge ${riskCls}">${(msg.risk_level || "LOW").toUpperCase()}</span>
        <span class="task-title">${escHtml(msg.action_type || "작업")}</span>
      </div>
      <div class="task-desc">${escHtml(msg.description || msg.domain || "")}</div>
      <div class="task-actions">
        <button class="btn-approve" onclick="App.approve('${msg.task_id}', this)">✅ 승인</button>
        <button class="btn-reject"  onclick="App.reject('${msg.task_id}', this)">❌ 거부</button>
      </div>`;
    chatMessages.appendChild(wrap);
    scrollToBottom();
    updateBadge("badge-approval", 1, true);
    updateBadge("badge-task",     1, true);
    navigateTo("chat");
  }

  function approve(taskId, btn) {
    send({ action: "approve", task_id: taskId });
    btn.closest(".task-actions").innerHTML = '<span style="color:var(--green);font-size:12px">✅ 승인 완료</span>';
    updateBadge("badge-approval", -1, true);
  }

  function reject(taskId, btn) {
    send({ action: "reject", task_id: taskId });
    btn.closest(".task-actions").innerHTML = '<span style="color:var(--text-dim);font-size:12px">❌ 거부됨</span>';
    updateBadge("badge-approval", -1, true);
  }

  function updateBadge(id, delta, relative) {
    const el = document.getElementById(id);
    if (!el) return;
    const cur  = parseInt(el.textContent) || 0;
    const next = relative ? cur + delta : delta;
    if (next <= 0) { el.style.display = "none"; el.textContent = "0"; }
    else           { el.style.display = "";     el.textContent = next; }
  }

  function updateBrowserStatus(msg) {
    const port  = $("bs-port");
    const bsUrl = $("bs-url");
    const state = $("bs-state");
    if (port  && msg.port)  port.textContent  = msg.port;
    if (bsUrl && msg.url)   bsUrl.textContent = msg.url.length > 60 ? msg.url.slice(0, 60) + "…" : msg.url;
    if (state && msg.state) state.textContent = msg.state;
  }

  // ── 채팅 전송 ─────────────────────────────────────────────────────────────
  function sendChat() {
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = "";
    autoResize();
    btnSend.disabled = true;
    // 로컬에 즉시 표시
    appendChat("user", text, Date.now() / 1000);
    // 서버 전송
    send({ action: "chat", text });
  }

  btnSend.onclick = sendChat;

  chatInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });

  chatInput.addEventListener("input", () => {
    autoResize();
    btnSend.disabled = !chatInput.value.trim();
  });

  function autoResize() {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
  }

  // 퀵칩 전송
  function quickSend(text) {
    chatInput.value = text;
    autoResize();
    btnSend.disabled = false;
    sendChat();
  }

  // ── 메뉴 편집 드로어 ───────────────────────────────────────────────────────
  btnEditMenu.onclick   = openDrawer;
  btnDrawerClose.onclick   = closeDrawer;
  btnDrawerCancel.onclick  = closeDrawer;
  btnDrawerSave.onclick    = saveMenuDrawer;
  drawerOverlay.onclick    = closeDrawer;

  function openDrawer() {
    renderDrawerList();
    drawerOverlay.classList.add("open");
    drawer.classList.add("open");
  }

  function closeDrawer() {
    drawerOverlay.classList.remove("open");
    drawer.classList.remove("open");
  }

  let drawerDragSrc = null;

  function renderDrawerList() {
    drawerList.innerHTML = "";
    menuItems.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className  = "drawer-item";
      row.dataset.id  = item.id;
      row.dataset.idx = idx;
      row.draggable   = true;
      row.innerHTML = `
        <label>
          <input type="checkbox" ${item.visible !== false ? "checked" : ""} data-id="${item.id}">
          <span class="d-icon">${item.icon}</span>
          <span class="d-label">${item.label}</span>
        </label>
        <span class="d-handle">⠿</span>`;

      row.addEventListener("dragstart", e => {
        drawerDragSrc = idx;
        e.dataTransfer.effectAllowed = "move";
        row.style.opacity = ".5";
      });
      row.addEventListener("dragover", e => {
        e.preventDefault();
        row.style.background = "var(--surface3)";
      });
      row.addEventListener("dragleave", () => row.style.background = "");
      row.addEventListener("drop", e => {
        e.preventDefault();
        row.style.background = "";
        if (drawerDragSrc === null || drawerDragSrc === idx) return;
        const moved = menuItems.splice(drawerDragSrc, 1)[0];
        menuItems.splice(idx, 0, moved);
        renderDrawerList();
      });
      row.addEventListener("dragend", () => {
        drawerDragSrc = null;
        drawerList.querySelectorAll(".drawer-item").forEach(r => {
          r.style.opacity    = "";
          r.style.background = "";
        });
      });

      drawerList.appendChild(row);
    });
  }

  function saveMenuDrawer() {
    const checks = drawerList.querySelectorAll("input[type=checkbox]");
    checks.forEach(cb => {
      const item = menuItems.find(m => m.id === cb.dataset.id);
      if (item) item.visible = cb.checked;
    });
    send({ action: "save_menu", user_id: user.id, items: menuItems });
    renderNav();
    closeDrawer();
  }

  // ── 설정 패널 ─────────────────────────────────────────────────────────────
  const btnSettingsSave = $("btn-settings-save");
  if (btnSettingsSave) {
    btnSettingsSave.onclick = () => {
      const serverUrl = $("set-server-url")?.value.trim();
      const name      = $("set-user-name")?.value.trim();
      const role      = $("set-user-role")?.value;

      if (name) {
        user.name = name;
        localStorage.setItem("user_name", name);
        sbUserName.textContent = name;
        sbAvatar.textContent   = name.charAt(0).toUpperCase();
      }
      if (role) {
        user.role = role;
        localStorage.setItem("user_role", role);
        sbUserRole.textContent = role === "owner" ? "Owner" : role === "admin" ? "Admin" : "User";
      }
      if (serverUrl) {
        localStorage.setItem("server_url", serverUrl);
      }
      appendSystem("✅ 설정이 저장되었습니다.");
      navigateTo("chat");
    };
  }

  // ── 유틸 ──────────────────────────────────────────────────────────────────
  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g,  "&lt;")
      .replace(/>/g,  "&gt;")
      .replace(/"/g,  "&quot;");
  }

  // ── 초기화 ────────────────────────────────────────────────────────────────
  function init() {
    // 사이드바 상태 복원
    if (localStorage.getItem("sb_collapsed") === "1") collapseSidebar();

    // 사용자 정보 표시
    sbUserName.textContent = user.name;
    sbAvatar.textContent   = user.name.charAt(0).toUpperCase();
    sbUserRole.textContent = user.role === "owner" ? "Owner" : user.role === "admin" ? "Admin" : "User";

    // 설정 패널 초기값
    const su = $("set-server-url");
    const sn = $("set-user-name");
    const sr = $("set-user-role");
    if (su) su.value = localStorage.getItem("server_url") || "ws://localhost:8000/ws/desktop";
    if (sn) sn.value = user.name;
    if (sr) sr.value = user.role;

    // 기본 메뉴 즉시 렌더 (서버 응답 전)
    renderNav();

    // 채팅 패널을 기본 화면으로
    navigateTo("chat");

    // WebSocket 연결
    connectWS();

    // 시작 메시지
    appendSystem("🤖 Haehan AI 앱이 준비됐습니다. 메시지를 입력하거나 빠른 메뉴를 선택하세요.");
  }

  return { init, approve, reject, quickSend };
})();

window.App = App;
document.addEventListener("DOMContentLoaded", App.init);
