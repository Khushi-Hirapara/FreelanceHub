document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('talentSearch');
  const locationInput = document.getElementById('talentLocation');
  const categoryChips = document.querySelectorAll('.filter-category');
  const ratingChips = document.querySelectorAll('.filter-rating');
  const rateChips = document.querySelectorAll('.filter-rate');
  const grid = document.getElementById('talentGrid');
  const pager = document.getElementById('talentPager');
  const pageLabel = document.getElementById('talentPageLabel');
  const prevBtn = document.getElementById('talentPrev');
  const nextBtn = document.getElementById('talentNext');

  const user = typeof Auth !== 'undefined' ? Auth.getUser() : null;
  if (user && Auth.isLoggedIn()) fillSidebar(user);

  let activeCategory = 'all';
  let minRating = 0;
  let rateRange = 'all';
  let page = 1;
  let pages = 0;
  let searchTimer = null;

  categoryChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      categoryChips.forEach((item) => item.classList.remove('active'));
      chip.classList.add('active');
      activeCategory = chip.dataset.category || 'all';
      page = 1;
      loadTalent();
    });
  });

  ratingChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      ratingChips.forEach((item) => item.classList.remove('active'));
      chip.classList.add('active');
      minRating = Number(chip.dataset.rating || 0);
      page = 1;
      loadTalent();
    });
  });

  rateChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      rateChips.forEach((item) => item.classList.remove('active'));
      chip.classList.add('active');
      rateRange = chip.dataset.rate || 'all';
      page = 1;
      loadTalent();
    });
  });

  searchInput?.addEventListener('input', () => scheduleSearch());
  locationInput?.addEventListener('input', () => scheduleSearch());
  prevBtn?.addEventListener('click', () => {
    if (page <= 1) return;
    page -= 1;
    loadTalent();
  });
  nextBtn?.addEventListener('click', () => {
    if (page >= pages) return;
    page += 1;
    loadTalent();
  });

  loadTalent();

  function scheduleSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      page = 1;
      loadTalent();
    }, 300);
  }

  function rateBounds() {
    if (rateRange === '0-25') return { max_rate: 25 };
    if (rateRange === '25-50') return { min_rate: 25, max_rate: 50 };
    if (rateRange === '50-100') return { min_rate: 50, max_rate: 100 };
    if (rateRange === '100+') return { min_rate: 100 };
    return {};
  }

  async function loadTalent() {
    if (!grid) return;
    grid.innerHTML = '<p id="talentStatus" style="color:var(--slate); grid-column:1 / -1;">Loading freelancers…</p>';
    if (pager) pager.hidden = true;

    const params = new URLSearchParams({ role: 'freelancer', page: String(page), limit: '9' });
    const query = (searchInput?.value || '').trim();
    const location = (locationInput?.value || '').trim();
    if (query) params.set('q', query);
    if (location) params.set('location', location);
    if (activeCategory && activeCategory !== 'all') params.set('skill', activeCategory);
    if (minRating > 0) params.set('min_rating', String(minRating));
    const rates = rateBounds();
    if (rates.min_rate != null) params.set('min_rate', String(rates.min_rate));
    if (rates.max_rate != null) params.set('max_rate', String(rates.max_rate));

    try {
      const data = await api(`/users?${params.toString()}`);
      const items = data.items || [];
      pages = Number(data.pages || 0);
      page = Number(data.page || 1);
      if (!items.length) {
        grid.innerHTML = '<p id="talentStatus" style="color:var(--slate); grid-column:1 / -1;">No freelancers match your filters. Try clearing a filter or searching a different skill.</p>';
        if (pager) pager.hidden = true;
        return;
      }
      grid.innerHTML = items.map(renderCard).join('');
      bindHireButtons(grid);
      renderPager(data);
    } catch (err) {
      pages = 0;
      grid.innerHTML = `<p id="talentStatus" style="color:#B23A3A; grid-column:1 / -1;">${escapeHtml(err.message || 'Could not load freelancers.')}</p>`;
      if (pager) pager.hidden = true;
    }
  }

  function renderPager(data) {
    if (!pager || !pageLabel) return;
    const total = Number(data.total || 0);
    const current = Number(data.page || 1);
    const pageCount = Number(data.pages || 0);
    if (pageCount <= 1) {
      pager.hidden = true;
      return;
    }
    pager.hidden = false;
    pageLabel.textContent = `Page ${current} of ${pageCount} · ${total} freelancer${total === 1 ? '' : 's'}`;
    if (prevBtn) prevBtn.disabled = current <= 1;
    if (nextBtn) nextBtn.disabled = current >= pageCount;
  }
});

function renderCard(person) {
  const ratings = person.ratings || {};
  const average = Number(ratings.average || 0);
  const count = Number(ratings.count || 0);
  const skills = (person.skills || []).slice(0, 3).map((skill) => `<span class="tag">${escapeHtml(skill)}</span>`).join('');
  const rate = person.hourly_rate == null
    ? '<span class="talent-rate">Rate on request</span>'
    : `<span class="talent-rate">${formatMoney(person.hourly_rate)}/hr</span>`;
  const rating = count
    ? `<span class="talent-rating"><span class="stars">★</span> ${average.toFixed(1)} <span style="color:var(--slate-light)">(${count})</span></span>`
    : '<span class="talent-rating"><span class="stars">★</span> New</span>';
  const done = Number(person.projects_done || 0);
  const viewer = typeof Auth !== 'undefined' ? Auth.getUser() : null;
  const canHire = viewer && (viewer.role === 'client' || viewer.role === 'admin');

  return `
    <div class="card talent-card">
      <div class="talent-card-top">
        <div class="talent-avatar">${escapeHtml(initials(person.name))}</div>
        <div>
          <h3>${escapeHtml(person.name)}</h3>
          <div class="talent-title">${escapeHtml(person.title || 'Freelancer')}${done ? ` · ${done} project${done === 1 ? '' : 's'}` : ''}</div>
        </div>
      </div>
      <div class="talent-meta">
        ${rating}
        ${rate}
      </div>
      <div class="talent-tags">${skills || '<span class="tag">No skills listed</span>'}</div>
      <p class="talent-bio">${escapeHtml(trimBio(person.bio) || 'No bio yet.')}</p>
      <div class="talent-actions${canHire ? '' : ' single'}">
        <a href="freelancer-profile.html?id=${encodeURIComponent(person.id)}" class="btn btn-outline btn-sm">View Profile</a>
        ${
          canHire
            ? `<button type="button" class="btn btn-primary btn-sm" data-hire-open
                data-id="${person.id}"
                data-name="${escapeHtml(person.name)}"
                data-title="${escapeHtml(person.title || 'Freelancer')}"
                data-skills="${escapeHtml((person.skills || []).join(','))}">Hire</button>`
            : ''
        }
      </div>
    </div>
  `;
}

function trimBio(bio) {
  const text = String(bio || '').trim();
  if (text.length <= 160) return text;
  return `${text.slice(0, 157)}…`;
}

function fillSidebar(user) {
  const avatar = document.querySelector('.sidebar-profile .avatar');
  const name = document.querySelector('.sidebar-profile h4');
  const meta = document.querySelector('.sidebar-profile span');
  if (avatar) avatar.textContent = initials(user.name);
  if (name) name.textContent = user.name;
  if (meta) {
    meta.textContent =
      user.role === 'freelancer' ? 'Freelancer' : user.role === 'admin' ? 'Admin' : 'Client';
  }
}

function bindHireButtons(root) {
  root?.querySelectorAll('[data-hire-open]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (typeof openHireFlow !== 'function') {
        showToast('Hire flow is unavailable. Refresh the page.', 'error');
        return;
      }
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
}
