// ============================================
// profile.js — load & save profile via API
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  const user = requireAuth();
  if (!user) return;

  const tabs = document.querySelectorAll('.profile-tab');
  const panels = document.querySelectorAll('.tab-panel');

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      tabs.forEach((t) => t.classList.remove('active'));
      panels.forEach((p) => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
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
    document.querySelector('.avatar-lg')?.replaceChildren(document.createTextNode(initials(profile.name)));
    const nameEl = document.querySelector('.profile-card h2');
    if (nameEl) nameEl.textContent = profile.name;

    const roleTag = document.querySelector('.role-tag');
    if (roleTag) {
      roleTag.textContent = `${profile.role === 'freelancer' ? 'Freelancer' : 'Client'}${profile.title ? ` · ${profile.title}` : ''}`;
    }

    const rating = document.querySelector('.profile-rating');
    if (rating) {
      rating.innerHTML = `<span class="stars">★★★★★</span> ${Number(profile.rating_avg || 0).toFixed(1)} (${profile.rating_count || 0} reviews)`;
    }

    const miniVals = document.querySelectorAll('.profile-stats-mini .val');
    if (miniVals[0]) miniVals[0].textContent = String(profile.projects_done || 0);
    if (miniVals[1]) miniVals[1].textContent = `${Math.round(profile.on_time_pct || 100)}%`;

    const fullName = document.getElementById('fullName');
    const email = document.getElementById('email');
    const location = document.getElementById('location');
    const hourlyRate = document.getElementById('hourlyRate');
    const bio = document.getElementById('bio');

    if (fullName) fullName.value = profile.name || '';
    if (email) {
      email.value = profile.email || '';
      email.disabled = true;
    }
    if (location) location.value = profile.location || '';
    if (hourlyRate) hourlyRate.value = profile.hourly_rate ?? '';
    if (bio) bio.value = profile.bio || '';

    skillWrap?.querySelectorAll('.skill-chip').forEach((c) => c.remove());
    (profile.skills || []).forEach(addSkillChip);
    bindSkillRemove();
  }

  loadProfile();

  async function loadProfile() {
    try {
      const profile = await api('/users/me');
      Auth.setSession(Auth.getToken(), profile);
      fillProfile(profile);
    } catch (err) {
      showToast(err.message || 'Could not load profile.', 'error');
    }
  }

  const basicForm = document.querySelector('#tab-basic form');
  basicForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const updated = await api('/users/me', {
        method: 'PUT',
        body: JSON.stringify({
          name: document.getElementById('fullName').value.trim(),
          location: document.getElementById('location').value.trim() || null,
          hourly_rate: Number(document.getElementById('hourlyRate').value) || null,
        }),
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
