document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth(['client']);
  if (!user) return;
  const contractId = Number(new URLSearchParams(window.location.search).get('contract_id'));
  if (!contractId) {
    showMessage('Open this page from Fund Contract on a pending contract.');
    return;
  }
  document.getElementById('backLink').href = `contract-detail.html?id=${contractId}`;
  startCheckout(contractId, user);
});

function showMessage(text, isError = false) {
  document.getElementById('payBody').innerHTML = `<p style="color:${isError ? '#B23A3A' : 'var(--slate)'};">${escapeHtml(text)}</p>`;
}

async function startCheckout(contractId, user) {
  const body = document.getElementById('payBody');
  body.innerHTML = '<p style="color:var(--slate);">Loading payment…</p>';
  try {
    const contract = await api(`/contracts/${contractId}`);
    if (user.id !== contract.client_id) {
      showMessage('Only the client on this contract can fund it.', true);
      return;
    }
    if (contract.status !== 'pending') {
      showMessage('This contract is not awaiting payment.');
      return;
    }
    const payment = await api(`/payments/create/${contractId}`, { method: 'POST', body: '{}' });
    renderForm(contract, payment, user);
  } catch (err) {
    showMessage(err.message || 'Could not start the payment.', true);
  }
}

function renderForm(contract, payment, user) {
  const amount = formatCurrency(payment.amount, payment.currency);
  const fee = formatCurrency(payment.platform_fee, payment.currency);
  const freelancerAmount = formatCurrency(payment.freelancer_amount, payment.currency);
  const freelancer = contract.freelancer?.name || 'Freelancer';
  const project = contract.project?.title || `Project #${contract.project_id}`;

  document.getElementById('payBody').innerHTML = `
    <h1>Fund escrow</h1>
    <p class="tiny" style="margin-bottom:16px;">Fund the contract now. The freelancer is paid after you approve the work.</p>
    <div class="pay-row"><span>Project</span><strong>${escapeHtml(project)}</strong></div>
    <div class="pay-row"><span>Freelancer</span><strong>${escapeHtml(freelancer)}</strong></div>
    <div class="pay-row"><span>Contract Amount</span><strong>${amount}</strong></div>
    <div class="pay-row"><span>Platform Fee</span><strong>${fee}</strong></div>
    <div class="pay-row"><span>Freelancer Receives</span><strong>${freelancerAmount}</strong></div>
    <div class="method">
      <label><input type="radio" checked disabled> Mock Card</label>
    </div>
    <div class="field">
      <span>Card number</span>
      <input type="text" value="4242 4242 4242 4242" readonly autocomplete="off" aria-label="Demo card number">
    </div>
    <div class="field">
      <span>Cardholder Name</span>
      <input type="text" value="${escapeHtml(user.name || '')}" readonly autocomplete="off">
    </div>
    <div class="field-row">
      <div class="field">
        <span>Expiry</span>
        <input type="text" value="12/30" readonly autocomplete="off">
      </div>
      <div class="field">
        <span>CVV</span>
        <input type="password" value="***" readonly autocomplete="off">
      </div>
    </div>
    <div class="pay-actions">
      <button type="button" class="btn btn-primary" id="confirmPay">Confirm Payment ${amount}</button>
      <button type="button" class="btn btn-outline" id="failPay">Simulate failed payment</button>
    </div>
    <p class="tiny">Card details are used for this checkout session only.</p>
  `;

  document.getElementById('confirmPay').addEventListener('click', () => confirmPayment(payment.id, contract.id));
  document.getElementById('failPay').addEventListener('click', () => failPayment(payment.id, contract.id));
}

function processingView() {
  document.getElementById('payBody').innerHTML = `
    <h1>FreelanceHub Pay</h1>
    <div class="result"><h2>Processing payment...</h2><p style="color:var(--slate);">Please wait while we confirm funding.</p></div>
  `;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function confirmPayment(paymentId, contractId) {
  processingView();
  await wait(700);
  try {
    const payment = await api(`/payments/${paymentId}/confirm`, { method: 'POST', body: '{}' });
    const paidOn = payment.paid_at ? new Date(payment.paid_at).toLocaleString() : 'Just now';
    document.getElementById('payBody').innerHTML = `
      <div class="result">
        <h2 class="ok">✓ Payment Successful</h2>
        <p>Transaction ID:<br><strong>${escapeHtml(payment.transaction_id || '—')}</strong></p>
        <p style="margin-top:10px;">Amount Paid:<br><strong>${formatCurrency(payment.amount, payment.currency)}</strong></p>
        <p style="margin-top:10px;">Contract Status:<br><strong>Funded</strong></p>
        <p class="tiny">${escapeHtml(paidOn)}</p>
        <p style="margin-top:16px;"><a class="btn btn-primary" href="contract-detail.html?id=${contractId}">View Contract</a></p>
      </div>
    `;
  } catch (err) {
    showFailure(err.message || 'Unable to process payment.', contractId, paymentId);
  }
}

async function failPayment(paymentId, contractId) {
  processingView();
  await wait(500);
  try {
    await api(`/payments/${paymentId}/fail`, { method: 'POST', body: '{}' });
    showFailure('Unable to process payment.', contractId, null);
  } catch (err) {
    showFailure(err.message || 'Unable to process payment.', contractId, paymentId);
  }
}

function showFailure(reason, contractId, paymentId) {
  document.getElementById('payBody').innerHTML = `
    <div class="result">
      <h2 class="bad">✕ Payment Failed</h2>
      <p>Reason:<br>${escapeHtml(reason)}</p>
      <p class="tiny">The contract is still awaiting payment. No charge was made.</p>
      <p style="margin-top:16px;"><button type="button" class="btn btn-primary" id="tryAgain">Try Again</button></p>
    </div>
  `;
  document.getElementById('tryAgain').addEventListener('click', () => startCheckout(contractId, Auth.getUser()));
}
