document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;

  const convList = document.getElementById('convList');
  const chatName = document.getElementById('chatName');
  const chatBody = document.getElementById('chatBody');
  const msgInput = document.getElementById('msgInput');
  const sendBtn = document.getElementById('sendBtn');
  const attachBtn = document.getElementById('attachBtn');
  const attachInput = document.getElementById('attachInput');
  const chatHeaderSub = document.querySelector('.chat-header-info span');
  const chatAvatar = document.querySelector('.chat-header .conv-avatar');
  const wsState = document.getElementById('wsState');
  const chatBrowseLink = document.getElementById('chatBrowseLink');

  const AI_CONV_ID = 'ai';
  const AI_STORAGE_KEY = `fh_ai_chat_${user.id}`;

  let currentConv = null;
  let socket = null;
  let socketConvId = null;
  let reconnectTimer = null;
  let useRestFallback = false;
  let aiBusy = false;
  const seenMessageIds = new Set();
  let aiHistory = loadAiHistory();

  loadConversations();
  window.addEventListener('beforeunload', () => closeSocket());

  attachBtn?.addEventListener('click', () => {
    if (!currentConv || isAiConversation(currentConv)) {
      showToast(isAiConversation(currentConv) ? 'AI chat does not support file uploads.' : 'Select a conversation first.', 'error');
      return;
    }
    attachInput?.click();
  });
  attachInput?.addEventListener('change', async () => {
    const file = attachInput.files?.[0];
    attachInput.value = '';
    if (!file || !currentConv || isAiConversation(currentConv)) return;
    try {
      const saved = await uploadAttachment(file, { conversation_id: currentConv.id });
      chatBody.insertAdjacentHTML('beforeend', renderAttachmentBubble(saved, true));
      chatBody.scrollTop = chatBody.scrollHeight;
      bindAttachmentActions(chatBody);
      const preview = convList.querySelector(`[data-id="${currentConv.id}"] .conv-preview`);
      if (preview) preview.textContent = `Attachment: ${saved.filename}`;
      showToast('File sent.');
    } catch (err) {
      showToast(err.message || 'Upload failed.', 'error');
    }
  });

  function isAiConversation(conv) {
    return Boolean(conv && (conv.id === AI_CONV_ID || conv.is_ai));
  }

  function loadAiHistory() {
    try {
      const raw = sessionStorage.getItem(AI_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.slice(-20) : [];
    } catch {
      return [];
    }
  }

  function saveAiHistory() {
    try {
      sessionStorage.setItem(AI_STORAGE_KEY, JSON.stringify(aiHistory.slice(-20)));
    } catch {
      // ignore quota
    }
  }

  function aiConversationItem() {
    const last = aiHistory.length ? aiHistory[aiHistory.length - 1].content : 'Ask anything about FreelanceHub';
    return {
      id: AI_CONV_ID,
      is_ai: true,
      other_user: { id: 0, name: 'FreelanceHub AI' },
      project_tag: 'Gemini assistant',
      last_message: last,
      updated_at: new Date().toISOString(),
      unread_count: 0,
    };
  }

  async function loadConversations() {
    convList.innerHTML = '<p style="padding:16px;color:var(--slate);font-size:0.9rem;">Loading…</p>';
    const wantedId = Number(new URLSearchParams(window.location.search).get('conversation') || 0);
    try {
      const conversations = await api('/conversations');
      const items = [aiConversationItem(), ...conversations];
      convList.innerHTML = items.map(renderConvItem).join('');
      bindConvClicks();

      const wanted = wantedId
        ? conversations.find((c) => Number(c.id) === wantedId)
        : null;
      if (wanted) {
        await openConversation(wanted);
        convList.querySelector(`[data-id="${wanted.id}"]`)?.classList.add('active');
      } else {
        await openConversation(aiConversationItem());
        convList.querySelector(`[data-id="${AI_CONV_ID}"]`)?.classList.add('active');
      }
    } catch (err) {
      convList.innerHTML = `
        ${renderConvItem(aiConversationItem())}
        <p style="padding:16px;color:#B23A3A;font-size:0.9rem;">${escapeHtml(err.message)}</p>
      `;
      bindConvClicks();
      await openConversation(aiConversationItem());
      convList.querySelector(`[data-id="${AI_CONV_ID}"]`)?.classList.add('active');
    }
  }

  function renderConvItem(conv) {
    const name = conv.other_user?.name || 'User';
    const aiClass = isAiConversation(conv) ? ' ai-conv' : '';
    return `
      <div class="conv-item${aiClass}" data-id="${conv.id}" data-ai="${isAiConversation(conv) ? '1' : '0'}" data-receiver="${conv.other_user?.id || 0}" data-name="${escapeHtml(name)}" data-tag="${escapeHtml(conv.project_tag || '')}">
        <div class="conv-avatar${isAiConversation(conv) ? ' ai-avatar' : ''}">${isAiConversation(conv) ? 'AI' : initials(name)}</div>
        <div class="conv-info">
          <div class="conv-top-row"><h4>${escapeHtml(name)}</h4><span class="conv-time">${isAiConversation(conv) ? 'online' : timeAgo(conv.updated_at)}</span></div>
          <p class="conv-preview">${escapeHtml(conv.last_message || 'No messages yet')}</p>
          ${conv.project_tag ? `<span class="conv-project-tag">${escapeHtml(conv.project_tag)}</span>` : ''}
        </div>
        ${conv.unread_count ? '<div class="unread-dot"></div>' : ''}
      </div>
    `;
  }

  function bindConvClicks() {
    convList.querySelectorAll('.conv-item').forEach((item) => {
      item.addEventListener('click', async () => {
        convList.querySelectorAll('.conv-item').forEach((i) => i.classList.remove('active'));
        item.classList.add('active');
        item.querySelector('.unread-dot')?.remove();
        const isAi = item.dataset.ai === '1';
        await openConversation({
          id: isAi ? AI_CONV_ID : Number(item.dataset.id),
          is_ai: isAi,
          other_user: { id: Number(item.dataset.receiver), name: item.dataset.name },
          project_tag: item.dataset.tag,
        });
      });
    });
  }

  async function openConversation(conv) {
    currentConv = conv;
    seenMessageIds.clear();
    useRestFallback = false;
    chatName.textContent = conv.other_user?.name || 'Chat';
    if (chatHeaderSub) {
      chatHeaderSub.textContent = isAiConversation(conv)
        ? 'Powered by Gemini · marketplace help'
        : (conv.project_tag ? `Re: ${conv.project_tag}` : 'Direct message');
    }
    if (chatAvatar) {
      chatAvatar.textContent = isAiConversation(conv) ? 'AI' : initials(conv.other_user?.name);
      chatAvatar.classList.toggle('ai-avatar', isAiConversation(conv));
    }
    if (attachBtn) attachBtn.style.visibility = isAiConversation(conv) ? 'hidden' : 'visible';
    if (chatBrowseLink) {
      chatBrowseLink.style.display = isAiConversation(conv) ? 'none' : '';
    }

    if (isAiConversation(conv)) {
      closeSocket();
      setConnectionState('live', 'Gemini');
      renderAiThread();
      return;
    }

    chatBody.innerHTML = '<div class="day-divider">Loading…</div>';
    try {
      const [messages, files] = await Promise.all([
        api(`/conversations/${conv.id}/messages`),
        listAttachments({ conversation_id: conv.id }),
      ]);
      const parts = ['<div class="day-divider">Conversation</div>'];
      if (!messages.length && !files.length) {
        parts.push(`
          <div class="msg-bubble received">
            This is the start of your conversation with ${escapeHtml(conv.other_user?.name || 'them')}.
            <span class="msg-time">Just now</span>
          </div>
        `);
      } else {
        parts.push(...messages.map((m) => {
          seenMessageIds.add(m.id);
          return renderBubble(m, user.id);
        }));
        parts.push(...files.map((file) => renderAttachmentBubble(file, file.uploader_id === user.id)));
      }
      chatBody.innerHTML = parts.join('');
      bindAttachmentActions(chatBody);
      chatBody.scrollTop = chatBody.scrollHeight;
      connectSocket(conv.id);
    } catch (err) {
      chatBody.innerHTML = `<div class="msg-bubble received">${escapeHtml(err.message)}</div>`;
      setConnectionState('offline', 'Offline');
    }
  }

  function renderAiThread() {
    const parts = ['<div class="day-divider">FreelanceHub AI</div>'];
    if (!aiHistory.length) {
      parts.push(`
        <div class="msg-bubble received ai-bubble">
          Hi ${escapeHtml(user.name || 'there')} — I’m your FreelanceHub assistant.
          Ask about posting projects, proposals, contracts, milestones, or messaging tips.
          <span class="msg-time">Ready</span>
        </div>
      `);
    } else {
      aiHistory.forEach((turn) => {
        const mine = turn.role === 'user';
        parts.push(`
          <div class="msg-bubble ${mine ? 'sent' : 'received ai-bubble'}">
            ${escapeHtml(turn.content)}
            <span class="msg-time">${mine ? 'You' : 'AI'}</span>
          </div>
        `);
      });
    }
    chatBody.innerHTML = parts.join('');
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  function wsUrl(conversationId) {
    const base = API_BASE.replace(/^http/, 'ws');
    const token = encodeURIComponent(Auth.getToken() || '');
    return `${base}/ws/conversations/${conversationId}?token=${token}`;
  }

  function setConnectionState(kind, label) {
    if (!wsState) return;
    wsState.className = `ws-state ${kind}`;
    wsState.textContent = label;
  }

  function closeSocket() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (socket) {
      const active = socket;
      socket = null;
      socketConvId = null;
      try {
        active.close();
      } catch {
        // ignore
      }
    }
  }

  function connectSocket(conversationId) {
    closeSocket();
    if (!Auth.getToken()) {
      useRestFallback = true;
      setConnectionState('fallback', 'REST');
      return;
    }
    setConnectionState('offline', 'Connecting…');
    let opened = false;
    try {
      socket = new WebSocket(wsUrl(conversationId));
      socketConvId = conversationId;
    } catch {
      useRestFallback = true;
      setConnectionState('fallback', 'REST');
      return;
    }

    socket.addEventListener('open', () => {
      opened = true;
      useRestFallback = false;
      setConnectionState('live', 'Live');
    });

    socket.addEventListener('message', (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (payload.type === 'connected') {
        setConnectionState('live', 'Live');
        return;
      }
      if (payload.type === 'error') {
        showToast(payload.detail || 'Chat error', 'error');
        return;
      }
      if (payload.type === 'message' && payload.message) {
        appendLiveMessage(payload.message);
      }
    });

    socket.addEventListener('close', () => {
      if (socketConvId !== conversationId) return;
      socket = null;
      if (!opened) {
        useRestFallback = true;
        setConnectionState('fallback', 'REST');
        return;
      }
      setConnectionState('offline', 'Reconnecting…');
      reconnectTimer = setTimeout(() => {
        if (currentConv?.id === conversationId) connectSocket(conversationId);
      }, 1500);
    });

    socket.addEventListener('error', () => {
      // close handler decides fallback vs reconnect
    });
  }

  function appendLiveMessage(message) {
    if (!currentConv || isAiConversation(currentConv) || message.conversation_id !== currentConv.id) return;
    if (seenMessageIds.has(message.id)) return;
    seenMessageIds.add(message.id);
    const placeholder = chatBody.querySelector('.msg-bubble.received');
    if (placeholder && chatBody.children.length <= 2 && (placeholder.textContent || '').includes('start of your conversation')) {
      placeholder.remove();
    }
    chatBody.insertAdjacentHTML('beforeend', renderBubble(message, user.id));
    chatBody.scrollTop = chatBody.scrollHeight;
    const preview = convList.querySelector(`[data-id="${currentConv.id}"] .conv-preview`);
    if (preview) preview.textContent = message.message_text;
    const time = convList.querySelector(`[data-id="${currentConv.id}"] .conv-time`);
    if (time) time.textContent = 'just now';
  }

  function renderBubble(message, myId) {
    const mine = message.sender_id === myId;
    const time = new Date(message.created_at).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
    return `
      <div class="msg-bubble ${mine ? 'sent' : 'received'}" data-message-id="${message.id}">
        ${escapeHtml(message.message_text)}
        <span class="msg-time">${time}</span>
      </div>
    `;
  }

  function renderAttachmentBubble(file, mine) {
    return `
      <div class="msg-attachment ${mine ? 'sent-file' : ''}">
        <span class="file-icon">FILE</span>
        <div style="flex:1; min-width:0;">
          <button type="button" class="attach-link" data-download="${file.id}" data-name="${escapeHtml(file.filename)}" style="padding:0;">
            <span>
              <strong>${escapeHtml(file.filename)}</strong>
              <small>${escapeHtml(formatBytes(file.size))}</small>
            </span>
          </button>
        </div>
      </div>
    `;
  }

  async function sendAiMessage(text) {
    if (aiBusy) return;
    aiBusy = true;
    if (sendBtn) sendBtn.disabled = true;
    setConnectionState('fallback', 'Thinking…');

    aiHistory.push({ role: 'user', content: text });
    saveAiHistory();
    chatBody.insertAdjacentHTML(
      'beforeend',
      `<div class="msg-bubble sent">${escapeHtml(text)}<span class="msg-time">You</span></div>
       <div class="msg-bubble received ai-bubble ai-typing" id="aiTyping">Writing a reply…<span class="msg-time">AI</span></div>`
    );
    chatBody.scrollTop = chatBody.scrollHeight;
    updateAiPreview(text);

    try {
      const history = aiHistory.slice(0, -1).map((turn) => ({
        role: turn.role,
        content: turn.content,
      }));
      const result = await api('/ai/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text, history }),
      });
      document.getElementById('aiTyping')?.remove();
      const reply = (result.reply || '').trim() || 'Sorry — I could not generate a reply.';
      aiHistory.push({ role: 'assistant', content: reply });
      saveAiHistory();
      chatBody.insertAdjacentHTML(
        'beforeend',
        `<div class="msg-bubble received ai-bubble">${escapeHtml(reply)}<span class="msg-time">AI</span></div>`
      );
      chatBody.scrollTop = chatBody.scrollHeight;
      updateAiPreview(reply);
      setConnectionState('live', 'Gemini');
    } catch (err) {
      document.getElementById('aiTyping')?.remove();
      aiHistory.pop();
      saveAiHistory();
      chatBody.insertAdjacentHTML(
        'beforeend',
        `<div class="msg-bubble received">${escapeHtml(err.message || 'AI reply failed.')}<span class="msg-time">Error</span></div>`
      );
      chatBody.scrollTop = chatBody.scrollHeight;
      setConnectionState('offline', 'AI error');
      showToast(err.message || 'AI reply failed.', 'error');
    } finally {
      aiBusy = false;
      if (sendBtn) sendBtn.disabled = false;
    }
  }

  function updateAiPreview(text) {
    const preview = convList.querySelector(`[data-id="${AI_CONV_ID}"] .conv-preview`);
    if (preview) preview.textContent = text;
  }

  async function sendMessage() {
    const text = msgInput.value.trim();
    if (!text || !currentConv) return;
    msgInput.value = '';

    if (isAiConversation(currentConv)) {
      await sendAiMessage(text);
      return;
    }

    const live = socket && socket.readyState === WebSocket.OPEN && !useRestFallback;
    if (live) {
      try {
        socket.send(JSON.stringify({ type: 'send', message_text: text }));
        const preview = convList.querySelector(`[data-id="${currentConv.id}"] .conv-preview`);
        if (preview) preview.textContent = text;
        return;
      } catch {
        useRestFallback = true;
        setConnectionState('fallback', 'REST');
      }
    }

    try {
      const saved = await api('/messages', {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: currentConv.id,
          receiver_id: currentConv.other_user.id,
          message_text: text,
        }),
      });
      appendLiveMessage(saved);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  sendBtn?.addEventListener('click', sendMessage);
  msgInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });
});
