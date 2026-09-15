// ============================================
// attachments.js — shared secure file helpers
// ============================================

async function uploadAttachment(file, parents) {
  const form = new FormData();
  form.append('file', file);
  Object.entries(parents || {}).forEach(([key, value]) => {
    if (value != null && value !== '') form.append(key, String(value));
  });
  return apiUpload('/attachments', form);
}

async function listAttachments(parents) {
  const params = new URLSearchParams();
  Object.entries(parents || {}).forEach(([key, value]) => {
    if (value != null && value !== '') params.set(key, String(value));
  });
  return api(`/attachments?${params.toString()}`);
}

function renderAttachmentList(items, { canDelete = false, empty = 'No files yet.' } = {}) {
  if (!items?.length) {
    return `<p class="attach-empty">${escapeHtml(empty)}</p>`;
  }
  return `
    <ul class="attach-list">
      ${items.map((item) => `
        <li class="attach-item">
          <button type="button" class="attach-link" data-download="${item.id}" data-name="${escapeHtml(item.filename)}">
            <span class="attach-icon">FILE</span>
            <span>
              <strong>${escapeHtml(item.filename)}</strong>
              <small>${escapeHtml(formatBytes(item.size))}${item.uploader_name ? ` · ${escapeHtml(item.uploader_name)}` : ''}</small>
            </span>
          </button>
          ${canDelete ? `<button type="button" class="btn btn-ghost btn-sm" data-delete-attach="${item.id}">Delete</button>` : ''}
        </li>
      `).join('')}
    </ul>
  `;
}

function bindAttachmentActions(root, { onDeleted } = {}) {
  root?.querySelectorAll('[data-download]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await downloadAttachment(Number(button.dataset.download), button.dataset.name);
      } catch (err) {
        showToast(err.message || 'Download failed.', 'error');
      }
    });
  });
  root?.querySelectorAll('[data-delete-attach]').forEach((button) => {
    button.addEventListener('click', async () => {
      if (!window.confirm('Delete this file?')) return;
      try {
        await api(`/attachments/${button.dataset.deleteAttach}`, { method: 'DELETE' });
        showToast('File deleted.');
        if (onDeleted) await onDeleted();
      } catch (err) {
        showToast(err.message || 'Could not delete file.', 'error');
      }
    });
  });
}

async function mountAttachmentPanel(container, parents, options = {}) {
  if (!container) return;
  const {
    title = 'Files',
    canUpload = false,
    canDelete = false,
    empty = 'No files yet.',
    inputId = `attach-${Math.random().toString(36).slice(2, 8)}`,
  } = options;

  container.innerHTML = `
    <div class="attach-panel">
      <div class="attach-head">
        <strong>${escapeHtml(title)}</strong>
        ${canUpload ? `<label class="btn btn-outline btn-sm" for="${inputId}">Upload file<input type="file" id="${inputId}" hidden></label>` : ''}
      </div>
      <div class="attach-body"><p class="attach-empty">Loading files…</p></div>
    </div>
  `;

  async function refresh() {
    const body = container.querySelector('.attach-body');
    try {
      const items = await listAttachments(parents);
      body.innerHTML = renderAttachmentList(items, {
        canDelete,
        empty,
      });
      bindAttachmentActions(body, { onDeleted: refresh });
    } catch (err) {
      body.innerHTML = `<p class="attach-empty" style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load files.')}</p>`;
    }
  }

  const input = container.querySelector(`#${inputId}`);
  input?.addEventListener('change', async () => {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    try {
      await uploadAttachment(file, parents);
      showToast('File uploaded.');
      await refresh();
    } catch (err) {
      showToast(err.message || 'Upload failed.', 'error');
    }
  });

  await refresh();
}
