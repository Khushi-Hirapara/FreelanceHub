// ============================================
// project-detail.js — single project view
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const projectId = Number(params.get('id') || params.get('project_id'));

  const backLink = document.getElementById('backLink');
  const user = Auth.getUser();
  if (user?.role === 'client' || user?.role === 'admin') {
    backLink.href = 'client-dashboard.html';
    backLink.textContent = '← Back to My Projects';
  } else {
    backLink.href = 'freelancer-dashboard.html';
    backLink.textContent = '← Back to Find Work';
  }

  if (!projectId) {
    document.getElementById('projectTitle').textContent = 'Project not found';
    document.getElementById('projectDescription').textContent =
      'Open a project from Find Work or My Projects.';
    return;
  }

  loadProject(projectId);
});

async function loadProject(projectId) {
  try {
    const project = await api(`/projects/${projectId}`);
    renderProject(project);
  } catch (err) {
    document.getElementById('projectTitle').textContent = 'Could not load project';
    document.getElementById('projectDescription').textContent = err.message || 'Try again later.';
    showToast(err.message || 'Could not load project.', 'error');
  }
}

function renderProject(project) {
  document.title = `${project.title} — FreelanceHub`;

  document.getElementById('projectCategory').textContent = project.category || 'Project';
  document.getElementById('projectTitle').textContent = project.title;
  document.getElementById('projectBudget').textContent =
    `Budget: ${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')}`;
  document.getElementById('projectDescription').textContent = project.description || '';

  const skillsEl = document.getElementById('projectSkills');
  const skills = project.skills || [];
  skillsEl.innerHTML = skills.length
    ? skills.map((s) => `<span class="tag">${escapeHtml(s)}</span>`).join('')
    : `<span class="tag">${escapeHtml(project.category || 'General')}</span>`;

  document.getElementById('projectStatus').textContent = statusLabel(project.status);
  document.getElementById('projectPosted').textContent = timeAgo(project.created_at);
  document.getElementById('projectProposals').textContent = String(project.proposal_count || 0);
  document.getElementById('projectDeadline').textContent = project.deadline
    ? new Date(project.deadline).toLocaleDateString()
    : 'Flexible';
  document.getElementById('projectExperience').textContent = project.experience_level || 'Any';

  if (project.client) {
    document.getElementById('clientAvatar').textContent = initials(project.client.name);
    document.getElementById('clientName').textContent = project.client.name;
    const company = project.client.title ? ` · ${project.client.title}` : '';
    document.getElementById('clientMeta').textContent =
      `Client${company} · ${project.client.projects_done || 0} projects posted`;
  }

  renderActions(project);
}

function renderActions(project) {
  const actions = document.getElementById('projectActions');
  const user = Auth.getUser();

  if (!Auth.isLoggedIn() || !user) {
    actions.innerHTML = `
      <a href="login.html" class="btn btn-primary">Log in to apply</a>
      <a href="freelancer-dashboard.html" class="btn btn-outline">Browse more work</a>
    `;
    return;
  }

  renderRoleActions(project, user, actions);
}

async function renderRoleActions(project, user, actions) {
  const isOwner =
    (user.role === 'client' || user.role === 'admin') && project.client_id === user.id;

  let contract = null;
  if (Auth.isLoggedIn()) {
    try {
      contract = await api(`/projects/${project.id}/contract`);
    } catch (err) {
      if (err.status === 403) {
        contract = null;
      } else if (err.status && err.status !== 404) {
        actions.insertAdjacentHTML(
          'beforeend',
          `<p style="color:#B23A3A;">${escapeHtml(err.message)}</p>`
        );
      }
    }
  }

  if (isOwner) {
    const contractBtn = contract
      ? `<a href="contract-detail.html?id=${contract.id}" class="btn btn-primary">View Contract</a>`
      : '';
    actions.innerHTML = `
      <a href="project-posting.html?edit=${project.id}" class="btn btn-outline">Edit Project</a>
      ${contractBtn}
    `;
    if (!contract) loadProposals(project.id);
    return;
  }

  if (user.role === 'freelancer') {
    const contractBtn = contract
      ? `<a href="contract-detail.html?id=${contract.id}" class="btn btn-outline">View Contract</a>`
      : `<a href="proposal-submission.html?project_id=${project.id}" class="btn btn-primary">Submit Proposal</a>`;
    actions.innerHTML = `
      ${contractBtn}
      <a href="messaging.html" class="btn btn-outline">Message Client</a>
    `;
    return;
  }

  if (user.role === 'admin' && contract) {
    actions.innerHTML = `<a href="contract-detail.html?id=${contract.id}" class="btn btn-primary">View Contract</a>`;
    return;
  }

  actions.innerHTML = `<a href="client-dashboard.html" class="btn btn-outline">Go to Dashboard</a>`;
}

async function loadProposals(projectId) {
  const panel = document.getElementById('proposalPanel');
  if (!panel) return;
  panel.innerHTML = `<div class="card" style="padding:var(--space-4);margin-bottom:var(--space-4);"><p style="color:var(--slate);">Loading proposals…</p></div>`;
  try {
    const proposals = await api(`/projects/${projectId}/proposals`);
    if (!proposals.length) {
      panel.innerHTML = `<div class="card" style="padding:var(--space-4);"><p style="color:var(--slate);">No proposals yet.</p></div>`;
      return;
    }
    panel.innerHTML = `
      <h2 style="font-family:var(--font-display);font-size:1.4rem;margin:0 0 var(--space-3);">Proposals</h2>
      ${proposals.map(renderProposalCard).join('')}
    `;
    panel.querySelectorAll('[data-accept]').forEach((btn) => {
      btn.addEventListener('click', () => acceptProposal(Number(btn.dataset.accept), btn));
    });
  } catch (err) {
    panel.innerHTML = `<div class="card" style="padding:var(--space-4);"><p style="color:#B23A3A;">${escapeHtml(err.message)}</p></div>`;
  }
}

function renderProposalCard(proposal) {
  const name = proposal.freelancer?.name || 'Freelancer';
  const pending = proposal.status === 'pending';
  return `
    <article class="card" style="padding:var(--space-4);margin-bottom:var(--space-3);">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
        <div>
          <h3 style="font-family:var(--font-display);font-size:1.1rem;margin-bottom:4px;">${escapeHtml(name)}</h3>
          <p style="color:var(--slate);font-size:0.9rem;margin-bottom:8px;">${escapeHtml(proposal.estimated_duration || 'Duration not specified')}</p>
        </div>
        <strong style="color:var(--green);font-family:var(--font-mono);">${formatMoney(proposal.bid_amount)}</strong>
      </div>
      <p style="white-space:pre-wrap;color:var(--ink);font-size:0.95rem;margin-bottom:12px;">${escapeHtml(proposal.cover_letter || '')}</p>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">
        <span class="status-badge ${proposal.status === 'accepted' ? 'status-accepted' : 'status-pending'}">${escapeHtml(statusLabel(proposal.status))}</span>
        ${pending ? `<button type="button" class="btn btn-primary" data-accept="${proposal.id}">Accept proposal</button>` : (proposal.contract_id ? `<a class="btn btn-outline" href="contract-detail.html?id=${proposal.contract_id}">View Contract</a>` : '')}
      </div>
    </article>
  `;
}

async function acceptProposal(proposalId, button) {
  button.disabled = true;
  button.textContent = 'Accepting…';
  try {
    const data = await api(`/proposals/${proposalId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'accepted' }),
    });
    const link = data.contract_id
      ? ` <a href="contract-detail.html?id=${data.contract_id}" style="color:inherit;text-decoration:underline;">View contract</a>`
      : '';
    showToast('Proposal accepted. Contract created.' + (data.contract_id ? '' : ''));
    const panel = document.getElementById('proposalPanel');
    if (panel) {
      panel.innerHTML = `
        <div class="card" style="padding:var(--space-4);margin-bottom:var(--space-4);">
          <p>Proposal accepted. A contract is pending (no payment yet).${link}</p>
        </div>
      `;
    }
    const actions = document.getElementById('projectActions');
    if (actions && data.contract_id) {
      actions.insertAdjacentHTML(
        'beforeend',
        ` <a href="contract-detail.html?id=${data.contract_id}" class="btn btn-primary">View Contract</a>`
      );
    }
  } catch (err) {
    button.disabled = false;
    button.textContent = 'Accept proposal';
    showToast(err.message || 'Could not accept proposal.', 'error');
  }
}
