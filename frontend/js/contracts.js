document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;

  if (user.role === 'freelancer') {
    const title = document.getElementById('pageTitle');
    const sub = document.getElementById('pageSub');
    if (title) title.textContent = 'My contracts';
    if (sub) {
      sub.textContent =
        'Track funded work, submit milestones, and wait for client approval before payout.';
    }
  } else if (user.role === 'client' || user.role === 'admin') {
    const sub = document.getElementById('pageSub');
    if (sub) {
      sub.textContent =
        'Fund contracts into escrow, approve deliveries, then release payment.';
    }
  }

  let allContracts = [];
  let activeFilter = 'all';

  document.querySelectorAll('#contractFilters [data-filter]').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#contractFilters [data-filter]').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter || 'all';
      renderList(user);
    });
  });

  loadContracts(user);

  async function loadContracts(currentUser) {
    const list = document.getElementById('contractList');
    list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">Loading contracts…</p>';
    try {
      allContracts = await api('/contracts/mine');
      renderList(currentUser);
    } catch (err) {
      list.innerHTML = `<p style="color:#B23A3A;padding:12px 0;">${escapeHtml(err.message || 'Could not load contracts.')}</p>`;
    }
  }

  function matchesFilter(item) {
    const status = item.status;
    if (activeFilter === 'all') return true;
    if (activeFilter === 'needs_action') {
      return (
        status === 'pending' ||
        status === 'submitted' ||
        status === 'approved' ||
        status === 'disputed'
      );
    }
    if (activeFilter === 'active') {
      return ['funded', 'in_progress', 'submitted', 'approved'].includes(status);
    }
    if (activeFilter === 'done') {
      return status === 'completed' || status === 'cancelled';
    }
    return true;
  }

  function renderList(currentUser) {
    const list = document.getElementById('contractList');
    const filtered = allContracts.filter(matchesFilter);

    if (!allContracts.length) {
      const isClient = currentUser.role === 'client' || currentUser.role === 'admin';
      list.innerHTML = `
        <div class="empty-box">
          <h3>No contracts yet</h3>
          <p>${
            isClient
              ? 'Accept a freelancer proposal on one of your projects. That creates the contract, then you fund it.'
              : 'When a client accepts your proposal, a contract appears here for funding and delivery.'
          }</p>
          <a class="btn btn-primary" href="${
            isClient ? 'client-dashboard.html' : 'freelancer-dashboard.html'
          }">${isClient ? 'Go to My Projects' : 'Find Work'}</a>
        </div>
      `;
      return;
    }

    if (!filtered.length) {
      list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">No contracts in this filter.</p>';
      return;
    }

    list.innerHTML = filtered.map((item) => renderContract(item, currentUser)).join('');
  }
});

function nextStepCopy(item, user) {
  const isClient = user.id === item.client_id || (user.role === 'client' && user.id === item.client_id);
  const isFreelancer = user.id === item.freelancer_id;
  switch (item.status) {
    case 'pending':
      return isClient
        ? { text: 'Next: Fund this contract into escrow so work can start.', cta: 'Fund now', href: `payment.html?contract_id=${item.id}` }
        : { text: 'Next: Waiting for the client to fund escrow.', cta: 'View contract', href: `contract-detail.html?id=${item.id}` };
    case 'funded':
      return isFreelancer
        ? { text: 'Next: Start work / milestones — funding is held in escrow.', cta: 'Open contract', href: `contract-detail.html?id=${item.id}` }
        : { text: 'Next: Freelancer can begin. Track milestones on the contract.', cta: 'Open contract', href: `contract-detail.html?id=${item.id}` };
    case 'in_progress':
      return isFreelancer
        ? { text: 'Next: Submit work when a milestone is ready for review.', cta: 'Submit / track', href: `contract-detail.html?id=${item.id}` }
        : { text: 'Next: Review progress and approve submitted milestones.', cta: 'Review work', href: `contract-detail.html?id=${item.id}` };
    case 'submitted':
      return isClient
        ? { text: 'Next: Review the delivery and approve or request changes.', cta: 'Review delivery', href: `contract-detail.html?id=${item.id}` }
        : { text: 'Next: Waiting for client approval of your submission.', cta: 'View status', href: `contract-detail.html?id=${item.id}` };
    case 'approved':
      return isClient
        ? { text: 'Next: Release payment / complete the contract.', cta: 'Complete', href: `contract-detail.html?id=${item.id}` }
        : { text: 'Next: Client can release payment after approval.', cta: 'View contract', href: `contract-detail.html?id=${item.id}` };
    case 'completed':
      return { text: 'Contract completed. Leave a review if you haven’t yet.', cta: 'Open', href: `contract-detail.html?id=${item.id}` };
    case 'disputed':
      return { text: 'Dispute open — follow updates on the contract page.', cta: 'View dispute', href: `contract-detail.html?id=${item.id}` };
    case 'cancelled':
      return { text: 'This contract was cancelled.', cta: 'Details', href: `contract-detail.html?id=${item.id}` };
    default:
      return { text: 'Open the contract for the current next step.', cta: 'Open', href: `contract-detail.html?id=${item.id}` };
  }
}

function renderContract(item, user) {
  const title = item.project?.title || `Project #${item.project_id}`;
  const other =
    user.role === 'freelancer' || user.id === item.freelancer_id
      ? item.client?.name || 'Client'
      : item.freelancer?.name || 'Freelancer';
  const otherLabel =
    user.role === 'freelancer' || user.id === item.freelancer_id ? 'Client' : 'Freelancer';
  const start = item.start_date ? new Date(item.start_date).toLocaleDateString() : 'Not started';
  const end = item.end_date ? new Date(item.end_date).toLocaleDateString() : 'Open';
  const next = nextStepCopy(item, user);
  const primaryIsFund = item.status === 'pending' && (user.id === item.client_id || user.role === 'admin');

  return `
    <article class="card contract-item">
      <div class="contract-top">
        <h3>${escapeHtml(title)}</h3>
        <span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
      </div>
      <p class="contract-meta">${otherLabel}: ${escapeHtml(other)} · ${escapeHtml(item.currency || 'USD')}</p>
      <p class="contract-meta">Agreed ${formatMoney(item.agreed_amount)} · Fee ${formatMoney(item.platform_fee)} · Freelancer ${formatMoney(item.freelancer_amount)}</p>
      <div class="next-step"><strong>Next step:</strong> ${escapeHtml(next.text)}</div>
      <div class="contract-foot">
        <span class="muted">Start ${escapeHtml(start)} · End ${escapeHtml(end)}</span>
        <div class="contract-ctas">
          <a class="btn btn-outline btn-sm" href="project-detail.html?id=${item.project_id}">Project</a>
          <a class="btn ${primaryIsFund ? 'btn-primary' : 'btn-outline'} btn-sm" href="${next.href}">${escapeHtml(next.cta)}</a>
        </div>
      </div>
    </article>
  `;
}
