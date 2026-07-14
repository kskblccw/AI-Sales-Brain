/**
 * app.js — 电商智能客服前端逻辑
 *
 * 功能：
 *  - 多会话管理（localStorage）
 *  - SSE 流式接收响应
 *  - 消息气泡渲染
 *  - 人工审核交互
 */

// ── 会话管理 ────────────────────────────────────────────────────────────────
const STORAGE_KEY = "ecommerce_cs_sessions";

function getSessions() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch { return {}; }
}

function saveSessions(sessions) {
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

// ── DOM 元素 ─────────────────────────────────────────────────────────────────
const chatMessages = document.getElementById("chatMessages");
const chatInput = document.getElementById("chatInput");
const btnSend = document.getElementById("btnSend");
const approvalBanner = document.getElementById("approvalBanner");
const sessionList = document.getElementById("sessionList");

let currentAssistantBubble = null; // 当前正在流式写入的 AI 气泡
let isProcessing = false;

// ── 初始化 ───────────────────────────────────────────────────────────────────
function init() {
  renderSessionList();
  chatInput.focus();
}

// ── 会话列表 ────────────────────────────────────────────────────────────────
function renderSessionList() {
  const sessions = getSessions();
  const currentId = getCurrentSessionId();
  const entries = Object.entries(sessions).sort((a, b) => b[1].updatedAt - a[1].updatedAt);

  if (entries.length === 0) {
    sessionList.innerHTML = '<div style="padding:20px;text-align:center;color:#aaa;font-size:13px">暂无历史会话</div>';
    return;
  }

  sessionList.innerHTML = entries.map(([id, s]) => {
    const active = id === currentId ? " active" : "";
    const title = s.title || id.slice(0, 12);
    return `<div class="session-item${active}" onclick="switchSession('${id}')">${title}</div>`;
  }).join("");
}

function newSession() {
  const newId = "sess_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
  sessionStorage.setItem("cs_current_session", newId);
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
  renderSessionList();
  chatInput.focus();
}

function switchSession(id) {
  sessionStorage.setItem("cs_current_session", id);
  // 刷新页面加载该会话的消息
  location.reload();
}

// ── 消息渲染 ─────────────────────────────────────────────────────────────────
function addMessage(role, content) {
  // 移除欢迎消息
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
  scrollToBottom();
  return div;
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
  // 移除打字指示器
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

// ── 发送消息 ─────────────────────────────────────────────────────────────────
async function sendMessage() {
  const message = chatInput.value.trim();
  if (!message || isProcessing) return;

  isProcessing = true;
  btnSend.disabled = true;
  chatInput.value = "";
  approvalBanner.style.display = "none";

  // 显示用户消息
  addMessage("user", message);

  // 保存会话
  const sessionId = getCurrentSessionId();
  const sessions = getSessions();
  sessions[sessionId] = {
    title: message.slice(0, 30),
    updatedAt: Date.now(),
  };
  saveSessions(sessions);
  renderSessionList();

  // 创建 AI 气泡
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
            const data = JSON.parse(dataStr);
            handleSSEEvent(data);
          } catch (e) {
            // 忽略非JSON行
          }
        }
      }
    }
  } catch (err) {
    if (currentAssistantBubble) {
      appendToBubble(currentAssistantBubble, `\n\n❌ 网络错误：${err.message}`);
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
      // 显示人工审核横幅
      approvalBanner.style.display = "block";
      window._pendingApprovalData = data.data;
      break;

    case "done":
      currentAssistantBubble = null;
      break;

    case "error":
      if (currentAssistantBubble) {
        appendToBubble(currentAssistantBubble, `\n\n❌ 错误：${data.message}`);
      }
      currentAssistantBubble = null;
      break;
  }
}

// ── 人工审核 ─────────────────────────────────────────────────────────────────
async function handleApproval(approved) {
  const sessionId = getCurrentSessionId();
  const endpoint = approved ? "approve" : "reject";

  try {
    const resp = await fetch(`/api/human/${endpoint}/${sessionId}`, { method: "POST" });
    const result = await resp.json();

    approvalBanner.style.display = "none";
    addMessage("assistant", result.answer || (approved ? "✅ 已批准" : "❌ 已拒绝"));
  } catch (err) {
    addMessage("assistant", `操作失败：${err.message}`);
  }
}

// ── 快捷提问 ─────────────────────────────────────────────────────────────────
function quickAsk(question) {
  chatInput.value = question;
  sendMessage();
}

// ── 键盘事件 ─────────────────────────────────────────────────────────────────
function handleKeyDown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

// ── 启动 ─────────────────────────────────────────────────────────────────────
init();
