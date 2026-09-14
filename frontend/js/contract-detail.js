document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;
  const id = Number(new URLSearchParams(window.location.search).get('id'));
  if (!id) {
    document.getElementById('contractBody').innerHTML = '<p>Contract not found. Open one from your contracts list.</p>';
    return;
  }
  loadContract(id, user);
});

async function loadContract(id, user) {
  const body = document.getElementById('contractBody');
  body.innerHTML = '<p class="muted">Loading contract…</p>';
  try {
    const contract = await api(`/contracts/${id}`);
    renderContract(contract, user);
  } catch (err) {
    body.innerHTML = `<p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load contract.')}</p>`;
  }
}

function renderContract(contract, user) {
  const body = document.getElementById('contractBody');
  const title = contract.project?.title || `Project #${contract.project_id}`;
  document.title = `${title} contract — FreelanceHub`;
  const start = contract.start_date ? new Date(contract.start_date).toLocaleDateString() : 'Not started';
  const end = contract.end_date ? new Date(contract.end_date).toLocaleDateString() : 'Open';
  const created = contract.created_at ? new Date(contract.created_at).toLocaleString() : '—';
  const actions = actionButtons(contract, user);

  body.innerHTML = `
    <span class="status-badge status-${escapeHtml(contract.status)}">${escapeHtml(statusLabel(contract.status))}</span>
    <h1>${escapeHtml(title)}</h1>
    <p class="muted">${escapeHtml(contract.project?.category || 'Project')} · ${escapeHtml(contract.currency || 'USD')}</p>
    <p style="margin-top:8px;"><a href="project-detail.html?id=${contract.project_id}">View project</a></p>

    <h2>People</h2>
    <div class="people">
      <div>
        <span class="muted">Client</span>
        <strong style="display:block;">${escapeHtml(contract.client?.name || 'Client')}</strong>
        <span class="muted">${escapeHtml(contract.client?.title || contract.client?.location || '')}</span>
      </div>
      <div>
        <span class="muted">Freelancer</span>
        <strong style="display:block;">${escapeHtml(contract.freelancer?.name || 'Freelancer')}</strong>
        <span class="muted">${escapeHtml(contract.freelancer?.title || contract.freelancer?.location || '')}</span>
      </div>
    </div>

    <h2>Amounts</h2>
    <div class="money-grid">
      <div><span>Agreed amount</span><strong>${formatMoney(contract.agreed_amount)}</strong></div>
      <div><span>Platform fee</span><strong>${formatMoney(contract.platform_fee)}</strong></div>
      <div><span>Freelancer amount</span><strong>${formatMoney(contract.freelancer_amount)}</strong></div>
    </div>

    <h2>Dates</h2>
    <p class="muted">Created ${escapeHtml(created)} · Start ${escapeHtml(start)} · End ${escapeHtml(end)}</p>
    <p class="muted" style="margin-top:8px;">Status changes are checked on the server. Payment is not connected, so this page has no pay button.</p>
    <div class="actions" id="contractActions">${actions || '<span class="muted">No actions for this status.</span>'}</div>
  `;

  body.querySelectorAll('[data-status]').forEach((btn) => {
    btn.addEventListener('click', () => updateStatus(contract.id, btn.dataset.status, user, btn));
  });
}

function actionButtons(contract, user) {
  const status = contract.status;
  const isClient = user.id === contract.client_id;
  const isFreelancer = user.id === contract.freelancer_id;
  const isAdmin = user.role === 'admin';
  const buttons = [];

  if (isAdmin && status === 'pending') {
    buttons.push(['funded', 'Mark funded (no charge)', 'btn-outline']);
  }
  if ((isClient || isAdmin) && (status === 'pending' || status === 'funded' || status === 'in_progress')) {
    buttons.push(['cancelled', 'Cancel contract', 'btn-outline']);
  }
  if ((isFreelancer || isAdmin) && status === 'funded') {
    buttons.push(['in_progress', 'Start work', 'btn-primary']);
  }
  if ((isFreelancer || isAdmin) && status === 'in_progress') {
    buttons.push(['submitted', 'Submit work', 'btn-primary']);
  }
  if ((isClient || isAdmin) && status === 'submitted') {
    buttons.push(['approved', 'Approve work', 'btn-primary']);
  }
  if ((isClient || isAdmin) && status === 'approved') {
    buttons.push(['completed', 'Mark completed', 'btn-primary']);
  }
  if ((isClient || isFreelancer || isAdmin) && (status === 'in_progress' || status === 'submitted')) {
    buttons.push(['disputed', 'Open dispute', 'btn-outline']);
  }
  if (isAdmin && status === 'disputed') {
    buttons.push(['in_progress', 'Return to in progress', 'btn-outline']);
    buttons.push(['cancelled', 'Cancel contract', 'btn-outline']);
  }

  return buttons.map(([next, label, cls]) => (
    `<button type="button" class="btn ${cls}" data-status="${next}">${label}</button>`
  )).join('');
}

async function updateStatus(id, next, user, button) {
  button.disabled = true;
  try {
    const contract = await api(`/contracts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: next }),
    });
    showToast('Contract updated.');
    renderContract(contract, user);
  } catch (err) {
    button.disabled = false;
    showToast(err.message || 'Could not update contract.', 'error');
  }
}
