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
  mountProjectFiles(project);
}

async function mountProjectFiles(project) {
  const panel = document.getElementById('projectFiles');
  if (!panel || !Auth.isLoggedIn()) {
    if (panel) panel.style.display = 'none';
    return;
  }
  const user = Auth.getUser();
  const canManage = user?.role === 'admin' || Number(project.client_id) === Number(user?.id);
  try {
    await listAttachments({ project_id: project.id });
  } catch (err) {
    panel.style.display = 'none';
    return;
  }
  panel.style.display = '';
  await mountAttachmentPanel(panel, { project_id: project.id }, {
    title: 'Project files',
    canUpload: Boolean(canManage || user?.role === 'freelancer'),
    canDelete: canManage,
    empty: 'No project files yet.',
  });
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

function canManageProject(project, user) {
  return user?.role === 'admin' || Number(project.client_id) === Number(user?.id);
}

async function renderRoleActions(project, user, actions) {
  const isManager = canManageProject(project, user);
  const locked = project.status === 'completed' || project.status === 'cancelled';
  const canEdit = user.role === 'admin' || (isManager && !locked);

  let contract = null;
  if (Auth.isLoggedIn()) {
    try {
      contract = await api(`/projects/${project.id}/contract`);
    } catch (err) {
      if (err.status !== 403 && err.status !== 404 && err.status) {
        actions.insertAdjacentHTML(
          'beforeend',
          `<p style="color:#B23A3A;">${escapeHtml(err.message)}</p>`
        );
      }
    }
  }

  if (isManager && (user.role === 'client' || user.role === 'admin')) {
    const contractBtn = contract
      ? `<a href="contract-detail.html?id=${contract.id}" class="btn btn-primary">View Contract</a>`
      : '';
    const editBtn = canEdit
      ? `<a href="project-posting.html?edit=${project.id}" class="btn btn-outline">Edit Project</a>`
      : '';
    actions.innerHTML = `${editBtn}${contractBtn}<a href="#proposals" class="btn btn-outline">View Proposals</a>`;
    loadRecommendedFreelancers(project.id);
    loadProposals(project.id);
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

  actions.innerHTML = `<a href="client-dashboard.html" class="btn btn-outline">Back to My Projects</a>`;
}

async function loadRecommendedFreelancers(projectId) {
  const panel = document.getElementById('recommendPanel');
  if (!panel) return;
  panel.style.display = '';
  panel.innerHTML = `<div class="card recommend-card"><p class="muted">Finding recommended freelancers…</p></div>`;
  try {
    const matches = await api(`/projects/${projectId}/recommended-freelancers?limit=5`);
    if (!matches.length) {
      panel.innerHTML = `
        <h2>Recommended Freelancers</h2>
        <p class="muted">No strong matches yet. Ask freelancers to complete their skills and rates.</p>
      `;
      return;
    }
    panel.innerHTML = `
      <h2>Recommended Freelancers</h2>
      <p class="muted">Top matches based on skills, brief fit, budget, rating, and completed work.</p>
      ${matches.map(renderRecommendCard).join('')}
    `;
    panel.querySelectorAll('[data-hire-open]').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (typeof openHireFlow !== 'function') return;
        openHireFlow({
          id: Number(btn.dataset.id),
          name: btn.dataset.name,
          title: btn.dataset.title,
          skills: String(btn.dataset.skills || '')
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
        });
      });
    });
  } catch (err) {
    panel.innerHTML = `
      <h2>Recommended Freelancers</h2>
      <div class="card recommend-card"><p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load matches.')}</p></div>
    `;
  }
}

function renderRecommendCard(match) {
  const person = match.freelancer || {};
  const name = person.name || 'Freelancer';
  const rating = Number(person.ratings?.average || 0);
  const ratingCount = Number(person.ratings?.count || 0);
  const rate = person.hourly_rate != null ? `${formatMoney(person.hourly_rate)}/hr` : 'Rate not set';
  const matched = (match.matched_skills || [])
    .slice(0, 8)
    .map((skill) => `<span class="tag">${escapeHtml(skill)}</span>`)
    .join('');
  const reasons = (match.reasons || [])
    .map((reason) => `<li>${escapeHtml(reason)}</li>`)
    .join('');
  const profileLink = person.id
    ? `<a href="freelancer-profile.html?id=${person.id}">${escapeHtml(name)}</a>`
    : escapeHtml(name);

  return `
    <article class="card recommend-card">
      <div class="recommend-top">
        <div class="recommend-person">
          <div class="avatar-sm">${escapeHtml(initials(name))}</div>
          <div>
            <h3>${profileLink}</h3>
            <div style="color:var(--slate);font-size:0.88rem;">${escapeHtml(person.title || 'Freelancer')}</div>
          </div>
        </div>
        <span class="recommend-score">${Number(match.match_score || 0)}% match</span>
      </div>
      <div class="recommend-meta">
        <span><span class="stars">${starString(rating)}</span> ${rating.toFixed(1)} (${ratingCount})</span>
        <span>${escapeHtml(rate)}</span>
        <span>${Number(person.projects_done || 0)} projects done</span>
      </div>
      ${matched ? `<div class="recommend-tags">${matched}</div>` : ''}
      ${reasons ? `<ul class="recommend-reasons">${reasons}</ul>` : ''}
      <div class="recommend-foot">
        ${
          person.id
            ? `<a class="btn btn-outline btn-sm" href="freelancer-profile.html?id=${person.id}">View profile</a>
               <button type="button" class="btn btn-primary btn-sm" data-hire-open
                 data-id="${person.id}"
                 data-name="${escapeHtml(name)}"
                 data-title="${escapeHtml(person.title || 'Freelancer')}"
                 data-skills="${escapeHtml((person.skills || []).join(','))}">Hire</button>`
            : ''
        }
      </div>
    </article>
  `;
}

async function loadProposals(projectId) {
  const panel = document.getElementById('proposalPanel');
  if (!panel) return;
  panel.innerHTML = `<div class="card proposal-card"><p style="color:var(--slate);">Loading proposals…</p></div>`;
  try {
    const proposals = await api(`/projects/${projectId}/proposals`);
    const count = document.getElementById('projectProposals');
    if (count) count.textContent = String(proposals.length);
    if (!proposals.length) {
      panel.innerHTML = `<div class="proposal-list" id="proposals"><h2>Proposals</h2><div class="card proposal-card"><p style="color:var(--slate);">No proposals yet.</p></div></div>`;
      return;
    }
    panel.innerHTML = `
      <div class="proposal-list" id="proposals">
        <h2>Proposals</h2>
        ${proposals.map(renderProposalCard).join('')}
      </div>
    `;
    panel.querySelectorAll('[data-accept]').forEach((btn) => {
      btn.addEventListener('click', () => decideProposal(projectId, Number(btn.dataset.accept), 'accepted', btn));
    });
    panel.querySelectorAll('[data-reject]').forEach((btn) => {
      btn.addEventListener('click', () => decideProposal(projectId, Number(btn.dataset.reject), 'rejected', btn));
    });
  } catch (err) {
    panel.innerHTML = `<div class="card proposal-card"><p style="color:#B23A3A;">${escapeHtml(err.message)}</p></div>`;
  }
}

function renderProposalCard(proposal) {
  const person = proposal.freelancer || {};
  const name = person.name || 'Freelancer';
  const pending = proposal.status === 'pending';
  const rating = Number(person.rating_avg || 0);
  const ratingCount = Number(person.rating_count || 0);
  const skills = (person.skills || [])
    .slice(0, 6)
    .map((skill) => `<span class="tag">${escapeHtml(skill)}</span>`)
    .join('');
  const milestones = (proposal.milestones || [])
    .map((item) => {
      const label = escapeHtml(item.description || item.title || 'Milestone');
      const amount = item.amount != null ? ` — ${formatMoney(item.amount)}` : '';
      return `<li>${label}${amount}</li>`;
    })
    .join('');
  const when = proposal.created_at ? new Date(proposal.created_at).toLocaleDateString() : '—';
  const badge = proposal.status === 'accepted'
    ? 'status-accepted'
    : proposal.status === 'rejected'
      ? 'status-rejected'
      : 'status-pending';
  const profile = person.id
    ? `<a href="freelancer-profile.html?id=${person.id}">${escapeHtml(name)}</a>`
    : escapeHtml(name);
  const actions = pending
    ? `<div class="proposal-actions">
        <button type="button" class="btn btn-primary btn-sm" data-accept="${proposal.id}">Accept</button>
        <button type="button" class="btn btn-outline btn-sm" data-reject="${proposal.id}">Reject</button>
      </div>`
    : proposal.contract_id
      ? `<a class="btn btn-outline btn-sm" href="contract-detail.html?id=${proposal.contract_id}">View Contract</a>`
      : '';

  return `
    <article class="card proposal-card">
      <div class="proposal-top">
        <div>
          <h3>${profile}</h3>
          <div style="color:var(--slate);font-size:0.88rem;">${escapeHtml(person.title || 'Freelancer')}</div>
        </div>
        <span class="proposal-bid">${formatMoney(proposal.bid_amount)}</span>
      </div>
      <div class="proposal-meta">
        <span><span class="stars">${starString(rating)}</span> ${rating.toFixed(1)} (${ratingCount})</span>
        <span>${escapeHtml(proposal.estimated_duration || 'Duration not specified')}</span>
        <span>Submitted ${escapeHtml(when)}</span>
      </div>
      <div class="brief-tags">${skills || '<span class="tag">No skills listed</span>'}</div>
      <p class="proposal-letter">${escapeHtml(proposal.cover_letter || '')}</p>
      ${milestones ? `<ul class="proposal-milestones">${milestones}</ul>` : '<p style="color:var(--slate);font-size:0.9rem;">No milestones listed.</p>'}
      <div class="proposal-foot">
        <span class="status-badge ${badge}">${escapeHtml(statusLabel(proposal.status))}</span>
        ${actions}
      </div>
    </article>
  `;
}

async function decideProposal(projectId, proposalId, nextStatus, button) {
  if (nextStatus === 'rejected' && !window.confirm('Reject this proposal?')) return;
  const original = button.textContent;
  button.disabled = true;
  button.textContent = nextStatus === 'accepted' ? 'Accepting…' : 'Rejecting…';
  try {
    const data = await api(`/proposals/${proposalId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: nextStatus }),
    });
    showToast(nextStatus === 'accepted'
      ? (data.contract_id ? 'Proposal accepted. Contract created.' : 'Proposal accepted.')
      : 'Proposal rejected.');
    await loadProject(projectId);
    await loadProposals(projectId);
  } catch (err) {
    button.disabled = false;
    button.textContent = original;
    showToast(err.message || 'Could not update proposal.', 'error');
  }
}
