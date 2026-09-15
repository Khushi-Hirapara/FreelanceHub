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
    let payments = [];
    try {
      payments = await api('/payments/mine');
    } catch (err) {
      payments = [];
    }
    renderContract(contract, user, payments.filter((item) => item.contract_id === contract.id));
  } catch (err) {
    body.innerHTML = `<p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load contract.')}</p>`;
  }
}

function renderContract(contract, user, payments = []) {
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

    <div class="journey" aria-label="Contract progress">
      ${journeySteps(contract.status)}
    </div>

    <h2>People</h2>
    <div class="people">
      <div>
        <span class="muted">Client</span>
        <strong style="display:block;"><a href="freelancer-profile.html?id=${contract.client_id}">${escapeHtml(contract.client?.name || 'Client')}</a></strong>
        <span class="muted">${escapeHtml(contract.client?.title || contract.client?.location || '')}</span>
      </div>
      <div>
        <span class="muted">Freelancer</span>
        <strong style="display:block;"><a href="freelancer-profile.html?id=${contract.freelancer_id}">${escapeHtml(contract.freelancer?.name || 'Freelancer')}</a></strong>
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
    <div class="dates-grid">
      <div><span>Created</span><strong>${escapeHtml(created)}</strong></div>
      <div><span>Start</span><strong>${escapeHtml(start)}</strong></div>
      <div><span>End</span><strong>${escapeHtml(end)}</strong></div>
    </div>
    <div id="paymentPanel"></div>
    <div id="milestonePanel"></div>
    <div id="disputePanel"></div>
    <div id="reviewPanel"></div>
    <div class="actions" id="contractActions">${actions || '<span class="muted">No actions for this status.</span>'}</div>
  `;

  body.querySelectorAll('[data-status]').forEach((btn) => {
    btn.addEventListener('click', () => updateStatus(contract.id, btn.dataset.status, user, btn));
  });
    renderPaymentPanel(contract, user, payments);
  renderMilestonePanel(contract, user, []);
  loadMilestones(contract, user);
  loadDisputes(contract, user);
  loadContractReviews(contract, user);
}

function journeySteps(status) {
  const steps = [
    { key: 'pending', label: 'Fund' },
    { key: 'funded', label: 'Funded' },
    { key: 'in_progress', label: 'Work' },
    { key: 'submitted', label: 'Review' },
    { key: 'completed', label: 'Done' },
  ];
  const rank = {
    pending: 0,
    funded: 1,
    in_progress: 2,
    submitted: 3,
    approved: 3,
    disputed: 3,
    completed: 4,
    cancelled: -1,
  };
  const current = rank[status] ?? 0;
  return steps
    .map((step, index) => {
      let cls = '';
      if (status === 'cancelled') cls = index === 0 ? 'on' : '';
      else if (index < current) cls = 'done';
      else if (index === current) cls = 'on';
      return `<span class="${cls}">${step.label}</span>`;
    })
    .join('');
}

function latestPayment(payments) {
  const paid = payments.find((item) => item.status === 'paid');
  if (paid) return paid;
  return payments[0] || null;
}

function renderPaymentPanel(contract, user, payments) {
  const panel = document.getElementById('paymentPanel');
  if (!panel) return;
  const isClient = user.role === 'client' && user.id === contract.client_id;
  const payment = latestPayment(payments);
  const amount = formatCurrency(contract.agreed_amount, contract.currency);
  const readOnly = ['completed', 'cancelled', 'disputed', 'submitted', 'approved', 'in_progress', 'funded'].includes(contract.status);

  if (contract.status === 'pending' && isClient) {
    panel.innerHTML = `
      <div class="pay-box">
        <h2>Payment Required</h2>
        <p>Amount: <strong>${amount}</strong></p>
        <p class="muted">Status: Awaiting Payment</p>
        <a class="btn btn-primary" href="payment.html?contract_id=${contract.id}">Fund Contract</a>
      </div>
    `;
    return;
  }

  if (contract.status === 'pending') {
    panel.innerHTML = `
      <div class="pay-box">
        <h2>Payment Status</h2>
        <p>Awaiting Payment</p>
        <p class="muted">The client funds this contract. No charge has been made.</p>
      </div>
    `;
    return;
  }

  if (payment && payment.status === 'paid') {
    const paidOn = payment.paid_at ? new Date(payment.paid_at).toLocaleString() : '—';
    const heading = isClient ? '✓ Payment Completed' : 'Payment Status: Funded';
    panel.innerHTML = `
      <div class="pay-box">
        <h2>${heading}</h2>
        <p>Transaction ID: <strong>${escapeHtml(payment.transaction_id || '—')}</strong></p>
        <p>Amount Paid: <strong>${formatCurrency(payment.amount, payment.currency)}</strong></p>
        <p class="muted">Payment Date: ${escapeHtml(paidOn)}</p>
        <p><a href="payment-detail.html?id=${payment.id}">Payment details</a></p>
      </div>
    `;
    return;
  }

  if (readOnly) {
    const statusText = payment ? statusLabel(payment.status) : statusLabel(contract.status);
    panel.innerHTML = `
      <div class="pay-box">
        <h2>Payment Status</h2>
        <p>${escapeHtml(statusText)}</p>
        <p class="muted">${payment ? `Amount ${formatCurrency(payment.amount, payment.currency)}` : 'No payment has been recorded yet.'}</p>
        ${payment ? `<p><a href="payment-detail.html?id=${payment.id}">Payment details</a></p>` : ''}
      </div>
    `;
  }
}

function actionButtons(contract, user) {
  const status = contract.status;
  const isClient = user.id === contract.client_id;
  const isFreelancer = user.id === contract.freelancer_id;
  const isAdmin = user.role === 'admin';
  const buttons = [];

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
    loadContract(id, user);
  } catch (err) {
    button.disabled = false;
    showToast(err.message || 'Could not update contract.', 'error');
  }
}

async function loadDisputes(contract, user) {
  const panel = document.getElementById('disputePanel');
  if (!panel) return;
  panel.innerHTML = '<p class="muted">Loading disputes…</p>';
  try {
    const disputes = await api(`/contracts/${contract.id}/disputes`);
    renderDisputePanel(contract, user, disputes);
  } catch (err) {
    panel.innerHTML = `<p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load disputes.')}</p>`;
  }
}

function renderDisputePanel(contract, user, disputes) {
  const panel = document.getElementById('disputePanel');
  if (!panel) return;
  const isParty = user.id === contract.client_id || user.id === contract.freelancer_id;
  const isAdmin = user.role === 'admin';
  const active = disputes.find((item) => item.status === 'open' || item.status === 'under_review');
  const canOpen = isParty
    && !active
    && !['completed', 'cancelled'].includes(contract.status);

  const list = disputes.length
    ? disputes.map((item) => `
        <div class="dispute-item">
          <p><span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(item.status === 'open' ? 'Open' : statusLabel(item.status))}</span>
            <strong style="margin-left:8px;">${escapeHtml(item.reason)}</strong></p>
          <p class="muted">${escapeHtml(item.description)}</p>
          <p class="muted">Opened by ${escapeHtml(item.opener_name || `#${item.opened_by}`)}
            · ${escapeHtml(new Date(item.created_at).toLocaleString())}</p>
          ${item.resolution ? `<p class="muted">Resolution: ${escapeHtml(statusLabel(item.resolution))}${item.partial_amount != null ? ` (${formatMoney(item.partial_amount)})` : ''}</p>` : ''}
          ${item.resolution_notes ? `<p class="muted">${escapeHtml(item.resolution_notes)}</p>` : ''}
          ${isAdmin && (item.status === 'open' || item.status === 'under_review') ? `
            <form class="ms-form" data-resolve-dispute="${item.id}">
              <strong>Resolve dispute</strong>
              <select name="outcome" required>
                <option value="resolved">Resolve</option>
                <option value="rejected">Reject</option>
              </select>
              <select name="resolution">
                <option value="">Resolution (if resolving)</option>
                <option value="refund_client">Refund client</option>
                <option value="release_to_freelancer">Release to freelancer</option>
                <option value="partial_refund">Partial refund</option>
              </select>
              <input name="partial_amount" type="number" min="0.01" step="0.01" placeholder="Partial amount (optional)">
              <textarea name="notes" maxlength="4000" placeholder="Notes"></textarea>
              <button class="btn btn-primary" type="submit">Apply resolution</button>
            </form>
            ${item.status === 'open' ? `<button type="button" class="btn btn-outline" data-review-dispute="${item.id}">Mark under review</button>` : ''}
          ` : ''}
        </div>
      `).join('')
    : '<p class="muted">No disputes on this contract.</p>';

  const form = canOpen
    ? `
      <form class="ms-form" id="disputeForm">
        <strong>Open a dispute</strong>
        <input name="reason" required maxlength="200" placeholder="Reason">
        <textarea name="description" required maxlength="8000" minlength="10" placeholder="Describe the issue"></textarea>
        <button class="btn btn-outline" type="submit">Submit dispute</button>
      </form>
    `
    : '';

  panel.innerHTML = `
    <div class="dispute-box">
      <h2>Disputes</h2>
      <p class="muted">Only contract parties can open a dispute. Admins resolve outcomes from the admin console.</p>
      ${list}
      ${form}
    </div>
  `;

  panel.querySelector('#disputeForm')?.addEventListener('submit', (event) => submitDispute(event, contract, user));
  panel.querySelectorAll('[data-resolve-dispute]').forEach((formEl) => {
    formEl.addEventListener('submit', (event) => resolveDispute(event, contract, user));
  });
  panel.querySelectorAll('[data-review-dispute]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await api(`/disputes/${button.dataset.reviewDispute}`, {
          method: 'PATCH',
          body: JSON.stringify({ status: 'under_review' }),
        });
        showToast('Dispute marked under review.');
        loadContract(contract.id, user);
      } catch (err) {
        showToast(err.message || 'Could not update dispute.', 'error');
      }
    });
  });
}

async function submitDispute(event, contract, user) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;
  try {
    await api(`/contracts/${contract.id}/disputes`, {
      method: 'POST',
      body: JSON.stringify({
        reason: form.reason.value.trim(),
        description: form.description.value.trim(),
      }),
    });
    showToast('Dispute opened.');
    loadContract(contract.id, user);
  } catch (err) {
    if (button) button.disabled = false;
    showToast(err.message || 'Could not open dispute.', 'error');
  }
}

async function resolveDispute(event, contract, user) {
  event.preventDefault();
  const form = event.currentTarget;
  const disputeId = form.dataset.resolveDispute;
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
    showToast('Dispute updated.');
    loadContract(contract.id, user);
  } catch (err) {
    showToast(err.message || 'Could not resolve dispute.', 'error');
  }
}

const MILESTONE_STEPS = ['pending', 'funded', 'in_progress', 'submitted', 'approved', 'released'];

function milestoneProgress(status) {
  const index = MILESTONE_STEPS.indexOf(status);
  if (index < 0) return 0;
  return Math.round(((index + 1) / MILESTONE_STEPS.length) * 100);
}

async function loadMilestones(contract, user) {
  const panel = document.getElementById('milestonePanel');
  if (!panel) return;
  panel.innerHTML = '<p class="muted">Loading milestones…</p>';
  try {
    const milestones = await api(`/contracts/${contract.id}/milestones`);
    renderMilestonePanel(contract, user, milestones);
  } catch (err) {
    panel.innerHTML = `<p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load milestones.')}</p>`;
  }
}

function renderMilestonePanel(contract, user, milestones) {
  const panel = document.getElementById('milestonePanel');
  if (!panel) return;
  const isClient = user.role === 'client' && user.id === contract.client_id;
  const form = isClient && contract.status === 'pending'
    ? `
      <form class="ms-form" id="milestoneForm">
        <strong>Add milestone</strong>
        <input name="title" required maxlength="200" placeholder="Title">
        <textarea name="description" maxlength="4000" placeholder="Description"></textarea>
        <input name="amount" type="number" min="0.5" step="0.01" required placeholder="Amount">
        <input name="due_date" type="date">
        <button class="btn btn-outline" type="submit">Save milestone</button>
      </form>
    `
    : '';
  const cards = milestones.length
    ? milestones.map((item) => milestoneCard(item, user, contract)).join('')
    : '<p class="muted">No milestones yet.</p>';
  panel.innerHTML = `
    <h2>Milestones</h2>
    <p class="muted">Fund each milestone, submit work, then approve and release payment.</p>
    ${cards}
    ${form}
  `;
  panel.querySelector('#milestoneForm')?.addEventListener('submit', (event) => createMilestone(event, contract, user));
  panel.querySelectorAll('[data-ms-action]').forEach((button) => {
    button.addEventListener('click', () => milestoneAction(button, contract, user));
  });
  panel.querySelectorAll('[data-ms-upload]').forEach((input) => {
    input.addEventListener('change', async () => {
      const file = input.files?.[0];
      input.value = '';
      if (!file) return;
      try {
        await uploadAttachment(file, { milestone_id: Number(input.dataset.msUpload), contract_id: contract.id });
        showToast('Deliverable uploaded.');
        loadMilestones(contract, user);
      } catch (err) {
        showToast(err.message || 'Upload failed.', 'error');
      }
    });
  });
  panel.querySelectorAll('[data-ms-files]').forEach((slot) => {
    const milestoneId = Number(slot.dataset.msFiles);
    const canDelete = user.role === 'admin' || (user.role === 'client' && user.id === contract.client_id);
    mountAttachmentPanel(slot, { milestone_id: milestoneId }, {
      title: 'Milestone files',
      canUpload: false,
      canDelete,
      empty: 'No files attached to this milestone.',
    });
  });
}

function milestoneCard(item, user, contract) {
  const isClient = user.role === 'client' && user.id === contract.client_id;
  const isFreelancer = user.role === 'freelancer' && user.id === contract.freelancer_id;
  const due = item.due_date ? new Date(item.due_date).toLocaleDateString() : 'No due date';
  const pay = item.payment_status ? statusLabel(item.payment_status) : 'Unpaid';
  const progress = milestoneProgress(item.status);
  const actions = [];
  let note = '';
  if (item.status === 'pending') {
    if (isClient) {
      note = '<p class="muted">Payment Required</p>';
      actions.push(`<a class="btn btn-primary" href="milestone-payment.html?milestone_id=${item.id}">Fund Milestone</a>`);
      actions.push(`<button type="button" class="btn btn-outline" data-ms-action="status" data-status="cancelled" data-id="${item.id}">Cancel</button>`);
    } else if (isFreelancer) {
      note = '<p class="muted">Awaiting Funding</p>';
    }
  }
  if (item.status === 'funded') {
    note = '<p class="muted">Funded</p>';
    if (isClient) note += '<p class="muted">Waiting for the freelancer to start this milestone.</p>';
    if (isFreelancer) {
      actions.push(`<button type="button" class="btn btn-primary" data-ms-action="status" data-status="in_progress" data-id="${item.id}">Start Milestone</button>`);
    }
    if (isClient) {
      actions.push(`<button type="button" class="btn btn-outline" data-ms-action="status" data-status="cancelled" data-id="${item.id}">Cancel</button>`);
    }
  }
  if (item.status === 'in_progress') {
    if (isFreelancer) {
      actions.push(`<label class="btn btn-outline" for="ms-file-${item.id}">Attach deliverable<input type="file" id="ms-file-${item.id}" data-ms-upload="${item.id}" hidden></label>`);
      actions.push(`<button type="button" class="btn btn-primary" data-ms-action="status" data-status="submitted" data-id="${item.id}">Submit Milestone</button>`);
    }
    if (isClient) {
      actions.push(`<button type="button" class="btn btn-outline" data-ms-action="status" data-status="cancelled" data-id="${item.id}">Cancel</button>`);
    }
  }
  if (isClient && item.status === 'submitted') {
    actions.push(`<button type="button" class="btn btn-primary" data-ms-action="status" data-status="approved" data-id="${item.id}">Approve Milestone</button>`);
  }
  if (isClient && item.status === 'approved') {
    actions.push(`<button type="button" class="btn btn-primary" data-ms-action="release" data-id="${item.id}">Release Payment</button>`);
  }
  if (item.status === 'released') {
    note = `
      <p style="color:var(--green);font-weight:600;">✓ Payment Released</p>
      <p class="muted">Transaction ID: ${escapeHtml(item.payment_transaction_id || '—')}</p>
    `;
  }
  return `
    <article class="ms-card">
      <div class="ms-top">
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          <p class="muted">${escapeHtml(item.description || '')}</p>
        </div>
        <span class="status-badge status-${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
      </div>
      <p>Amount: <strong>${formatCurrency(item.amount, contract.currency)}</strong></p>
      <p class="muted">Due ${escapeHtml(due)} · Payment ${escapeHtml(pay)}</p>
      ${note}
      <div class="progress" aria-label="Progress ${progress}%"><span style="width:${progress}%"></span></div>
      <div class="ms-files" data-ms-files="${item.id}"></div>
      <div class="ms-actions">${actions.join('')}</div>
    </article>
  `;
}

async function createMilestone(event, contract, user) {
  event.preventDefault();
  const form = event.currentTarget;
  const body = {
    title: form.title.value.trim(),
    description: form.description.value.trim() || null,
    amount: Number(form.amount.value),
    due_date: form.due_date.value || null,
  };
  try {
    await api(`/contracts/${contract.id}/milestones`, { method: 'POST', body: JSON.stringify(body) });
    showToast('Milestone saved.');
    loadMilestones(contract, user);
  } catch (err) {
    showToast(err.message || 'Could not save milestone.', 'error');
  }
}

async function milestoneAction(button, contract, user) {
  const id = button.dataset.id;
  button.disabled = true;
  try {
    if (button.dataset.msAction === 'release') {
      await api(`/milestones/${id}/release`, { method: 'POST', body: '{}' });
      showToast('Payment released.');
      loadMilestones(contract, user);
      return;
    }
    await api(`/milestones/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: button.dataset.status }),
    });
    showToast('Milestone updated.');
    loadMilestones(contract, user);
  } catch (err) {
    button.disabled = false;
    showToast(err.message || 'Could not update milestone.', 'error');
  }
}

async function loadContractReviews(contract, user) {
  const panel = document.getElementById('reviewPanel');
  if (!panel) return;
  if (contract.status !== 'completed') {
    panel.innerHTML = '';
    return;
  }
  panel.innerHTML = '<p class="muted">Loading reviews…</p>';
  try {
    const reviews = await api(`/contracts/${contract.id}/reviews`);
    const mine = reviews.find((item) => item.reviewer_id === user.id);
    const other = user.id === contract.client_id ? contract.freelancer : contract.client;
    const list = reviews.length
      ? reviews.map((item) => `
        <article class="ms-card">
          <div class="ms-top">
            <strong>${escapeHtml(item.reviewer?.name || 'Member')}</strong>
            <span class="review-stars">${starString(item.rating)} ${item.rating}.0</span>
          </div>
          <p>${escapeHtml(item.comment)}</p>
        </article>
      `).join('')
      : '<p class="muted">No reviews yet.</p>';
    const form = mine
      ? ''
      : `
        <form class="ms-form" id="reviewForm">
          <label>Your rating for ${escapeHtml(other?.name || 'the other party')}</label>
          <select name="rating" required>
            <option value="5">5 stars</option>
            <option value="4">4 stars</option>
            <option value="3">3 stars</option>
            <option value="2">2 stars</option>
            <option value="1">1 star</option>
          </select>
          <textarea name="comment" required maxlength="2000" placeholder="Write a review"></textarea>
          <button class="btn btn-primary" type="submit">Submit review</button>
        </form>
      `;
    panel.innerHTML = `<h2>Reviews</h2>${list}${form}`;
    panel.querySelector('#reviewForm')?.addEventListener('submit', (event) => submitReview(event, contract, user));
  } catch (err) {
    panel.innerHTML = `<p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load reviews.')}</p>`;
  }
}

async function submitReview(event, contract, user) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api('/reviews', {
      method: 'POST',
      body: JSON.stringify({
        contract_id: contract.id,
        rating: Number(form.rating.value),
        comment: form.comment.value.trim(),
      }),
    });
    showToast('Review submitted.');
    loadContractReviews(contract, user);
  } catch (err) {
    showToast(err.message || 'Could not submit review.', 'error');
  }
}
