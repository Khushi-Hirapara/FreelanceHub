const adminState = {
  users: { page: 1, q: '', role: '', active: '' },
  projects: { page: 1, q: '', status: '' },
  contracts: { page: 1, q: '', status: '' },
  payments: { page: 1, q: '', status: '' },
  disputes: { page: 1, q: '' },
};

document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth(['admin']);
  if (!user) return;

  document.getElementById('adminAvatar').textContent = initials(user.name);
  document.getElementById('adminName').textContent = user.name;

  bindSectionNav();
  bindSearch('usersQ', 'users', () => loadUsers());
  bindSelect('usersRole', 'users', 'role', () => loadUsers());
  bindSelect('usersActive', 'users', 'active', () => loadUsers());
  bindSearch('projectsQ', 'projects', () => loadProjects());
  bindSelect('projectsStatus', 'projects', 'status', () => loadProjects());
  bindSearch('contractsQ', 'contracts', () => loadContracts());
  bindSelect('contractsStatus', 'contracts', 'status', () => loadContracts());
  bindSearch('paymentsQ', 'payments', () => loadPayments());
  bindSelect('paymentsStatus', 'payments', 'status', () => loadPayments());
  bindSearch('disputesQ', 'disputes', () => loadDisputes());

  loadOverview();
  showSection(location.hash.replace('#', '') || 'overview');
});

function bindSectionNav() {
  document.querySelectorAll('.admin-nav, .admin-tab').forEach((el) => {
    el.addEventListener('click', (event) => {
      event.preventDefault();
      showSection(el.dataset.section);
    });
  });
}

function showSection(section) {
  const name = ['overview', 'users', 'projects', 'contracts', 'payments', 'disputes'].includes(section)
    ? section
    : 'overview';
  document.querySelectorAll('.panel').forEach((panel) => panel.classList.toggle('active', panel.id === `panel-${name}`));
  document.querySelectorAll('.admin-nav, .admin-tab').forEach((el) => {
    el.classList.toggle('active', el.dataset.section === name);
  });
  history.replaceState(null, '', `#${name}`);
  if (name === 'overview') loadOverview();
  if (name === 'users') loadUsers();
  if (name === 'projects') loadProjects();
  if (name === 'contracts') loadContracts();
  if (name === 'payments') loadPayments();
  if (name === 'disputes') loadDisputes();
}

function bindSearch(inputId, key, loader) {
  const input = document.getElementById(inputId);
  let timer = null;
  input?.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      adminState[key].q = input.value.trim();
      adminState[key].page = 1;
      loader();
    }, 250);
  });
}

function bindSelect(selectId, key, field, loader) {
  document.getElementById(selectId)?.addEventListener('change', (event) => {
    adminState[key][field] = event.target.value;
    adminState[key].page = 1;
    loader();
  });
}

async function loadOverview() {
  const box = document.getElementById('overviewStats');
  box.innerHTML = '<div class="card stat-card"><div class="eyebrow">Loading</div><div class="val">…</div></div>';
  try {
    const data = await api('/admin/dashboard');
    const cards = [
      ['Total users', data.total_users, `${data.clients} clients · ${data.freelancers} freelancers`],
      ['Projects', data.projects, 'All briefs on the platform'],
      ['Active contracts', data.active_contracts, `${data.completed_contracts} completed`],
      ['Payment volume', formatMoney(data.total_payment_volume), 'Paid demo payments'],
      ['Platform revenue', formatMoney(data.platform_revenue), 'Fees from paid payments'],
      ['Pending disputes', data.pending_disputes, 'Contracts and milestones'],
    ];
    box.innerHTML = cards
      .map(
        ([label, value, note]) => `
      <div class="card stat-card">
        <div class="eyebrow">${escapeHtml(label)}</div>
        <div class="val">${escapeHtml(String(value))}</div>
        <div class="delta">${escapeHtml(note)}</div>
      </div>`
      )
      .join('');
  } catch (err) {
    box.innerHTML = `<p class="muted" style="color:#B23A3A;">${escapeHtml(err.message)}</p>`;
  }
}

async function loadUsers() {
  const params = new URLSearchParams({
    page: String(adminState.users.page),
    limit: '10',
  });
  if (adminState.users.q) params.set('q', adminState.users.q);
  if (adminState.users.role) params.set('role', adminState.users.role);
  if (adminState.users.active !== '') params.set('is_active', adminState.users.active);
  await renderPage('users', `/admin/users?${params}`, renderUsersTable);
}

function renderUsersTable(items) {
  if (!items.length) return '<p class="muted" style="padding:16px;">No users found.</p>';
  return `
    <table class="admin-table">
      <thead>
        <tr><th>User</th><th>Role</th><th>Status</th><th>Joined</th><th></th></tr>
      </thead>
      <tbody>
        ${items
          .map((user) => {
            const active = user.is_active;
            return `
            <tr>
              <td>
                <strong>${escapeHtml(user.name)}</strong><br>
                <span class="muted">${escapeHtml(user.email)}</span>
              </td>
              <td>${escapeHtml(user.role)}</td>
              <td><span class="status-badge ${active ? 'status-active' : 'status-inactive'}">${active ? 'Active' : 'Inactive'}</span></td>
              <td>${escapeHtml(new Date(user.created_at).toLocaleDateString())}</td>
              <td>
                ${user.role === 'admin'
                  ? '<span class="muted">Protected</span>'
                  : `<button type="button" class="btn btn-outline btn-sm" data-user-status="${user.id}" data-active="${active ? 'false' : 'true'}">${active ? 'Deactivate' : 'Activate'}</button>`}
              </td>
            </tr>`;
          })
          .join('')}
      </tbody>
    </table>`;
}

async function loadProjects() {
  const params = new URLSearchParams({ page: String(adminState.projects.page), limit: '10' });
  if (adminState.projects.q) params.set('q', adminState.projects.q);
  if (adminState.projects.status) params.set('status', adminState.projects.status);
  await renderPage('projects', `/admin/projects?${params}`, (items) => {
    if (!items.length) return '<p class="muted" style="padding:16px;">No projects found.</p>';
    return `
      <table class="admin-table">
        <thead><tr><th>Project</th><th>Client</th><th>Budget</th><th>Status</th><th>Proposals</th></tr></thead>
        <tbody>
          ${items
            .map(
              (project) => `
            <tr>
              <td><strong><a href="project-detail.html?id=${project.id}">${escapeHtml(project.title)}</a></strong><br><span class="muted">${escapeHtml(project.category)}</span></td>
              <td>${escapeHtml(project.client_name || `#${project.client_id}`)}</td>
              <td>${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')}</td>
              <td><span class="status-badge status-${escapeHtml(project.status)}">${escapeHtml(statusLabel(project.status))}</span></td>
              <td>${project.proposal_count}</td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>`;
  });
}

async function loadContracts() {
  const params = new URLSearchParams({ page: String(adminState.contracts.page), limit: '10' });
  if (adminState.contracts.q) params.set('q', adminState.contracts.q);
  if (adminState.contracts.status) params.set('status', adminState.contracts.status);
  await renderPage('contracts', `/admin/contracts?${params}`, (items) => {
    if (!items.length) return '<p class="muted" style="padding:16px;">No contracts found.</p>';
    return `
      <table class="admin-table">
        <thead><tr><th>Contract</th><th>Parties</th><th>Amount</th><th>Status</th></tr></thead>
        <tbody>
          ${items
            .map(
              (contract) => `
            <tr>
              <td><strong><a href="contract-detail.html?id=${contract.id}">${escapeHtml(contract.project_title || `Contract #${contract.id}`)}</a></strong></td>
              <td>${escapeHtml(contract.client_name || 'Client')} → ${escapeHtml(contract.freelancer_name || 'Freelancer')}</td>
              <td>${formatMoney(contract.agreed_amount)}<br><span class="muted">Fee ${formatMoney(contract.platform_fee)}</span></td>
              <td><span class="status-badge status-${escapeHtml(contract.status)}">${escapeHtml(statusLabel(contract.status))}</span></td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>`;
  });
}

async function loadPayments() {
  const params = new URLSearchParams({ page: String(adminState.payments.page), limit: '10' });
  if (adminState.payments.q) params.set('q', adminState.payments.q);
  if (adminState.payments.status) params.set('status', adminState.payments.status);
  await renderPage('payments', `/admin/payments?${params}`, (items) => {
    if (!items.length) return '<p class="muted" style="padding:16px;">No payments found.</p>';
    return `
      <table class="admin-table">
        <thead><tr><th>Payment</th><th>Project</th><th>Amount</th><th>Status</th></tr></thead>
        <tbody>
          ${items
            .map(
              (payment) => `
            <tr>
              <td><strong><a href="payment-detail.html?id=${payment.id}">#${payment.id}</a></strong><br><span class="muted">${escapeHtml(payment.transaction_id || 'No transaction yet')}</span></td>
              <td>${escapeHtml(payment.project_title || `Contract #${payment.contract_id}`)}</td>
              <td>${formatMoney(payment.amount)}<br><span class="muted">Fee ${formatMoney(payment.platform_fee)}</span></td>
              <td><span class="status-badge status-${escapeHtml(payment.status)}">${escapeHtml(statusLabel(payment.status))}</span></td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>`;
  });
}

async function loadDisputes() {
  const params = new URLSearchParams({ page: String(adminState.disputes.page), limit: '10' });
  if (adminState.disputes.q) params.set('q', adminState.disputes.q);
  await renderPage('disputes', `/admin/disputes?${params}`, (items) => {
    if (!items.length) return '<p class="muted" style="padding:16px;">No open disputes.</p>';
    return `
      <table class="admin-table">
        <thead><tr><th>Project</th><th>Reason</th><th>Status</th><th>Contract</th><th>Resolve</th></tr></thead>
        <tbody>
          ${items
            .map(
              (item) => `
            <tr>
              <td><strong>${escapeHtml(item.title)}</strong><div class="muted">${escapeHtml(new Date(item.updated_at || item.created_at).toLocaleString())}</div></td>
              <td>${escapeHtml(item.reason)}<div class="muted">${escapeHtml((item.description || '').slice(0, 120))}</div></td>
              <td><span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(item.status === 'open' ? 'Open' : statusLabel(item.status))}</span></td>
              <td><a href="contract-detail.html?id=${item.contract_id}">Contract #${item.contract_id}</a></td>
              <td>
                <form class="admin-resolve" data-dispute-id="${item.id}">
                  <select name="outcome" required>
                    <option value="resolved">Resolve</option>
                    <option value="rejected">Reject</option>
                  </select>
                  <select name="resolution">
                    <option value="">Resolution</option>
                    <option value="refund_client">Refund client</option>
                    <option value="release_to_freelancer">Release to freelancer</option>
                    <option value="partial_refund">Partial refund</option>
                  </select>
                  <input name="partial_amount" type="number" min="0.01" step="0.01" placeholder="Partial $">
                  <input name="notes" maxlength="400" placeholder="Notes">
                  <button type="submit" class="btn btn-primary btn-sm">Apply</button>
                </form>
              </td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>`;
  });
}

async function renderPage(key, path, renderer) {
  const table = document.getElementById(`${key}Table`);
  const pager = document.getElementById(`${key}Pager`);
  table.innerHTML = '<p class="muted" style="padding:16px;">Loading…</p>';
  pager.innerHTML = '';
  try {
    const data = await api(path);
    table.innerHTML = renderer(data.items || []);
    if (key === 'users') {
      table.querySelectorAll('[data-user-status]').forEach((button) => {
        button.addEventListener('click', () => toggleUser(Number(button.dataset.userStatus), button.dataset.active === 'true'));
      });
    }
    if (key === 'disputes') {
      table.querySelectorAll('[data-dispute-id]').forEach((form) => {
        form.addEventListener('submit', (event) => resolveAdminDispute(event));
      });
    }
    renderPager(pager, key, data);
  } catch (err) {
    table.innerHTML = `<p class="muted" style="padding:16px;color:#B23A3A;">${escapeHtml(err.message)}</p>`;
  }
}

function renderPager(container, key, data) {
  const page = Number(data.page || 1);
  const pages = Number(data.pages || 0);
  const total = Number(data.total || 0);
  if (pages <= 1) {
    container.innerHTML = total ? `<span class="muted">${total} result${total === 1 ? '' : 's'}</span>` : '';
    return;
  }
  container.innerHTML = `
    <button type="button" class="btn btn-outline btn-sm" data-prev ${page <= 1 ? 'disabled' : ''}>Previous</button>
    <span class="muted">Page ${page} of ${pages} · ${total}</span>
    <button type="button" class="btn btn-outline btn-sm" data-next ${page >= pages ? 'disabled' : ''}>Next</button>
  `;
  container.querySelector('[data-prev]')?.addEventListener('click', () => {
    adminState[key].page = Math.max(1, page - 1);
    reload(key);
  });
  container.querySelector('[data-next]')?.addEventListener('click', () => {
    adminState[key].page = Math.min(pages, page + 1);
    reload(key);
  });
}

function reload(key) {
  if (key === 'users') return loadUsers();
  if (key === 'projects') return loadProjects();
  if (key === 'contracts') return loadContracts();
  if (key === 'payments') return loadPayments();
  if (key === 'disputes') return loadDisputes();
}

async function toggleUser(userId, nextActive) {
  try {
    await api(`/admin/users/${userId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: nextActive }),
    });
    showToast(nextActive ? 'User activated.' : 'User deactivated.');
    loadUsers();
    loadOverview();
  } catch (err) {
    showToast(err.message || 'Could not update user.', 'error');
  }
}

async function resolveAdminDispute(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const disputeId = form.dataset.disputeId;
  const payload = {
    outcome: form.outcome.value,
    notes: form.notes.value.trim() || null,
  };
  if (payload.outcome === 'resolved') {
    payload.resolution = form.resolution.value || null;
    if (form.partial_amount.value) {
      payload.partial_amount = Number(form.partial_amount.value);
    }
  }
  try {
    await api(`/admin/disputes/${disputeId}/resolve`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    showToast('Dispute resolved.');
    loadDisputes();
    loadOverview();
  } catch (err) {
    showToast(err.message || 'Could not resolve dispute.', 'error');
  }
}
