// ============================================
// dashboard.js — Client & Freelancer dashboards (live data)
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  const projectList = document.getElementById('projectList');
  const proposalsList = document.getElementById('proposalsList');
  const isFreelancerDash = Boolean(projectList);
  const isMyProposals = Boolean(proposalsList);
  const isClientDash = Boolean(document.querySelector('.dash-grid') || document.getElementById('clientProjectList'));

  document.querySelectorAll('.filter-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.filter-chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      applyLocalFilters();
    });
  });

  document.querySelector('.search-input')?.addEventListener('input', () => applyLocalFilters());

  if (isFreelancerDash) {
    const user = requireAuth(['freelancer']);
    if (!user) return;
    fillSidebar(user, 'freelancer');
    loadFreelancerDashboard();
  } else if (isMyProposals) {
    const user = requireAuth(['freelancer']);
    if (!user) return;
    fillSidebar(user, 'freelancer');
    loadMyProposals();
  } else if (isClientDash) {
    const user = requireAuth(['client', 'admin']);
    if (!user) return;
    fillSidebar(user, 'client');
    loadClientDashboard();
  }
});

function fillSidebar(user, role) {
  const avatar = document.querySelector('.sidebar-profile .avatar');
  const name = document.querySelector('.sidebar-profile h4');
  const meta = document.querySelector('.sidebar-profile span');
  if (avatar) avatar.textContent = initials(user.name);
  if (name) name.textContent = user.name;
  if (meta) {
    meta.textContent =
      role === 'freelancer' ? 'Freelancer' : role === 'admin' ? 'Admin' : 'Client';
  }
}

function applyLocalFilters() {
  const category = document.querySelector('.filter-chip.active')?.textContent.trim() || 'All';
  const query = (document.querySelector('.search-input')?.value || '').toLowerCase();
  document.querySelectorAll('.project-item').forEach((item) => {
    const title = item.querySelector('h3')?.textContent.toLowerCase() || '';
    const itemCat = (item.dataset.category || '').toLowerCase();
    const tags = Array.from(item.querySelectorAll('.tag')).map((t) => t.textContent.toLowerCase());
    const budgetText = item.querySelector('.project-budget')?.textContent || '';
    const maxMatch = budgetText.match(/[\d,]+/g);
    const maxBudget = maxMatch ? Number(maxMatch[maxMatch.length - 1].replace(/,/g, '')) : Infinity;

    let matchCat = category === 'All';
    if (category === 'Under $500') matchCat = maxBudget <= 500;
    else if (!matchCat) {
      matchCat =
        itemCat.includes(category.toLowerCase()) ||
        tags.some((tag) => category.toLowerCase().includes(tag) || tag.includes(category.toLowerCase()));
    }

    item.style.display = matchCat && (!query || title.includes(query)) ? '' : 'none';
  });
}

async function loadFreelancerDashboard() {
  const list = document.getElementById('projectList');
  list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">Loading projects…</p>';

  try {
    const [summary, projects] = await Promise.all([
      api('/dashboard/summary'),
      api('/projects?status=open'),
    ]);

    const h1 = document.querySelector('.dash-header h1');
    const sub = document.querySelector('.dash-header p');
    // Keep page title "Find Work" — only update subtitle
    if (sub) {
      sub.textContent =
        projects.length === 0
          ? 'No open briefs yet — check back soon.'
          : `${projects.length} open brief${projects.length === 1 ? '' : 's'} on the board right now.`;
    }
    if (h1 && h1.textContent.trim() === 'Find your next project') {
      h1.textContent = 'Find Work';
    }

    const vals = document.querySelectorAll('.stats-row .stat-card .val');
    const deltas = document.querySelectorAll('.stats-row .stat-card .delta');
    if (vals[0]) vals[0].textContent = String(summary.active_bids || 0);
    if (deltas[0]) deltas[0].textContent = `${summary.awaiting_reply || 0} awaiting reply`;
    if (vals[1]) vals[1].textContent = String(summary.active_contracts || 0);
    if (deltas[1]) deltas[1].textContent = summary.active_contracts ? 'Accepted proposals' : 'None yet';
    if (vals[2]) vals[2].textContent = formatMoney(summary.paid_earnings || summary.earned || 0);
    if (deltas[2]) deltas[2].textContent = `Pending ${formatMoney(summary.pending_earnings || 0)}`;
    if (vals[3]) vals[3].textContent = Number(summary.rating_avg || 0).toFixed(1);
    if (deltas[3]) deltas[3].textContent = `${summary.rating_count || 0} reviews`;

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
        <h3><a href="project-detail.html?id=${project.id}">${escapeHtml(project.title)}</a></h3>
        <p class="meta">Posted ${timeAgo(project.created_at)} · Remote · Client: ${escapeHtml(clientName)}</p>
        <div class="tags">${tags || `<span class="tag">${escapeHtml(project.category)}</span>`}</div>
      </div>
      <div class="project-proposals">${project.proposal_count || 0} proposals</div>
      <div class="project-budget"><span class="label">Budget</span>${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')}</div>
      <a href="project-detail.html?id=${project.id}" class="btn btn-outline btn-sm">View Project</a>
    </div>
  `;
}

async function loadClientDashboard() {
  const list = document.getElementById('clientProjectList');
  const activityEl = document.getElementById('activityFeed');
  if (list) list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">Loading your projects…</p>';

  try {
    const [summary, projects] = await Promise.all([
      api('/dashboard/summary'),
      api('/projects/mine'),
    ]);

    const user = Auth.getUser();
    const h1 = document.querySelector('.dash-header h1');
    const sub = document.querySelector('.dash-header p');
    if (h1 && user?.name) h1.textContent = `Welcome back, ${user.name.split(' ')[0]}`;
    if (sub) {
      sub.textContent = `You have ${summary.active_projects || 0} active project${
        summary.active_projects === 1 ? '' : 's'
      } and ${summary.new_proposals || 0} new proposal${summary.new_proposals === 1 ? '' : 's'} to review.`;
    }

    const vals = document.querySelectorAll('.stats-row .stat-card .val');
    const deltas = document.querySelectorAll('.stats-row .stat-card .delta');
    if (vals[0]) vals[0].textContent = String(summary.active_projects || 0);
    if (deltas[0]) deltas[0].textContent = 'Currently active';
    if (vals[1]) vals[1].textContent = String(summary.new_proposals || 0);
    if (deltas[1]) deltas[1].textContent = 'Pending review';
    if (vals[2]) vals[2].textContent = formatMoney(summary.total_spent || 0);
    if (deltas[2]) {
      deltas[2].textContent = `${summary.completed_payments || 0} completed · ${summary.pending_payments || 0} pending`;
    }
    if (vals[3]) vals[3].textContent = Number(summary.rating_avg || 0).toFixed(1);
    if (deltas[3]) deltas[3].textContent = `${summary.rating_count || 0} reviews left`;

    if (list) {
      if (!projects.length) {
        list.innerHTML =
          '<p style="color:var(--slate);padding:12px 0;">No projects yet. Post your first brief.</p>';
      } else {
        list.innerHTML = projects.map(renderClientCard).join('');
      }
    }

    if (activityEl) {
      if (!summary.activity?.length) {
        activityEl.innerHTML =
          '<div class="activity-item"><div class="activity-dot"></div><div>No recent activity yet.<span class="time">Post a project to get proposals</span></div></div>';
      } else {
        activityEl.innerHTML = summary.activity
          .map(
            (a) => `
          <div class="activity-item">
            <div class="activity-dot"></div>
            <div>${escapeHtml(a.text)}<span class="time">${timeAgo(a.time)}</span></div>
          </div>
        `
          )
          .join('');
      }
    }
  } catch (err) {
    if (list) list.innerHTML = `<p style="color:#B23A3A;padding:12px 0;">${escapeHtml(err.message)}</p>`;
  }
}

function renderClientCard(project) {
  return `
    <div class="card myproject-item">
      <div class="myproject-top">
        <h3><a href="project-detail.html?id=${project.id}">${escapeHtml(project.title)}</a></h3>
        <span class="status-badge ${statusClass(project.status)}">${statusLabel(project.status)}</span>
      </div>
      <p class="myproject-meta">Budget: ${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')} · Posted ${timeAgo(project.created_at)}</p>
      <div class="myproject-foot">
        <span>${project.proposal_count || 0} proposals received</span>
        <a href="project-detail.html?id=${project.id}" class="btn btn-outline btn-sm">View Project</a>
      </div>
    </div>
  `;
}

async function loadMyProposals() {
  const list = document.getElementById('proposalsList');
  if (!list) return;
  list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">Loading your proposals…</p>';

  let allProposals = [];
  let activeFilter = 'all';

  try {
    allProposals = await api('/proposals/mine');
    updateProposalStats(allProposals);
    renderProposalList();
  } catch (err) {
    list.innerHTML = `<p style="color:#B23A3A;padding:12px 0;">${escapeHtml(err.message)}</p>`;
  }

  document.querySelectorAll('#proposalFilters [data-filter]').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#proposalFilters [data-filter]').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter || 'all';
      renderProposalList();
    });
  });

  function updateProposalStats(proposals) {
    const stats = document.getElementById('proposalStats');
    const filters = document.getElementById('proposalFilters');
    const sub = document.getElementById('proposalsSub') || document.querySelector('.dash-header p');
    if (!proposals.length) {
      if (stats) stats.hidden = true;
      if (filters) filters.hidden = true;
      if (sub) sub.textContent = 'You haven’t submitted any proposals yet.';
      return;
    }
    if (stats) stats.hidden = false;
    if (filters) filters.hidden = false;
    const pending = proposals.filter((p) => p.status === 'pending').length;
    const accepted = proposals.filter((p) => p.status === 'accepted').length;
    const rejected = proposals.filter((p) => p.status === 'rejected' || p.status === 'withdrawn').length;
    setText('statTotal', String(proposals.length));
    setText('statPending', String(pending));
    setText('statAccepted', String(accepted));
    setText('statRejected', String(rejected));
    if (sub) {
      sub.textContent = `${proposals.length} proposal${proposals.length === 1 ? '' : 's'} · ${pending} waiting on clients`;
    }
  }

  function renderProposalList() {
    const filtered =
      activeFilter === 'all'
        ? allProposals
        : activeFilter === 'rejected'
          ? allProposals.filter((p) => p.status === 'rejected' || p.status === 'withdrawn')
          : allProposals.filter((p) => p.status === activeFilter);

    if (!allProposals.length) {
      list.innerHTML = `
        <div class="empty-box">
          <h3>No proposals yet</h3>
          <p>Browse open briefs, submit a strong cover letter and bid, then track everything here.</p>
          <a href="freelancer-dashboard.html" class="btn btn-primary">Browse projects</a>
        </div>
      `;
      return;
    }

    if (!filtered.length) {
      list.innerHTML = '<p style="color:var(--slate);padding:12px 0;">No proposals in this filter.</p>';
      return;
    }

    list.innerHTML = `<div class="prop-list">${filtered.map(renderProposalCard).join('')}</div>`;
  }
}

function renderProposalCard(proposal) {
  const title = proposal.project?.title || `Project #${proposal.project_id}`;
  const status = proposal.status || 'pending';
  const category = proposal.project?.category || 'Project';
  const letter = proposal.cover_letter || '';
  const preview = letter.length > 160 ? `${letter.slice(0, 160)}…` : letter;
  const projectHref = proposal.project_id
    ? `project-detail.html?id=${proposal.project_id}`
    : 'freelancer-dashboard.html';
  const contractHref = proposal.contract_id
    ? `contract-detail.html?id=${proposal.contract_id}`
    : null;

  let nextHint = 'Waiting for the client to review your bid.';
  if (status === 'accepted') nextHint = 'Proposal accepted — open the contract to continue.';
  if (status === 'rejected') nextHint = 'Not selected this time. Keep bidding on other briefs.';
  if (status === 'withdrawn') nextHint = 'You withdrew this proposal.';

  return `
    <article class="proposal-item">
      <div class="proposal-top">
        <div>
          <div class="proposal-cat">${escapeHtml(category)}</div>
          <h3>${escapeHtml(title)}</h3>
        </div>
        <span class="status-badge status-${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span>
      </div>
      <p class="proposal-letter">${escapeHtml(preview || 'No cover letter provided.')}</p>
      <div class="proposal-metrics">
        <div class="bid"><span>Your bid</span><strong>${formatMoney(proposal.bid_amount)}</strong></div>
        <div><span>Timeline</span><strong>${escapeHtml(proposal.estimated_duration || 'Flexible')}</strong></div>
        <div><span>Next</span><strong style="font-size:0.88rem;font-weight:500;">${escapeHtml(nextHint)}</strong></div>
      </div>
      <div class="proposal-foot">
        <span class="when">Submitted ${escapeHtml(timeAgo(proposal.created_at))}</span>
        <div class="proposal-ctas">
          <a class="btn btn-outline btn-sm" href="${projectHref}">View project</a>
          ${
            contractHref
              ? `<a class="btn btn-primary btn-sm" href="${contractHref}">View contract</a>`
              : status === 'pending'
                ? `<a class="btn btn-ghost btn-sm" href="${projectHref}">Follow up</a>`
                : ''
          }
        </div>
      </div>
    </article>
  `;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}
