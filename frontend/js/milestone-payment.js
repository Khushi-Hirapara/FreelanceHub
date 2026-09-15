document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth(['client']);
  if (!user) return;
  const milestoneId = Number(new URLSearchParams(window.location.search).get('milestone_id'));
  if (!milestoneId) {
    showMessage('Open this page from Fund Milestone on a pending milestone.');
    return;
  }
  startCheckout(milestoneId, user);
});

function showMessage(text, isError = false) {
  document.getElementById('payBody').innerHTML = `<p style="color:${isError ? '#B23A3A' : 'var(--slate)'};">${escapeHtml(text)}</p>`;
}

async function startCheckout(milestoneId, user) {
  const body = document.getElementById('payBody');
  body.innerHTML = '<p style="color:var(--slate);">Loading payment…</p>';
  try {
    const milestone = await api(`/milestones/${milestoneId}`);
    const contract = await api(`/contracts/${milestone.contract_id}`);
    document.getElementById('backLink').href = `contract-detail.html?id=${contract.id}`;
    if (user.id !== contract.client_id) {
      showMessage('Only the client on this contract can fund this milestone.', true);
      return;
    }
    if (milestone.status === 'cancelled') {
      showMessage('This milestone was cancelled.', true);
      return;
    }
    if (milestone.status !== 'pending') {
      showMessage('This milestone is not awaiting payment.');
      return;
    }
    const payment = await api(`/milestones/${milestoneId}/payment`, { method: 'POST', body: '{}' });
    renderForm(contract, milestone, payment, user);
  } catch (err) {
    showMessage(err.message || 'Could not start the payment.', true);
  }
}

function renderForm(contract, milestone, payment, user) {
  const amount = formatCurrency(payment.amount, payment.currency);
  const fee = formatCurrency(payment.platform_fee, payment.currency);
  const freelancerAmount = formatCurrency(payment.freelancer_amount, payment.currency);
  const project = contract.project?.title || `Project #${contract.project_id}`;

  document.getElementById('payBody').innerHTML = `
    <h1>Fund milestone</h1>
    <p class="tiny" style="margin-bottom:16px;">Fund this milestone into escrow. Release happens after approval.</p>
    <div class="pay-row"><span>Project</span><strong>${escapeHtml(project)}</strong></div>
    <div class="pay-row"><span>Milestone</span><strong>${escapeHtml(milestone.title)}</strong></div>
    <div class="pay-row"><span>Amount</span><strong>${amount}</strong></div>
    <div class="pay-row"><span>Platform fee</span><strong>${fee}</strong></div>
    <div class="pay-row"><span>Freelancer receives</span><strong>${freelancerAmount}</strong></div>
    <div class="method">
      <label><input type="radio" checked disabled> Card</label>
    </div>
    <div class="field">
      <span>Card Number</span>
      <input type="text" value="4242 4242 4242 4242" readonly autocomplete="off" aria-label="Card number">
    </div>
    <div class="field-row">
      <div class="field">
        <span>MM/YY</span>
        <input type="text" value="12/30" readonly autocomplete="off">
      </div>
      <div class="field">
        <span>CVV</span>
        <input type="password" value="***" readonly autocomplete="off">
      </div>
    </div>
    <div class="field">
      <span>Cardholder Name</span>
      <input type="text" value="${escapeHtml(user.name || 'Cardholder')}" readonly autocomplete="off">
    </div>
    <div class="pay-actions">
      <button type="button" class="btn btn-primary" id="confirmPay">Confirm Payment</button>
      <button type="button" class="btn btn-outline" id="failPay">Simulate failed payment</button>
    </div>
    <p class="tiny">Card details are used for this checkout session only.</p>
  `;

  document.getElementById('confirmPay').addEventListener('click', () => confirmPayment(milestone, payment));
  document.getElementById('failPay').addEventListener('click', () => failPayment(milestone));
}

function processingView() {
  document.getElementById('payBody').innerHTML = `
    <h1>FreelanceHub Pay</h1>
    <div class="result"><h2>Processing...</h2><p style="color:var(--slate);">Please wait while we confirm funding.</p></div>
  `;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function confirmPayment(milestone, payment) {
  processingView();
  await wait(700);
  try {
    const confirmed = await api(`/milestones/${milestone.id}/payment/confirm`, { method: 'POST', body: '{}' });
    document.getElementById('payBody').innerHTML = `
      <div class="result">
        <h2 class="ok">✓ Payment Successful</h2>
        <p>Transaction ID:<br><strong>${escapeHtml(confirmed.transaction_id || '—')}</strong></p>
        <p style="margin-top:10px;">Amount:<br><strong>${formatCurrency(confirmed.amount, confirmed.currency)}</strong></p>
        <p style="margin-top:10px;">Milestone:<br><strong>${escapeHtml(milestone.title)}</strong></p>
        <p style="margin-top:10px;">Status:<br><strong>Funded</strong></p>
        <p class="tiny">${new Date().toLocaleString()}</p>
        <p style="margin-top:16px;"><a class="btn btn-primary" href="contract-detail.html?id=${milestone.contract_id}">Back to Contract</a></p>
      </div>
    `;
  } catch (err) {
    showFailure(err.message || 'Unable to process payment.', milestone);
  }
}

async function failPayment(milestone) {
  processingView();
  await wait(500);
  try {
    await api(`/milestones/${milestone.id}/payment/fail`, { method: 'POST', body: '{}' });
    showFailure('Payment Failed', milestone);
  } catch (err) {
    showFailure(err.message || 'Payment Failed', milestone);
  }
}

function showFailure(reason, milestone) {
  document.getElementById('payBody').innerHTML = `
    <div class="result">
      <h2 class="bad">✕ Payment Failed</h2>
      <p>${escapeHtml(reason)}</p>
      <p class="tiny">The milestone is still pending. No charge was made.</p>
      <p style="margin-top:16px;"><button type="button" class="btn btn-primary" id="tryAgain">Try Again</button></p>
    </div>
  `;
  document.getElementById('tryAgain').addEventListener('click', () => startCheckout(milestone.id, Auth.getUser()));
}
