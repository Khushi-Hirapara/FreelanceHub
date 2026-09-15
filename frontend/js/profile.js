// ============================================
// profile.js — load & save profile via API
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;

  const role = user.role || 'client';
  applyRoleLayout(role);

  const tabs = Array.from(document.querySelectorAll('.profile-tab'));
  const panels = Array.from(document.querySelectorAll('.tab-panel'));

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      if (tab.hidden) return;
      tabs.forEach((t) => t.classList.remove('active'));
      panels.forEach((p) => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(`tab-${tab.dataset.tab}`)?.classList.add('active');
    });
  });

  const skillWrap = document.getElementById('profileSkillWrap');
  const skillInput = document.getElementById('profileSkillInput');

  if (skillInput) {
    skillInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && skillInput.value.trim()) {
        e.preventDefault();
        addSkillChip(skillInput.value.trim());
        skillInput.value = '';
      }
    });
  }

  function addSkillChip(skill) {
    const chip = document.createElement('span');
    chip.className = 'skill-chip';
    chip.innerHTML = `${escapeHtml(skill)} <button type="button">&times;</button>`;
    skillWrap.insertBefore(chip, skillInput);
    bindSkillRemove();
  }

  function bindSkillRemove() {
    skillWrap?.querySelectorAll('.skill-chip button').forEach((btn) => {
      btn.onclick = () => btn.closest('.skill-chip').remove();
    });
  }

  function collectSkills() {
    return Array.from(skillWrap?.querySelectorAll('.skill-chip') || [])
      .map((chip) => chip.childNodes[0].textContent.trim())
      .filter(Boolean);
  }

  function fillProfile(profile) {
    const avatar = document.getElementById('profileAvatar') || document.querySelector('.avatar-lg');
    if (avatar) avatar.textContent = initials(profile.name);

    const nameEl = document.getElementById('profileName') || document.querySelector('.profile-card h2');
    if (nameEl) nameEl.textContent = profile.name;

    const roleLabel =
      profile.role === 'freelancer' ? 'Freelancer' : profile.role === 'admin' ? 'Admin' : 'Client';
    const titleEl = document.getElementById('profileTitle') || document.querySelector('.role-tag');
    if (titleEl) {
      if (profile.role === 'freelancer' && profile.title) {
        titleEl.textContent = profile.title;
      } else if (profile.role === 'client' && profile.title) {
        titleEl.textContent = profile.title;
      } else {
        titleEl.textContent = roleLabel;
      }
    }

    const meta = document.getElementById('profileMeta') || document.querySelector('.profile-rating');
    if (meta) {
      if (profile.role === 'freelancer') {
        const avg = Number(profile.rating_avg || 0);
        const reviewCount = Number(profile.rating_count || 0);
        const place = profile.location ? `<span>${escapeHtml(profile.location)}</span>` : '';
        const rate =
          profile.hourly_rate == null
            ? ''
            : `<span class="rate">${formatMoney(profile.hourly_rate)}/hr</span>`;
        meta.innerHTML = `
          <span><span class="stars">${starString(avg)}</span> ${avg.toFixed(1)} (${reviewCount})</span>
          <span>${Number(profile.projects_done || 0)} jobs</span>
          ${rate}
          ${place}
        `;
      } else {
        const bits = [
          `<span>${escapeHtml(roleLabel)}</span>`,
          profile.location ? `<span>${escapeHtml(profile.location)}</span>` : '',
          profile.email ? `<span>${escapeHtml(profile.email)}</span>` : '',
        ].filter(Boolean);
        meta.innerHTML = bits.join('');
      }
    }

    if (profile.role === 'freelancer') {
      setText('statDone', String(profile.projects_done || 0));
      setText('statOnTime', `${Math.round(profile.on_time_pct || 100)}%`);
      setText(
        'statRate',
        profile.hourly_rate == null ? '—' : formatMoney(profile.hourly_rate)
      );
      setText('statReviews', String(profile.rating_count || 0));
    }

    const publicLink = document.getElementById('viewPublicProfile');
    if (publicLink && profile.role === 'freelancer') {
      publicLink.href = `freelancer-profile.html?id=${profile.id}`;
    }

    const fullName = document.getElementById('fullName');
    const email = document.getElementById('email');
    const titleInput = document.getElementById('title');
    const location = document.getElementById('location');
    const hourlyRate = document.getElementById('hourlyRate');
    const bio = document.getElementById('bio');

    if (fullName) fullName.value = profile.name || '';
    if (email) {
      email.value = profile.email || '';
      email.disabled = true;
    }
    if (titleInput) titleInput.value = profile.title || '';
    if (location) location.value = profile.location || '';
    if (hourlyRate) hourlyRate.value = profile.hourly_rate ?? '';
    if (bio) bio.value = profile.bio || '';

    skillWrap?.querySelectorAll('.skill-chip').forEach((c) => c.remove());
    if (profile.role === 'freelancer') {
      (profile.skills || []).forEach(addSkillChip);
      bindSkillRemove();
      loadPortfolioPreview(profile.id);
    }
  }

  async function loadPortfolioPreview(userId) {
    const grid = document.getElementById('portfolioGrid');
    if (!grid) return;
    try {
      const items = await api(`/users/${userId}/portfolio`);
      if (!items.length) {
        grid.innerHTML = `<div class="portfolio-add">+</div>`;
        return;
      }
      grid.innerHTML =
        items
          .slice(0, 6)
          .map(
            (item) => `
          <div class="portfolio-item">
            <div class="overlay">${escapeHtml(item.title || 'Portfolio item')}</div>
          </div>
        `
          )
          .join('') + `<a class="portfolio-add" href="freelancer-profile.html?id=${userId}" title="Manage on public profile">+</a>`;
    } catch {
      // keep default
    }
  }

  loadProfile();

  async function loadProfile() {
    try {
      const profile = await api('/users/me');
      Auth.setSession(Auth.getToken(), profile);
      applyRoleLayout(profile.role);
      fillProfile(profile);
      if (profile.role === 'freelancer') loadReviews(profile.id);
    } catch (err) {
      showToast(err.message || 'Could not load profile.', 'error');
    }
  }

  const basicForm = document.querySelector('#tab-basic form');
  basicForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const payload = {
        name: document.getElementById('fullName').value.trim(),
        location: document.getElementById('location').value.trim() || null,
      };

      const titleInput = document.getElementById('title');
      const titleGroup = document.getElementById('titleGroup');
      if (titleInput && titleGroup && !titleGroup.hidden) {
        payload.title = titleInput.value.trim() || null;
      }

      const hourlyGroup = document.getElementById('hourlyRateGroup');
      const hourlyRate = document.getElementById('hourlyRate');
      if (hourlyGroup && !hourlyGroup.hidden && hourlyRate) {
        payload.hourly_rate = Number(hourlyRate.value) || null;
      }

      const updated = await api('/users/me', {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      Auth.setSession(Auth.getToken(), updated);
      fillProfile(updated);
      showToast('Profile updated successfully!');
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  const skillsForm = document.querySelector('#tab-skills form');
  skillsForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const updated = await api('/users/me', {
        method: 'PUT',
        body: JSON.stringify({
          bio: document.getElementById('bio').value.trim() || null,
          skills: collectSkills(),
        }),
      });
      Auth.setSession(Auth.getToken(), updated);
      fillProfile(updated);
      showToast('Skills & bio saved!');
      if (updated.role === 'freelancer') loadReviews(updated.id);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  const securityForm = document.querySelector('#tab-security form');
  securityForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const currentPassword = document.getElementById('currentPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmNewPassword = document.getElementById('confirmNewPassword').value;

    if (newPassword.length < 8) {
      showToast('New password must be at least 8 characters.', 'error');
      return;
    }
    if (newPassword !== confirmNewPassword) {
      showToast('New passwords do not match.', 'error');
      return;
    }

    try {
      await api('/users/me/password', {
        method: 'PUT',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      securityForm.reset();
      showToast('Password updated!');
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
});

function applyRoleLayout(role) {
  const normalized = role || 'client';

  document.querySelectorAll('[data-roles]').forEach((el) => {
    const allowed = (el.dataset.roles || '')
      .split(',')
      .map((r) => r.trim())
      .filter(Boolean);
    el.hidden = allowed.length > 0 && !allowed.includes(normalized);
  });

  const basicLead = document.getElementById('basicLead');
  const titleLabel = document.getElementById('titleLabel');
  const titleInput = document.getElementById('title');

  if (normalized === 'freelancer') {
    if (basicLead) basicLead.textContent = 'This is what clients see on your public profile.';
    if (titleLabel) titleLabel.textContent = 'Professional title';
    if (titleInput) titleInput.placeholder = 'e.g. Full-stack developer';
  } else if (normalized === 'client') {
    if (basicLead) basicLead.textContent = 'Your client account details used across projects and contracts.';
    if (titleLabel) titleLabel.textContent = 'Company or role';
    if (titleInput) titleInput.placeholder = 'e.g. Product manager at Acme';
  } else {
    if (basicLead) basicLead.textContent = 'Your admin account details for the FreelanceHub console.';
  }

  // Ensure a visible tab is active
  const tabs = Array.from(document.querySelectorAll('.profile-tab'));
  const panels = Array.from(document.querySelectorAll('.tab-panel'));
  const activeVisible = tabs.find((t) => t.classList.contains('active') && !t.hidden);
  if (!activeVisible) {
    const first = tabs.find((t) => !t.hidden);
    tabs.forEach((t) => t.classList.remove('active'));
    panels.forEach((p) => p.classList.remove('active'));
    if (first) {
      first.classList.add('active');
      document.getElementById(`tab-${first.dataset.tab}`)?.classList.add('active');
    }
  }
}

async function loadReviews(userId) {
  const list = document.getElementById('reviewList');
  const heading = document.getElementById('reviewCount');
  if (!list) return;
  list.innerHTML = '<p style="color:var(--slate);">Loading reviews…</p>';
  try {
    const reviews = await api(`/users/${userId}/reviews`);
    if (heading) heading.textContent = `(${reviews.length})`;
    if (!reviews.length) {
      list.innerHTML = '<p style="color:var(--slate);">No reviews yet. Reviews appear after a contract is completed.</p>';
      return;
    }
    list.innerHTML = reviews.map(renderReviewItem).join('');
  } catch (err) {
    list.innerHTML = `<p style="color:#B23A3A;">${escapeHtml(err.message || 'Could not load reviews.')}</p>`;
  }
}

function renderReviewItem(review) {
  const when = review.created_at ? new Date(review.created_at).toLocaleDateString() : '';
  const project = review.project_title ? `Project: ${review.project_title}` : 'Completed contract';
  return `
    <article class="review-item">
      <div class="review-top">
        <h4>${escapeHtml(review.reviewer?.name || 'Member')}</h4>
        <span class="review-stars">${starString(review.rating)} ${review.rating}.0</span>
      </div>
      <p>${escapeHtml(review.comment)}</p>
      <div class="review-meta">${escapeHtml(project)} · ${escapeHtml(when)}</div>
    </article>
  `;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}
