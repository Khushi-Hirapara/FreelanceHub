document.addEventListener('DOMContentLoaded', () => {
  const userId = Number(new URLSearchParams(window.location.search).get('id'));
  if (!userId) {
    document.getElementById('profileBody').innerHTML =
      '<p>Open a profile from Find Talent. This page needs a user id.</p>';
    return;
  }
  loadPublicProfile(userId);
});

let editingItemId = null;
let portfolioById = new Map();

async function loadPublicProfile(userId) {
  const body = document.getElementById('profileBody');
  const hero = document.getElementById('profileHero');
  body.innerHTML = '<p style="color:var(--slate);">Loading profile…</p>';
  try {
    const [profile, reviews, portfolio] = await Promise.all([
      api(`/users/${userId}`),
      api(`/users/${userId}/reviews`),
      api(`/users/${userId}/portfolio`),
    ]);
    const viewer = Auth.isLoggedIn() ? Auth.getUser() : null;
    renderHero(profile, viewer, hero);
    renderBody(profile, reviews, portfolio, viewer, body);
  } catch (err) {
    body.innerHTML = `<p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load profile.')}</p>`;
    hero.innerHTML = '';
  }
}

function renderHero(profile, viewer, hero) {
  document.title = `${profile.name} — FreelanceHub`;
  const avg = Number(profile.rating_avg || 0);
  const reviewCount = Number(profile.rating_count || 0);
  const done = Number(profile.projects_done || 0);
  const rate = profile.hourly_rate == null
    ? ''
    : `<span class="rate">${formatMoney(profile.hourly_rate)}/hr</span>`;
  const place = profile.location ? `<span>${escapeHtml(profile.location)}</span>` : '';
  const isOwner = viewer && Number(viewer.id) === Number(profile.id);
  const isFreelancer = profile.role === 'freelancer';

  let actions = '';
  if (isOwner) {
    actions = '<a href="profile.html" class="btn btn-outline">Edit Profile</a>';
  } else if (isFreelancer) {
    actions = `
      <button type="button" class="btn btn-primary" id="hireFreelancer">Hire</button>
      <button type="button" class="btn btn-outline" id="messageFreelancer">Message</button>
    `;
  }

  hero.innerHTML = `
    <div class="profile-hero">
      <div class="profile-hero-top">
        <div class="avatar-lg">${escapeHtml(initials(profile.name))}</div>
        <div style="flex:1; min-width:200px;">
          <h1>${escapeHtml(profile.name)}</h1>
          <div class="title">${escapeHtml(profile.title || (profile.role === 'client' ? 'Client' : 'Freelancer'))}</div>
          <div class="profile-meta-row">
            <span><span class="stars">${starString(avg)}</span> ${avg.toFixed(1)} (${reviewCount} reviews)</span>
            <span>${done} completed project${done === 1 ? '' : 's'}</span>
            ${rate}
            ${place}
          </div>
        </div>
        <div class="profile-actions">${actions}</div>
      </div>
      <div id="messageBox" class="message-box" hidden></div>
    </div>
  `;

  document.getElementById('hireFreelancer')?.addEventListener('click', () => {
    if (!viewer) {
      window.location.href = 'login.html?next=freelancer-profile.html';
      return;
    }
    if (typeof openHireFlow === 'function') {
      openHireFlow(profile);
    } else {
      showToast('Hire flow is unavailable. Refresh the page.', 'error');
    }
  });
  document.getElementById('messageFreelancer')?.addEventListener('click', () => openMessageBox(profile, viewer));
}

function hireAction(viewer, freelancerId) {
  // Kept for compatibility; Hire now opens openHireFlow().
  const id = Number(freelancerId || 0);
  const hireQuery = id ? `?hire=${encodeURIComponent(id)}` : '';
  if (!viewer) return { href: `login.html?next=project-posting.html`, label: 'Hire' };
  if (viewer.role === 'client' || viewer.role === 'admin') {
    return { href: `project-posting.html${hireQuery}`, label: 'Hire' };
  }
  return { href: 'freelancer-dashboard.html', label: 'View Projects' };
}

function openMessageBox(profile, viewer) {
  const box = document.getElementById('messageBox');
  if (!box) return;
  if (!viewer) {
    window.location.href = 'login.html';
    return;
  }
  if (Number(viewer.id) === Number(profile.id)) return;
  box.hidden = false;
  box.innerHTML = `
    <form class="profile-form" id="messageForm">
      <div class="form-group">
        <label for="messageText">Message ${escapeHtml(profile.name)}</label>
        <textarea id="messageText" rows="3" maxlength="5000" required placeholder="Introduce the work you need…"></textarea>
      </div>
      <div class="profile-form-actions">
        <button type="submit" class="btn btn-primary btn-sm">Send</button>
        <button type="button" class="btn btn-ghost btn-sm" id="cancelMessage">Cancel</button>
      </div>
      <p id="messageError" style="color:#B23A3A; margin-top:8px;"></p>
    </form>
  `;
  document.getElementById('cancelMessage')?.addEventListener('click', () => {
    box.hidden = true;
    box.innerHTML = '';
  });
  document.getElementById('messageForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = document.getElementById('messageText').value.trim();
    const error = document.getElementById('messageError');
    if (!text) return;
    try {
      await api('/messages', {
        method: 'POST',
        body: JSON.stringify({ receiver_id: profile.id, message_text: text }),
      });
      window.location.href = 'messaging.html';
    } catch (err) {
      if (error) error.textContent = err.message || 'Could not send message.';
    }
  });
}

function renderBody(profile, reviews, portfolio, viewer, body) {
  const skills = (profile.skills || []).map((skill) => `<span class="tag">${escapeHtml(skill)}</span>`).join('');
  const isOwner = viewer && Number(viewer.id) === Number(profile.id);
  const avg = Number(profile.rating_avg || 0);
  const reviewHtml = reviews.length
    ? reviews.map(renderReview).join('')
    : '<p>No reviews yet.</p>';

  body.innerHTML = `
    <div class="card profile-section">
      <h2>About</h2>
      <p>${escapeHtml(profile.bio || 'No bio yet.')}</p>
    </div>
    <div class="card profile-section">
      <h2>Skills</h2>
      <div class="skills-wrap">${skills || '<span class="tag">No skills listed</span>'}</div>
    </div>
    <div class="card profile-section">
      <h2>Portfolio</h2>
      <div class="portfolio-grid" id="portfolioGrid">${renderPortfolio(portfolio, isOwner)}</div>
      ${isOwner ? portfolioForm() : ''}
    </div>
    <div class="card profile-section">
      <h2>Reviews</h2>
      <p style="margin-bottom:12px;"><span class="stars">${starString(avg)}</span> ${avg.toFixed(1)} average · ${reviewCountLabel(reviews.length)}</p>
      ${reviewHtml}
    </div>
  `;

  if (isOwner) bindPortfolioForm(profile.id);
}

function renderReview(review) {
  const when = review.created_at ? new Date(review.created_at).toLocaleDateString() : '';
  const project = review.project_title ? `Project: ${review.project_title}` : 'Completed contract';
  return `
    <div class="review-item">
      <div class="review-top">
        <h4>${escapeHtml(review.reviewer?.name || 'Member')}</h4>
        <span class="review-stars">${starString(review.rating)} ${review.rating}.0</span>
      </div>
      <p>${escapeHtml(review.comment)}</p>
      <div class="review-meta">${escapeHtml(project)} · ${escapeHtml(when)}</div>
    </div>
  `;
}

function renderPortfolio(items, isOwner) {
  portfolioById = new Map(items.map((item) => [item.id, item]));
  if (!items.length) {
    return '<p style="grid-column:1 / -1; color:var(--slate);">No portfolio items yet.</p>';
  }
  return items.map((item) => {
    const image = safeHttpUrl(item.image_url);
    const link = safeHttpUrl(item.project_url);
    const style = image ? ` style="background-image:url('${escapeHtml(image)}'); background-size:cover; background-position:center;"` : '';
    const overlay = `
      <div class="overlay">
        <strong>${escapeHtml(item.title)}</strong>
        ${item.description ? `<div>${escapeHtml(trimText(item.description, 90))}</div>` : ''}
      </div>
    `;
    const tile = link
      ? `<a class="portfolio-item" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer"${style}>${overlay}</a>`
      : `<div class="portfolio-item"${style}>${overlay}</div>`;
    const controls = isOwner
      ? `<div class="portfolio-actions">
          <button type="button" class="btn btn-outline btn-sm" data-edit="${item.id}">Edit</button>
          <button type="button" class="btn btn-ghost btn-sm" data-delete="${item.id}">Delete</button>
        </div>`
      : '';
    return `<div data-item="${item.id}">${tile}${controls}</div>`;
  }).join('');
}

function portfolioForm() {
  return `
    <form class="profile-form" id="portfolioForm">
      <h3 id="portfolioFormTitle" style="font-family:var(--font-display); font-size:1.05rem; margin-bottom:12px;">Add portfolio item</h3>
      <div class="form-group">
        <label for="portfolioTitle">Title</label>
        <input id="portfolioTitle" maxlength="200" required>
      </div>
      <div class="form-group">
        <label for="portfolioDescription">Description</label>
        <textarea id="portfolioDescription" rows="3" maxlength="4000"></textarea>
      </div>
      <div class="form-group">
        <label for="portfolioUrl">Project URL</label>
        <input id="portfolioUrl" type="url" placeholder="https://">
      </div>
      <div class="form-group">
        <label for="portfolioImage">Image URL</label>
        <input id="portfolioImage" type="url" placeholder="https://">
      </div>
      <div class="profile-form-actions">
        <button type="submit" class="btn btn-primary btn-sm" id="portfolioSubmit">Add item</button>
        <button type="button" class="btn btn-ghost btn-sm" id="portfolioCancel" hidden>Cancel</button>
      </div>
      <p id="portfolioError" style="color:#B23A3A; margin-top:8px;"></p>
    </form>
  `;
}

function bindPortfolioForm(userId) {
  const form = document.getElementById('portfolioForm');
  form?.addEventListener('submit', (event) => savePortfolioItem(event, userId));
  document.getElementById('portfolioCancel')?.addEventListener('click', resetPortfolioForm);
  document.querySelectorAll('[data-edit]').forEach((button) => {
    button.addEventListener('click', () => startEdit(Number(button.dataset.edit)));
  });
  document.querySelectorAll('[data-delete]').forEach((button) => {
    button.addEventListener('click', () => removePortfolioItem(userId, Number(button.dataset.delete)));
  });
}

function portfolioPayload() {
  return {
    title: document.getElementById('portfolioTitle').value.trim(),
    description: document.getElementById('portfolioDescription').value.trim(),
    project_url: document.getElementById('portfolioUrl').value.trim(),
    image_url: document.getElementById('portfolioImage').value.trim(),
  };
}

async function savePortfolioItem(event, userId) {
  event.preventDefault();
  const error = document.getElementById('portfolioError');
  if (error) error.textContent = '';
  const payload = portfolioPayload();
  try {
    if (editingItemId) {
      await api(`/users/me/portfolio/${editingItemId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
    } else {
      await api('/users/me/portfolio', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    }
    editingItemId = null;
    await loadPublicProfile(userId);
  } catch (err) {
    if (error) error.textContent = err.message || 'Could not save portfolio item.';
  }
}

function startEdit(itemId) {
  const item = portfolioById.get(itemId);
  if (!item) return;
  editingItemId = itemId;
  document.getElementById('portfolioTitle').value = item.title || '';
  document.getElementById('portfolioDescription').value = item.description || '';
  document.getElementById('portfolioUrl').value = item.project_url || '';
  document.getElementById('portfolioImage').value = item.image_url || '';
  document.getElementById('portfolioFormTitle').textContent = 'Edit portfolio item';
  document.getElementById('portfolioSubmit').textContent = 'Save changes';
  document.getElementById('portfolioCancel').hidden = false;
  document.getElementById('portfolioForm')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function resetPortfolioForm() {
  editingItemId = null;
  document.getElementById('portfolioForm')?.reset();
  document.getElementById('portfolioFormTitle').textContent = 'Add portfolio item';
  document.getElementById('portfolioSubmit').textContent = 'Add item';
  document.getElementById('portfolioCancel').hidden = true;
}

async function removePortfolioItem(userId, itemId) {
  if (!window.confirm('Delete this portfolio item?')) return;
  try {
    await api(`/users/me/portfolio/${itemId}`, { method: 'DELETE' });
    await loadPublicProfile(userId);
  } catch (err) {
    const error = document.getElementById('portfolioError');
    if (error) error.textContent = err.message || 'Could not delete portfolio item.';
  }
}

function reviewCountLabel(count) {
  return `${count} review${count === 1 ? '' : 's'}`;
}

function trimText(value, max) {
  const text = String(value || '').trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function safeHttpUrl(value) {
  const text = String(value || '').trim();
  if (!/^https?:\/\//i.test(text)) return '';
  return text;
}
