// ============================================
// home.js — landing page live data
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  loadHomeStats();
  loadHomeListings();
});

async function loadHomeStats() {
  try {
    const stats = await api('/stats');
    const eyebrow = document.getElementById('heroEyebrow');
    if (eyebrow) {
      eyebrow.textContent = `// ${stats.projects_this_month} projects posted this month`;
    }
    setText('statFreelancers', formatCount(stats.freelancers));
    setText('statOnTime', `${Math.round(stats.on_time_pct)}%`);
    setText('statPaid', formatMoney(stats.accepted_bid_total));
  } catch {
    setText('heroEyebrow', '// Marketplace live stats unavailable');
  }
}

async function loadHomeListings() {
  const grid = document.getElementById('homeListings');
  if (!grid) return;

  try {
    const projects = await api('/projects?status=open');
    const latest = projects[0];
    if (latest) {
      setText('matchBriefLabel', `Brief #${String(latest.id).padStart(4, '0')}`);
      setText('matchBriefTitle', latest.title);
      setText(
        'matchBriefMeta',
        `Budget: ${formatMoney(latest.budget_min)}–${formatMoney(latest.budget_max).replace('$', '')}${
          latest.skills?.[0] ? ` · ${latest.skills[0]}` : ''
        }`
      );
      setText('matchClientName', latest.client?.name || 'Client');
      setText(
        'matchClientMeta',
        latest.client
          ? `★ ${Number(latest.client.rating_avg || 0).toFixed(1)} · ${latest.category}`
          : latest.category
      );
    } else {
      setText('matchBriefTitle', 'No open briefs yet');
      setText('matchBriefMeta', 'Be the first to post a project');
      setText('matchClientName', 'Join FreelanceHub');
      setText('matchClientMeta', 'Clients & freelancers welcome');
    }

    if (!projects.length) {
      grid.innerHTML =
        '<p style="color:var(--slate);grid-column:1/-1;">No open projects yet. <a href="pages/register.html">Create an account</a> and post the first brief.</p>';
      return;
    }

    grid.innerHTML = projects.slice(0, 3).map(renderHomeCard).join('');
  } catch (err) {
    grid.innerHTML = `<p style="color:#B23A3A;grid-column:1/-1;">${escapeHtml(err.message)}</p>`;
  }
}

function renderHomeCard(project) {
  const tags = (project.skills || [])
    .slice(0, 2)
    .map((s) => `<span class="tag">${escapeHtml(s)}</span>`)
    .join('');
  const desc =
    project.description.length > 110
      ? `${project.description.slice(0, 110)}…`
      : project.description;
  return `
    <a class="card listing-card" href="pages/proposal-submission.html?id=${project.id}" style="display:block;color:inherit;">
      <div class="listing-top">
        <span class="tag">${escapeHtml(project.category)}</span>
        <span class="listing-budget">${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')}</span>
      </div>
      <h3>${escapeHtml(project.title)}</h3>
      <p>${escapeHtml(desc)}</p>
      <div class="listing-tags">${tags || `<span class="tag">${escapeHtml(project.category)}</span>`}</div>
      <div class="listing-foot">
        <span>${project.proposal_count || 0} proposals</span>
        <span>Posted ${timeAgo(project.created_at)}</span>
      </div>
    </a>
  `;
}

function setText(id, value) {
  const el = typeof id === 'string' ? document.getElementById(id) : id;
  if (el) el.textContent = value;
}

function formatCount(n) {
  const num = Number(n || 0);
  if (num >= 1000) return `${(num / 1000).toFixed(num >= 10000 ? 0 : 1).replace(/\.0$/, '')}k+`;
  return String(num);
}
