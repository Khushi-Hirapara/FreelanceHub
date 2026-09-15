document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;
  const id = Number(new URLSearchParams(window.location.search).get('id'));
  if (!id) {
    document.getElementById('paymentBody').innerHTML = '<p>Payment not found.</p>';
    return;
  }
  loadPayment(id);
});

async function loadPayment(id) {
  const body = document.getElementById('paymentBody');
  body.innerHTML = '<p style="color:var(--slate);">Loading payment…</p>';
  try {
    const payment = await api(`/payments/${id}`);
    renderPayment(payment);
  } catch (err) {
    body.innerHTML = `<p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load payment.')}</p>`;
  }
}

function methodLabel(method) {
  if (method === 'mock_card') return 'Mock Card';
  return method || '—';
}

function renderPayment(payment) {
  const paidOn = payment.paid_at ? new Date(payment.paid_at).toLocaleString() : 'Not paid yet';
  const released = payment.released_at ? new Date(payment.released_at).toLocaleString() : null;
  const title = payment.project?.title || `Contract #${payment.contract_id}`;
  document.title = `${title} payment — FreelanceHub`;
  document.getElementById('paymentBody').innerHTML = `
    <span class="status-pill status-${escapeHtml(payment.status)}">${escapeHtml(statusLabel(payment.status))}</span>
    <h1>${escapeHtml(title)}</h1>
    <div class="row"><span>Transaction ID</span><strong>${escapeHtml(payment.transaction_id || '—')}</strong></div>
    <div class="row"><span>Type</span><strong>${payment.milestone_id ? 'Milestone payment' : 'Contract funding'}</strong></div>
    <div class="row"><span>Project</span><strong>${payment.project ? `<a href="project-detail.html?id=${payment.project.id}">${escapeHtml(payment.project.title)}</a>` : '—'}</strong></div>
    <div class="row"><span>Contract</span><strong><a href="contract-detail.html?id=${payment.contract_id}">View contract</a></strong></div>
    <div class="row"><span>Client</span><strong>${escapeHtml(payment.client?.name || 'Client')}</strong></div>
    <div class="row"><span>Freelancer</span><strong>${escapeHtml(payment.freelancer?.name || 'Freelancer')}</strong></div>
    <div class="row"><span>Amount funded</span><strong>${formatCurrency(payment.amount, payment.currency)}</strong></div>
    <div class="row"><span>Platform fee</span><strong>${formatCurrency(payment.platform_fee, payment.currency)}</strong></div>
    <div class="row"><span>Freelancer amount</span><strong>${formatCurrency(payment.freelancer_amount, payment.currency)}</strong></div>
    <div class="row"><span>Payment method</span><strong>${escapeHtml(methodLabel(payment.payment_method))}</strong></div>
    <div class="row"><span>Funded on</span><strong>${escapeHtml(paidOn)}</strong></div>
    <div class="row"><span>Released on</span><strong>${escapeHtml(released || 'Not released yet')}</strong></div>
  `;
}
