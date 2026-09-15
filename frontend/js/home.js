// ============================================
// home.js — landing page live data + motion
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  wireLandingNav();
  wireLandingReveal();
  loadHomeStats();
  loadHomeListings();
});

function wireLandingNav() {
  const nav = document.getElementById('landNav');
  if (!nav) return;
  const onScroll = () => {
    nav.classList.toggle('is-solid', window.scrollY > 40);
  };
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
}

function wireLandingReveal() {
  const nodes = document.querySelectorAll('.land-reveal');
  if (!nodes.length) return;
  if (!('IntersectionObserver' in window)) {
    nodes.forEach((el) => el.classList.add('is-in'));
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.16, rootMargin: '0px 0px -40px 0px' }
  );
  nodes.forEach((el) => observer.observe(el));
}

async function loadHomeStats() {
  try {
    const stats = await api('/stats');
    const eyebrow = document.getElementById('heroEyebrow');
    if (eyebrow) {
      eyebrow.textContent = `${stats.projects_this_month} projects posted this month — live from the board.`;
    }
    setText('statFreelancers', formatCount(stats.freelancers));
    setText('statOnTime', `${Math.round(stats.on_time_pct)}%`);
    setText('statPaid', formatMoney(stats.accepted_bid_total));
  } catch {
    setText('heroEyebrow', 'Marketplace stats will appear when the API is online.');
  }
}

async function loadHomeListings() {
  const grid = document.getElementById('homeListings');
  if (!grid) return;

  try {
    const projects = await api('/projects?status=open');
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
  const loggedIn = typeof Auth !== 'undefined' && Auth.isLoggedIn() && Auth.getUser();
  const href = loggedIn
    ? `pages/project-detail.html?id=${project.id}`
    : 'pages/login.html?next=project-detail.html';

  return `
    <a class="land-listing" href="${href}">
      <div class="land-listing-top">
        <span class="tag">${escapeHtml(project.category)}</span>
        <span class="budget">${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')}</span>
      </div>
      <h3>${escapeHtml(project.title)}</h3>
      <p>${escapeHtml(desc)}</p>
      <div class="listing-tags" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;">
        ${tags || `<span class="tag">${escapeHtml(project.category)}</span>`}
      </div>
      <div class="land-listing-foot">
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
