// ============================================
// dashboard.js — Client & Freelancer dashboards
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  const projectList = document.getElementById('projectList');
  const isFreelancerDash = Boolean(projectList);
  const isClientDash = Boolean(document.querySelector('.myproject-item') || document.querySelector('.dash-grid'));

  // Client-side chip/search filters (freelancer)
  const chips = document.querySelectorAll('.filter-chip');
  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      chips.forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      applyLocalFilters();
    });
  });

  const searchInput = document.querySelector('.search-input');
  searchInput?.addEventListener('input', () => applyLocalFilters());

  if (isFreelancerDash) {
    const user = requireAuth(['freelancer']);
    if (!user) return;
    greet(user);
    loadBrowseProjects();
  } else if (isClientDash) {
    const user = requireAuth(['client', 'admin']);
    if (!user) return;
    greet(user);
    loadClientProjects();
  }
});

function greet(user) {
  const h1 = document.querySelector('.page-head h1, .dash-main h1, main h1');
  if (h1 && user?.name) {
    h1.textContent = `Welcome back, ${user.name.split(' ')[0]}`;
  }
}

function applyLocalFilters() {
  const category = document.querySelector('.filter-chip.active')?.textContent.trim() || 'All';
  const query = (document.querySelector('.search-input')?.value || '').toLowerCase();
  document.querySelectorAll('.project-item').forEach((item) => {
    const title = item.querySelector('h3')?.textContent.toLowerCase() || '';
    const tags = Array.from(item.querySelectorAll('.tag')).map((t) => t.textContent.toLowerCase());
    const budgetText = item.querySelector('.project-budget')?.textContent || '';
    const maxMatch = budgetText.match(/[\d,]+/g);
    const maxBudget = maxMatch ? Number(maxMatch[maxMatch.length - 1].replace(/,/g, '')) : Infinity;

    let matchCat = category === 'All';
    if (category === 'Under $500') matchCat = maxBudget <= 500;
    else if (!matchCat) {
      matchCat = tags.some(
        (tag) => category.toLowerCase().includes(tag) || tag.includes(category.toLowerCase())
      );
    }

    const matchSearch = !query || title.includes(query);
    item.style.display = matchCat && matchSearch ? '' : 'none';
  });
}

async function loadBrowseProjects() {
  const list = document.getElementById('projectList');
  if (!list) return;
  list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">Loading projects…</p>';

  try {
    const projects = await api('/projects?status=open');
    if (!projects.length) {
      list.innerHTML =
        '<p style="color:var(--slate);padding:12px 0;">No open projects yet. Check back soon.</p>';
      return;
    }
    list.innerHTML = projects.map(renderBrowseCard).join('');
  } catch (err) {
    list.innerHTML = `<p style="color:#B23A3A;padding:12px 0;">${escapeHtml(err.message)}</p>`;
  }
}

function renderBrowseCard(project) {
  const tags = (project.skills || [])
    .slice(0, 4)
    .map((s) => `<span class="tag">${escapeHtml(s)}</span>`)
    .join('');
  const clientName = project.client?.name || 'Client';
  return `
    <div class="card project-item" data-category="${escapeHtml(project.category)}">
      <div>
        <h3>${escapeHtml(project.title)}</h3>
        <p class="meta">Posted ${timeAgo(project.created_at)} · Remote · Client: ${escapeHtml(clientName)}</p>
        <div class="tags">${tags || `<span class="tag">${escapeHtml(project.category)}</span>`}</div>
      </div>
      <div class="project-proposals">${project.proposal_count || 0} proposals</div>
      <div class="project-budget"><span class="label">Budget</span>${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')}</div>
      <a href="proposal-submission.html?id=${project.id}" class="btn btn-outline btn-sm">Submit Proposal</a>
    </div>
  `;
}

async function loadClientProjects() {
  const section = document.querySelector('.dash-grid > div');
  if (!section) return;

  const titleRow = section.querySelector('.section-title');
  const existing = section.querySelectorAll('.myproject-item');
  existing.forEach((el) => el.remove());

  const loading = document.createElement('p');
  loading.id = 'clientProjectsLoading';
  loading.style.cssText = 'color:var(--slate);padding:12px 0;';
  loading.textContent = 'Loading your projects…';
  titleRow?.after(loading);

  try {
    const projects = await api('/projects/mine');
    loading.remove();

    const active = projects.filter((p) => p.status !== 'cancelled' && p.status !== 'completed');
    const welcome = document.querySelector('.page-head p, .dash-main .page-head p, main .page-head p');
    if (welcome) {
      welcome.textContent = `You have ${active.length} active project${active.length === 1 ? '' : 's'}.`;
    }
    const activeStat = document.querySelector('.stats-row .stat-card .val');
    if (activeStat) activeStat.textContent = String(active.length);

    if (!projects.length) {
      const empty = document.createElement('p');
      empty.style.cssText = 'color:var(--slate);padding:12px 0;';
      empty.textContent = 'No projects yet. Post your first brief.';
      titleRow?.after(empty);
      return;
    }

    const html = projects.map(renderClientCard).join('');
    titleRow.insertAdjacentHTML('afterend', html);
  } catch (err) {
    loading.textContent = err.message;
    loading.style.color = '#B23A3A';
  }
}

function renderClientCard(project) {
  return `
    <div class="card myproject-item">
      <div class="myproject-top">
        <h3>${escapeHtml(project.title)}</h3>
        <span class="status-badge ${statusClass(project.status)}">${statusLabel(project.status)}</span>
      </div>
      <p class="myproject-meta">Budget: ${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')} · Posted ${timeAgo(project.created_at)}</p>
      <div class="myproject-foot">
        <span>${project.proposal_count || 0} proposals received</span>
        <a href="messaging.html" class="btn btn-outline btn-sm">Messages</a>
      </div>
    </div>
  `;
}
