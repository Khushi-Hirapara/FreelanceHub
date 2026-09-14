document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;

  document.getElementById('sideAvatar').textContent = initials(user.name);
  document.getElementById('sideName').textContent = user.name;
  document.getElementById('sideRole').textContent = user.role;

  const nav = document.getElementById('sideNav');
  const links = user.role === 'freelancer'
    ? [
        ['freelancer-dashboard.html', 'Find Work'],
        ['my-proposals.html', 'My Proposals'],
        ['contracts.html', 'Contracts'],
        ['messaging.html', 'Messages'],
        ['profile.html', 'Profile'],
      ]
    : [
        ['client-dashboard.html', 'My Projects'],
        ['project-posting.html', 'Post a Project'],
        ['contracts.html', 'Contracts'],
        ['messaging.html', 'Messages'],
        ['profile.html', 'Profile'],
      ];
  nav.innerHTML = links.map(([href, label]) => (
    `<a href="${href}" class="${href === 'contracts.html' ? 'active' : ''}"><span class="icon">#</span> ${label}</a>`
  )).join('');

  loadContracts(user);
});

async function loadContracts(user) {
  const list = document.getElementById('contractList');
  list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">Loading contracts…</p>';
  try {
    const contracts = await api('/contracts/mine');
    if (!contracts.length) {
      list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">No contracts yet. A contract is created when a client accepts a proposal.</p>';
      return;
    }
    list.innerHTML = contracts.map((item) => renderContract(item, user)).join('');
  } catch (err) {
    list.innerHTML = `<p style="color:#B23A3A;padding:12px 0;">${escapeHtml(err.message || 'Could not load contracts.')}</p>`;
  }
}

function renderContract(item, user) {
  const title = item.project?.title || `Project #${item.project_id}`;
  const other = user.role === 'freelancer'
    ? (item.client?.name || 'Client')
    : (item.freelancer?.name || 'Freelancer');
  const otherLabel = user.role === 'freelancer' ? 'Client' : 'Freelancer';
  const start = item.start_date ? new Date(item.start_date).toLocaleDateString() : 'Not started';
  const end = item.end_date ? new Date(item.end_date).toLocaleDateString() : 'Open';
  return `
    <article class="card contract-item">
      <div class="contract-top">
        <h3>${escapeHtml(title)}</h3>
        <span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
      </div>
      <p class="contract-meta">${otherLabel}: ${escapeHtml(other)} · ${escapeHtml(item.currency || 'USD')}</p>
      <p class="contract-meta">Agreed ${formatMoney(item.agreed_amount)} · Platform fee ${formatMoney(item.platform_fee)} · Freelancer ${formatMoney(item.freelancer_amount)}</p>
      <div class="contract-foot">
        <span>Start ${escapeHtml(start)} · End ${escapeHtml(end)}</span>
        <span>
          <a href="project-detail.html?id=${item.project_id}">Project</a>
          ·
          <a href="contract-detail.html?id=${item.id}">Contract details</a>
        </span>
      </div>
    </article>
  `;
}
