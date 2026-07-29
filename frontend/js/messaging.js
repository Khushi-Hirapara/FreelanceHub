// ============================================
// messaging.js — conversations & messages via API
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;

  const convList = document.getElementById('convList');
  const chatName = document.getElementById('chatName');
  const chatBody = document.getElementById('chatBody');
  const msgInput = document.getElementById('msgInput');
  const sendBtn = document.getElementById('sendBtn');
  const chatHeaderSub = document.querySelector('.chat-header-info span');
  const chatAvatar = document.querySelector('.chat-header .conv-avatar');

  let currentConv = null;

  loadConversations();

  async function loadConversations() {
    convList.innerHTML = '<p style="padding:16px;color:var(--slate);font-size:0.9rem;">Loading…</p>';
    try {
      const conversations = await api('/conversations');
      if (!conversations.length) {
        convList.innerHTML =
          '<p style="padding:16px;color:var(--slate);font-size:0.9rem;">No conversations yet. Message someone from a project.</p>';
        chatBody.innerHTML =
          '<div class="day-divider">Start a conversation from a proposal or project</div>';
        return;
      }
      convList.innerHTML = conversations.map(renderConvItem).join('');
      bindConvClicks();
      const first = conversations[0];
      await openConversation(first);
      convList.querySelector(`[data-id="${first.id}"]`)?.classList.add('active');
    } catch (err) {
      convList.innerHTML = `<p style="padding:16px;color:#B23A3A;font-size:0.9rem;">${escapeHtml(err.message)}</p>`;
    }
  }

  function renderConvItem(conv) {
    const name = conv.other_user?.name || 'User';
    return `
      <div class="conv-item" data-id="${conv.id}" data-receiver="${conv.other_user.id}" data-name="${escapeHtml(name)}" data-tag="${escapeHtml(conv.project_tag || '')}">
        <div class="conv-avatar">${initials(name)}</div>
        <div class="conv-info">
          <div class="conv-top-row"><h4>${escapeHtml(name)}</h4><span class="conv-time">${timeAgo(conv.updated_at)}</span></div>
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
        await openConversation({
          id: Number(item.dataset.id),
          other_user: { id: Number(item.dataset.receiver), name: item.dataset.name },
          project_tag: item.dataset.tag,
        });
      });
    });
  }

  async function openConversation(conv) {
    currentConv = conv;
    chatName.textContent = conv.other_user?.name || 'Chat';
    if (chatHeaderSub) chatHeaderSub.textContent = conv.project_tag ? `Re: ${conv.project_tag}` : 'Direct message';
    if (chatAvatar) chatAvatar.textContent = initials(conv.other_user?.name);

    chatBody.innerHTML = '<div class="day-divider">Loading…</div>';
    try {
      const messages = await api(`/conversations/${conv.id}/messages`);
      if (!messages.length) {
        chatBody.innerHTML = `
          <div class="day-divider">Today</div>
          <div class="msg-bubble received">
            This is the start of your conversation with ${escapeHtml(conv.other_user?.name || 'them')}.
            <span class="msg-time">Just now</span>
          </div>
        `;
        return;
      }
      chatBody.innerHTML =
        '<div class="day-divider">Conversation</div>' +
        messages.map((m) => renderBubble(m, user.id)).join('');
      chatBody.scrollTop = chatBody.scrollHeight;
    } catch (err) {
      chatBody.innerHTML = `<div class="msg-bubble received">${escapeHtml(err.message)}</div>`;
    }
  }

  function renderBubble(message, myId) {
    const mine = message.sender_id === myId;
    const time = new Date(message.created_at).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
    return `
      <div class="msg-bubble ${mine ? 'sent' : 'received'}">
        ${escapeHtml(message.message_text)}
        <span class="msg-time">${time}</span>
      </div>
    `;
  }

  async function sendMessage() {
    const text = msgInput.value.trim();
    if (!text || !currentConv) return;

    msgInput.value = '';
    try {
      const saved = await api('/messages', {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: currentConv.id,
          receiver_id: currentConv.other_user.id,
          message_text: text,
        }),
      });
      chatBody.insertAdjacentHTML('beforeend', renderBubble(saved, user.id));
      chatBody.scrollTop = chatBody.scrollHeight;

      const preview = convList.querySelector(`[data-id="${currentConv.id}"] .conv-preview`);
      if (preview) preview.textContent = text;
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  sendBtn?.addEventListener('click', sendMessage);
  msgInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });
});
