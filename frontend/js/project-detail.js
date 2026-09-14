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

  const isOwner =
    (user.role === 'client' || user.role === 'admin') && project.client_id === user.id;

  if (isOwner) {
    actions.innerHTML = `
      <a href="project-posting.html?edit=${project.id}" class="btn btn-outline">Edit Project</a>
      <a href="client-dashboard.html" class="btn btn-primary">View Proposals (${project.proposal_count || 0})</a>
    `;
    return;
  }

  if (user.role === 'freelancer') {
    actions.innerHTML = `
      <a href="proposal-submission.html?project_id=${project.id}" class="btn btn-primary">Submit Proposal</a>
      <a href="messaging.html" class="btn btn-outline">Message Client</a>
    `;
    return;
  }

  actions.innerHTML = `<a href="client-dashboard.html" class="btn btn-outline">Go to Dashboard</a>`;
}
