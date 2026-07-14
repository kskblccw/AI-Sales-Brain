/**
 * app.js — 电商智能客服前端逻辑
 *
 * 功能：
 *  - 多会话管理（PostgreSQL 持久化 + localStorage 本地缓存）
 *  - SSE 流式接收响应
 *  - 消息气泡渲染
 *  - 人工审核交互
 *  - 切换会话时恢复聊天记录
 */

// ── 会话管理（localStorage 缓存层，服务端 Postgres 为权威来源）──────────
const STORAGE_KEY = "ecommerce_cs_sessions";

function getCachedSessions() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch { return {}; }
}

function cacheSession(id, title) {
  const sessions = getCachedSessions();
  sessions[id] = { title: title || id.slice(0, 16), updatedAt: Date.now() };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

function getCurrentSessionId() {
  let id = sessionStorage.getItem("cs_current_session");
  if (!id) {
    id = "sess_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
    sessionStorage.setItem("cs_current_session", id);
  }
  return id;
}

function setCurrentSessionId(id) {
  sessionStorage.setItem("cs_current_session", id);
}

// ── DOM 元素 ────────────────────────────────────────────────────────────────
const chatMessages = document.getElementById("chatMessages");
const chatInput = document.getElementById("chatInput");
const btnSend = document.getElementById("btnSend");
const approvalBanner = document.getElementById("approvalBanner");
const sessionList = document.getElementById("sessionList");

let currentAssistantBubble = null;
let isProcessing = false;

// ── 初始化 ──────────────────────────────────────────────────────────────────
async function init() {
  await loadSessionList();
  // 如果是已有会话，加载历史
  const currentId = getCurrentSessionId();
  if (currentId) {
    await loadChatHistory(currentId);
  }
  chatInput.focus();
}

// ── 会话列表（从服务器加载，合并本地缓存）─────────────────────────────────
async function loadSessionList() {
  try {
    const resp = await fetch("/api/sessions");
    if (!resp.ok) throw new Error("API error");
    const serverIds = await resp.json();  // 纯字符串数组 ["sess_xxx", ...]
    const currentId = getCurrentSessionId();
    const local = getCachedSessions();

    if (serverIds.length === 0) {
      sessionList.innerHTML = '<div style="padding:20px;text-align:center;color:#aaa;font-size:13px">暂无历史会话</div>';
      return;
    }

    // 合并本地缓存标题
    sessionList.innerHTML = serverIds.map(id => {
      const active = id === currentId ? " active" : "";
      const title = (local[id] && local[id].title) ? local[id].title : id.slice(0, 16);
      return `<div class="session-item${active}" onclick="switchSession('${id}')">
        <span class="session-title">${escapeHtml(title)}</span>
        <button class="btn-delete-session" onclick="deleteSession(event, '${id}')" title="删除会话">x</button>
      </div>`;
    }).join("");

  } catch (e) {
    renderLocalSessionList();
  }
}

async function deleteSession(event, sessionId) {
  event.stopPropagation();  // 阻止触发 switchSession
  if (!confirm('确定删除此会话？')) return;
  try {
    await fetch(`/api/chat/${sessionId}`, { method: "DELETE" });
    // 清理本地缓存
    const sessions = getCachedSessions();
    delete sessions[sessionId];
    saveCachedSessions(sessions);
    // 如果删除的是当前会话，新建一个
    if (getCurrentSessionId() === sessionId) {
      newSession();
    } else {
      loadSessionList();
    }
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
}

function saveCachedSessions(sessions) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

function renderLocalSessionList() {
  const sessions = getCachedSessions();
  const currentId = getCurrentSessionId();
  const entries = Object.entries(sessions).sort((a, b) => b[1].updatedAt - a[1].updatedAt);
  if (entries.length === 0) {
    sessionList.innerHTML = '<div style="padding:20px;text-align:center;color:#aaa;font-size:13px">暂无历史会话</div>';
    return;
  }
  sessionList.innerHTML = entries.map(([id, s]) => {
    const active = id === currentId ? " active" : "";
    return `<div class="session-item${active}" onclick="switchSession('${id}')">
      <span class="session-title">${escapeHtml(s.title || id.slice(0, 12))}</span>
      <button class="btn-delete-session" onclick="deleteLocalSession(event, '${id}')" title="删除会话">x</button>
    </div>`;
  }).join("");
}

function deleteLocalSession(event, sessionId) {
  event.stopPropagation();
  if (!confirm('确定删除此会话？')) return;
  const sessions = getCachedSessions();
  delete sessions[sessionId];
  saveCachedSessions(sessions);
  if (getCurrentSessionId() === sessionId) newSession();
  else renderLocalSessionList();
}

// ── 切换会话（从服务器加载历史，不刷新页面）─────────────────────────────
async function switchSession(id) {
  setCurrentSessionId(id);
  // 清空当前消息
  chatMessages.innerHTML = '<div style="text-align:center;padding:20px;color:#aaa;">加载中...</div>';
  approvalBanner.style.display = "none";
  await loadSessionList();
  await loadChatHistory(id);
}

function newSession() {
  const newId = "sess_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
  setCurrentSessionId(newId);
  chatMessages.innerHTML = `
    <div class="welcome-message">
      <div class="welcome-icon">🛒</div>
      <h2>欢迎来到电商智能客服</h2>
      <p>我可以帮您：</p>
      <div class="quick-actions">
        <button onclick="quickAsk('帮我查一下我的订单')">📦 查询订单</button>
        <button onclick="quickAsk('推荐一款降噪耳机')">🛍️ 商品推荐</button>
        <button onclick="quickAsk('如何申请退货？')">🔧 退换货</button>
        <button onclick="quickAsk('支持哪些支付方式？')">📋 常见问题</button>
      </div>
    </div>`;
  approvalBanner.style.display = "none";
  loadSessionList();
  chatInput.focus();
}

// ── 加载会话历史 ───────────────────────────────────────────────────────────
async function loadChatHistory(sessionId) {
  try {
    console.log("[history] loading session:", sessionId);
    const resp = await fetch(`/api/chat/${encodeURIComponent(sessionId)}/history`);
    console.log("[history] response status:", resp.status);
    if (!resp.ok) {
      const errText = await resp.text();
      console.error("[history] server error:", resp.status, errText);
      showWelcome();
      return;
    }
    const data = await resp.json();
    console.log("[history] got", (data.messages || []).length, "messages");
    const messages = data.messages || [];

    if (messages.length === 0) {
      console.log("[history] empty, showing welcome");
      showWelcome();
      return;
    }

    chatMessages.innerHTML = "";
    for (const msg of messages) {
      const role = msg.role === "user" ? "user" : "assistant";
      if (role === "assistant" && !msg.content.trim()) continue;
      if (msg.role === "system") continue;
      renderMessage(role, msg.content);
    }
    console.log("[history] rendered", messages.length, "messages");
    scrollToBottom();
  } catch (e) {
    console.error("[history] fetch error:", e);
    showWelcome();
  }
}

function showWelcome() {
  chatMessages.innerHTML = `
    <div class="welcome-message">
      <div class="welcome-icon">🛒</div>
      <h2>欢迎来到电商智能客服</h2>
      <p>我可以帮您：</p>
      <div class="quick-actions">
        <button onclick="quickAsk('帮我查一下我的订单')">📦 查询订单</button>
        <button onclick="quickAsk('推荐一款降噪耳机')">🛍️ 商品推荐</button>
        <button onclick="quickAsk('如何申请退货？')">🔧 退换货</button>
        <button onclick="quickAsk('支持哪些支付方式？')">📋 常见问题</button>
      </div>
    </div>`;
}

// ── 消息渲染 ────────────────────────────────────────────────────────────────
function renderMessage(role, content) {
  const welcome = chatMessages.querySelector(".welcome-message");
  if (welcome) welcome.remove();

  const div = document.createElement("div");
  div.className = `message ${role}`;
  const avatarEmoji = role === "user" ? "👤" : "🤖";
  div.innerHTML = `
    <div class="message-avatar">${avatarEmoji}</div>
    <div class="message-bubble">${escapeHtml(content)}</div>
  `;
  chatMessages.appendChild(div);
  return div;
}

function addMessage(role, content) {
  return renderMessage(role, content);
}

function addStatusMessage(label) {
  const div = document.createElement("div");
  div.className = "message status";
  div.innerHTML = `<div class="message-bubble">${label}</div>`;
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

function createAssistantBubble() {
  const welcome = chatMessages.querySelector(".welcome-message");
  if (welcome) welcome.remove();

  const div = document.createElement("div");
  div.className = "message assistant";
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-bubble"><span class="typing-indicator"></span></div>
  `;
  chatMessages.appendChild(div);
  return div;
}

function appendToBubble(bubble, text) {
  const bubbleDiv = bubble.querySelector(".message-bubble");
  const indicator = bubbleDiv.querySelector(".typing-indicator");
  if (indicator) indicator.remove();
  bubbleDiv.textContent += text;
  scrollToBottom();
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML.replace(/\n/g, "<br>");
}

// ── 发送消息 ────────────────────────────────────────────────────────────────
async function sendMessage() {
  const message = chatInput.value.trim();
  if (!message || isProcessing) return;

  isProcessing = true;
  btnSend.disabled = true;
  chatInput.value = "";
  approvalBanner.style.display = "none";

  addMessage("user", message);

  const sessionId = getCurrentSessionId();
  cacheSession(sessionId, message.slice(0, 30));
  loadSessionList();

  currentAssistantBubble = createAssistantBubble();

  try {
    const response = await fetch(
      `/api/chat/${sessionId}/stream?message=${encodeURIComponent(message)}`
    );

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data:")) {
          const dataStr = line.slice(5).trim();
          if (!dataStr) continue;
          try {
            handleSSEEvent(JSON.parse(dataStr));
          } catch (e) {}
        }
      }
    }
  } catch (err) {
    if (currentAssistantBubble) {
      appendToBubble(currentAssistantBubble, `\n\n网络错误：${err.message}`);
    }
  }

  isProcessing = false;
  btnSend.disabled = false;
  chatInput.focus();
}

function handleSSEEvent(data) {
  switch (data.type) {
    case "status":
      addStatusMessage(data.label);
      break;
    case "token":
      if (currentAssistantBubble) {
        appendToBubble(currentAssistantBubble, data.content);
      }
      break;
    case "approval_required":
      approvalBanner.style.display = "block";
      window._pendingApprovalData = data.data;
      break;
    case "done":
      currentAssistantBubble = null;
      loadSessionList();
      break;
    case "error":
      if (currentAssistantBubble) {
        appendToBubble(currentAssistantBubble, `\n\n错误：${data.message}`);
      }
      currentAssistantBubble = null;
      break;
  }
}

// ── 人工审核 ────────────────────────────────────────────────────────────────
async function handleApproval(approved) {
  const sessionId = getCurrentSessionId();
  const endpoint = approved ? "approve" : "reject";

  try {
    const resp = await fetch(`/api/human/${endpoint}/${sessionId}`, { method: "POST" });
    const result = await resp.json();
    approvalBanner.style.display = "none";
    addMessage("assistant", result.answer || (approved ? "已批准" : "已拒绝"));
  } catch (err) {
    addMessage("assistant", `操作失败：${err.message}`);
  }
}

// ── 快捷提问 ────────────────────────────────────────────────────────────────
function quickAsk(question) {
  chatInput.value = question;
  sendMessage();
}

// ── 键盘事件 ────────────────────────────────────────────────────────────────
function handleKeyDown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

// ── 启动 ────────────────────────────────────────────────────────────────────
init();
