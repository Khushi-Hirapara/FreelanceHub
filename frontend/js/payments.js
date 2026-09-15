document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;

  const isFreelancer = user.role === 'freelancer';
  if (isFreelancer) {
    const title = document.getElementById('pageTitle');
    const sub = document.getElementById('pageSub');
    if (title) title.textContent = 'Earnings';
    if (sub) {
      sub.textContent =
        'Payments held in escrow until the client approves your work.';
    }
    setText('stat1Label', 'Awaiting');
    setText('stat2Label', 'Paid to you');
    setText('stat3Label', 'Gross volume');
  } else {
    setText('stat1Label', 'Awaiting fund');
    setText('stat2Label', 'In escrow / paid');
    setText('stat3Label', 'Total spent');
  }

  let allPayments = [];
  let activeFilter = 'all';

  document.querySelectorAll('#paymentFilters [data-filter]').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#paymentFilters [data-filter]').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter || 'all';
      renderList(user);
    });
  });

  loadPayments(user);

  async function loadPayments(currentUser) {
    const list = document.getElementById('paymentList');
    list.innerHTML = '<p style="color:var(--slate);padding:12px;">Loading payments…</p>';
    try {
      allPayments = await api('/payments/mine');
      renderStats(allPayments);
      renderList(currentUser);
    } catch (err) {
      list.innerHTML = `<p style="color:#B23A3A;padding:12px;">${escapeHtml(err.message || 'Could not load payments.')}</p>`;
    }
  }

  function renderStats(payments) {
    const pending = payments.filter((p) => p.status === 'pending' || p.status === 'processing');
    const paid = payments.filter((p) => p.status === 'paid');
    const pendingSum = pending.reduce((sum, p) => sum + Number(p.amount || 0), 0);
    const paidSum = paid.reduce((sum, p) => sum + Number(isFreelancer ? p.freelancer_amount || p.amount : p.amount || 0), 0);
    const totalSum = payments.reduce((sum, p) => sum + Number(p.amount || 0), 0);
    setText('statPending', formatMoney(pendingSum));
    setText('statPaid', formatMoney(paidSum));
    setText('statTotal', formatMoney(totalSum));
  }

  function matchesFilter(item) {
    if (activeFilter === 'all') return true;
    if (activeFilter === 'pending') return item.status === 'pending' || item.status === 'processing';
    if (activeFilter === 'paid') return item.status === 'paid';
    if (activeFilter === 'failed') return item.status === 'failed' || item.status === 'cancelled' || item.status === 'refunded';
    return true;
  }

  function renderList(currentUser) {
    const list = document.getElementById('paymentList');
    const filtered = allPayments.filter(matchesFilter);

    if (!allPayments.length) {
      list.innerHTML = `
        <div class="empty-box">
          <h3>No payments yet</h3>
          <p>${
            isFreelancer
              ? 'When a client funds your contract (or a milestone), the payment appears here while work is in progress.'
              : 'Open a pending contract and click Fund to create an escrow payment.'
          }</p>
          <a class="btn btn-primary" href="contracts.html">Go to Contracts</a>
        </div>
      `;
      return;
    }

    if (!filtered.length) {
      list.innerHTML = '<p style="color:var(--slate);padding:12px;">No payments in this filter.</p>';
      return;
    }

    list.innerHTML = `<div class="pay-list">${filtered.map((p) => renderCard(p, currentUser)).join('')}</div>`;
    list.querySelectorAll('[data-payment-id]').forEach((card) => {
      card.addEventListener('click', () => {
        window.location.href = `payment-detail.html?id=${card.dataset.paymentId}`;
      });
    });
  }
});

function renderCard(payment, user) {
  const title = payment.project?.title || payment.project_title || `Contract #${payment.contract_id}`;
  const isFreelancer = user.role === 'freelancer' || user.id === payment.freelancer_id;
  const amount = isFreelancer
    ? formatCurrency(payment.freelancer_amount ?? payment.amount, payment.currency)
    : formatCurrency(payment.amount, payment.currency);
  const when = payment.paid_at
    ? `Paid ${new Date(payment.paid_at).toLocaleDateString()}`
    : payment.created_at
      ? `Created ${new Date(payment.created_at).toLocaleDateString()}`
      : '';
  const party = isFreelancer
    ? `From ${payment.client?.name || 'Client'}`
    : `To ${payment.freelancer?.name || 'Freelancer'}`;
  const next =
    payment.status === 'pending' || payment.status === 'processing'
      ? user.id === payment.client_id
        ? 'Confirm funding on the checkout page or contract.'
        : 'Waiting for client to complete funding.'
      : payment.status === 'paid'
        ? payment.released_at
          ? 'Released to freelancer.'
          : 'Held in escrow / marked paid — release after approval on the contract.'
        : statusLabel(payment.status);

  return `
    <article class="pay-card" data-payment-id="${payment.id}">
      <div class="pay-card-top">
        <h3>${escapeHtml(title)}</h3>
        <span class="status-pill status-${escapeHtml(payment.status)}">${escapeHtml(statusLabel(payment.status))}</span>
      </div>
      <p class="meta">${escapeHtml(party)}${payment.milestone_id ? ' · Milestone payment' : ' · Contract funding'}</p>
      <div class="pay-amount">${amount}</div>
      <div class="pay-card-foot">
        <span>${escapeHtml(when)}</span>
        <span>${escapeHtml(next)}</span>
      </div>
    </article>
  `;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}
