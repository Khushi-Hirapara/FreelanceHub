// ============================================
// project.js — Post project + submit proposal
// ============================================

let skills = [];

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('projectForm');
  if (!form) return;

  requireAuth(['client', 'admin']);

  const categoryBtns = document.querySelectorAll('.category-btn');
  const titleInput = document.getElementById('title');
  const descInput = document.getElementById('description');
  const budgetMin = document.getElementById('budgetMin');
  const budgetMax = document.getElementById('budgetMax');
  const skillInput = document.getElementById('skillInput');
  const skillWrap = document.getElementById('skillWrap');
  let hireFreelancerId = null;

  categoryBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      categoryBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      updatePreview();
    });
  });

  [titleInput, descInput, budgetMin, budgetMax].forEach((el) => {
    el?.addEventListener('input', updatePreview);
  });

  skillInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && skillInput.value.trim()) {
      e.preventDefault();
      addSkill(skillInput.value.trim());
      skillInput.value = '';
    }
  });

  const generateBtn = document.getElementById('generateWithAi');
  const aiRough = document.getElementById('aiRoughDescription');
  const aiHint = document.getElementById('aiHint');

  generateBtn?.addEventListener('click', async () => {
    const rough = (aiRough?.value || descInput?.value || '').trim();
    if (rough.length < 10) {
      showToast('Add a rough description (at least 10 characters) before generating.', 'error');
      if (aiHint) aiHint.textContent = 'Describe what you need in a sentence or two.';
      return;
    }

    generateBtn.disabled = true;
    const previousLabel = generateBtn.textContent;
    generateBtn.textContent = 'Generating…';
    if (aiHint) aiHint.textContent = 'Working on a structured brief…';

    try {
      const brief = await api('/ai/project-brief', {
        method: 'POST',
        body: JSON.stringify({ description: rough }),
      });
      applyAiBrief(brief);
      if (aiHint) aiHint.textContent = 'Brief filled in. Edit anything you want, then post when ready.';
      showToast('AI brief ready — review before posting.');
    } catch (err) {
      const message = err.message || 'Could not generate a brief right now.';
      if (aiHint) aiHint.textContent = message;
      showToast(message, 'error');
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = previousLabel || '✨ Generate with AI';
    }
  });

  function applyAiBrief(brief) {
    if (!brief) return;
    if (titleInput) titleInput.value = brief.title || '';
    if (descInput) descInput.value = brief.description || '';
    if (budgetMin) budgetMin.value = brief.budget_min ?? '';
    if (budgetMax) budgetMax.value = brief.budget_max ?? '';

    const experience = document.getElementById('experience');
    if (experience && brief.experience_level) {
      const known = Array.from(experience.options).some(
        (option) => option.value === brief.experience_level || option.textContent === brief.experience_level
      );
      if (!known) {
        const option = document.createElement('option');
        option.value = brief.experience_level;
        option.textContent = brief.experience_level;
        experience.appendChild(option);
      }
      experience.value = brief.experience_level;
    }

    const duration = document.getElementById('estimatedDuration');
    if (duration) duration.value = brief.estimated_duration || '';

    categoryBtns.forEach((btn) => btn.classList.remove('active'));
    const match = Array.from(categoryBtns).find(
      (btn) => (btn.dataset.cat || '').toLowerCase() === String(brief.category || '').toLowerCase()
    );
    if (match) match.classList.add('active');
    else if (categoryBtns[0]) categoryBtns[0].classList.add('active');

    skills = [...(brief.skills || [])];
    renderSkills();
    updatePreview();
  }

  function addSkill(skill) {
    if (skills.includes(skill)) return;
    skills.push(skill);
    renderSkills();
    updatePreview();
  }

  function removeSkill(skill) {
    skills = skills.filter((s) => s !== skill);
    renderSkills();
    updatePreview();
  }

  function renderSkills() {
    document.querySelectorAll('.skill-chip').forEach((chip) => chip.remove());
    skills.forEach((skill) => {
      const chip = document.createElement('span');
      chip.className = 'skill-chip';
      chip.innerHTML = `${escapeHtml(skill)} <button type="button" data-skill="${escapeHtml(skill)}">&times;</button>`;
      skillWrap.insertBefore(chip, skillInput);
    });
    skillWrap.querySelectorAll('.skill-chip button').forEach((btn) => {
      btn.addEventListener('click', () => removeSkill(btn.dataset.skill));
    });
  }

  function updatePreview() {
    const activeCat = document.querySelector('.category-btn.active')?.dataset.cat || 'Web Dev';
    document.getElementById('previewCat').textContent = activeCat;
    document.getElementById('previewTitle').textContent = titleInput.value || 'Your project title appears here';
    document.getElementById('previewDesc').textContent =
      descInput.value ||
      "Your description will show up here as you type, so freelancers see exactly what you'll publish.";

    const min = budgetMin.value || '0';
    const max = budgetMax.value || '0';
    document.getElementById('previewBudget').textContent = `$${min}–${max}`;

    const previewTags = document.getElementById('previewTags');
    previewTags.innerHTML = '';
    skills.forEach((skill) => {
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = skill;
      previewTags.appendChild(tag);
    });
  }

  const editId = Number(new URLSearchParams(window.location.search).get('edit'));
  let editingId = null;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const payload = {
      title: titleInput.value.trim(),
      category: document.querySelector('.category-btn.active')?.dataset.cat,
      description: descInput.value.trim(),
      skills,
      budget_min: Number(budgetMin.value),
      budget_max: Number(budgetMax.value),
      deadline: document.getElementById('deadline').value || null,
      experience_level: document.getElementById('experience').value || null,
    };

    if (payload.title.length < 5) {
      showToast('Title must be at least 5 characters.', 'error');
      return;
    }
    if (!payload.category) {
      showToast('Choose a category.', 'error');
      return;
    }
    if (payload.description.length < 20) {
      showToast('Description must be at least 20 characters.', 'error');
      return;
    }
    if (!payload.budget_min || !payload.budget_max || payload.budget_min <= 0 || payload.budget_max <= 0) {
      showToast('Enter a budget greater than zero.', 'error');
      return;
    }
    if (payload.budget_min > payload.budget_max) {
      showToast('Minimum budget cannot exceed maximum.', 'error');
      return;
    }

    const submitBtn = document.getElementById('submitProject');
    if (submitBtn) submitBtn.disabled = true;
    try {
      if (editingId) {
        await api(`/projects/${editingId}`, { method: 'PUT', body: JSON.stringify(payload) });
        showToast('Project updated.');
        window.location.href = `project-detail.html?id=${editingId}`;
        return;
      }
      const created = await api('/projects', { method: 'POST', body: JSON.stringify(payload) });
      showToast('Project posted successfully!');
      if (hireFreelancerId) {
        sessionStorage.setItem('fh_hire_freelancer_id', String(hireFreelancerId));
        sessionStorage.setItem('fh_hire_project_id', String(created.id));
      }
      window.location.href = `project-detail.html?id=${created.id}`;
    } catch (err) {
      if (submitBtn) submitBtn.disabled = false;
      showToast(err.message || 'Something went wrong saving your project.', 'error');
    }
  });

  if (editId) {
    loadProjectForEdit(editId);
  } else {
    updatePreview();
    setupHireTarget();
  }

  async function setupHireTarget() {
    const params = new URLSearchParams(window.location.search);
    const hireId = Number(params.get('hire') || 0);
    const banner = document.getElementById('hireBanner');
    if (!hireId || !banner) return;

    hireFreelancerId = hireId;
    banner.hidden = false;

    try {
      const person = await api(`/users/${hireId}`);
      const name = person.name || 'this freelancer';
      setText('hireBannerTitle', `Hiring ${name}`);
      setText(
        'hireBannerText',
        `Post your brief for ${name}. After publishing, you can message them from their profile or the project page.`
      );
      setText('postTitle', `Hire ${name}`);
      setText('postSubtitle', 'Describe the work, budget, and timeline — then publish your brief.');

      if (Array.isArray(person.skills) && person.skills.length && !skills.length) {
        skills = person.skills.slice(0, 8).map((s) => String(s).trim()).filter(Boolean);
        renderSkills();
        updatePreview();
      }
    } catch {
      setText('hireBannerTitle', 'Hiring a freelancer');
      setText(
        'hireBannerText',
        'Post your brief, then message the freelancer once the project is live.'
      );
    }
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  async function loadProjectForEdit(projectId) {
    const notice = document.getElementById('formNotice');
    const submitBtn = document.getElementById('submitProject');
    try {
      const project = await api(`/projects/${projectId}`);
      const user = Auth.getUser();
      const isAdmin = user?.role === 'admin';
      const isOwner = Number(project.client_id) === Number(user?.id);
      if (!isOwner && !isAdmin) {
        if (notice) notice.textContent = 'Only the project owner can edit this brief.';
        form.querySelectorAll('input, textarea, select, button').forEach((el) => {
          el.disabled = true;
        });
        return;
      }
      const locked = project.status === 'completed' || project.status === 'cancelled';
      if (locked && !isAdmin) {
        if (notice) notice.textContent = 'Completed or cancelled projects cannot be edited.';
        form.querySelectorAll('input, textarea, select, button').forEach((el) => {
          el.disabled = true;
        });
        return;
      }

      editingId = project.id;
      document.title = 'Edit Project — FreelanceHub';
      document.getElementById('postTitle').textContent = 'Edit project';
      document.getElementById('postSubtitle').textContent = 'Update the brief. Freelancers will see the saved version.';
      if (submitBtn) submitBtn.textContent = 'Save changes';

      titleInput.value = project.title || '';
      descInput.value = project.description || '';
      budgetMin.value = project.budget_min ?? '';
      budgetMax.value = project.budget_max ?? '';
      const deadline = document.getElementById('deadline');
      if (deadline) {
        deadline.required = false;
        deadline.value = project.deadline || '';
      }
      const experience = document.getElementById('experience');
      if (experience && project.experience_level) {
        const known = Array.from(experience.options).some((option) => option.value === project.experience_level);
        if (!known) {
          const option = document.createElement('option');
          option.value = project.experience_level;
          option.textContent = project.experience_level;
          experience.appendChild(option);
        }
        experience.value = project.experience_level;
      }

      categoryBtns.forEach((btn) => btn.classList.remove('active'));
      const match = Array.from(categoryBtns).find(
        (btn) => (btn.dataset.cat || '').toLowerCase() === String(project.category || '').toLowerCase()
      );
      if (match) match.classList.add('active');

      skills = [...(project.skills || [])];
      renderSkills();
      updatePreview();
    } catch (err) {
      if (notice) notice.textContent = err.message || 'Could not load this project.';
      if (submitBtn) submitBtn.disabled = true;
      showToast(err.message || 'Could not load this project.', 'error');
    }
  }
});

// ---------- Proposal submission ----------
document.addEventListener('DOMContentLoaded', () => {
  const proposalForm = document.getElementById('proposalForm');
  if (!proposalForm) return;

  requireAuth(['freelancer']);

  const params = new URLSearchParams(window.location.search);
  const projectId = Number(params.get('project_id') || params.get('id'));
  const coverLetter = document.getElementById('coverLetter');
  const charCount = document.getElementById('charCount');
  const milestoneList = document.getElementById('milestoneList');
  const addMilestoneBtn = document.getElementById('addMilestone');

  if (!projectId) {
    showToast('Open a project from Find Work to submit a proposal.', 'error');
  } else {
    loadProjectBrief(projectId);
  }

  coverLetter?.addEventListener('input', () => {
    charCount.textContent = coverLetter.value.length;
  });

  function bindRemoveButtons() {
    milestoneList.querySelectorAll('.remove-milestone').forEach((btn) => {
      btn.onclick = () => {
        if (milestoneList.children.length > 1) {
          btn.closest('.milestone-row').remove();
        } else {
          showToast('At least one milestone row is required, clear it instead.', 'error');
        }
      };
    });
  }
  bindRemoveButtons();

  addMilestoneBtn?.addEventListener('click', () => {
    const row = document.createElement('div');
    row.className = 'milestone-row';
    row.innerHTML = `
      <input type="text" placeholder="Milestone description" class="milestone-desc">
      <input type="number" placeholder="$" class="milestone-amount">
      <button type="button" class="remove-milestone">&times;</button>
    `;
    milestoneList.appendChild(row);
    bindRemoveButtons();
  });

  proposalForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    if (!projectId) {
      showToast('Missing project id. Browse projects and click Submit Proposal.', 'error');
      return;
    }

    const bidAmount = Number(document.getElementById('bidAmount').value);
    const duration = document.getElementById('duration').value;
    const letter = coverLetter.value.trim();

    if (!bidAmount || bidAmount <= 0) {
      showToast('Please enter a valid bid amount.', 'error');
      return;
    }
    if (letter.length < 30) {
      showToast('Cover letter should be a bit more detailed (30+ characters).', 'error');
      return;
    }

    const milestones = Array.from(milestoneList.querySelectorAll('.milestone-row'))
      .map((row) => ({
        description: row.querySelector('.milestone-desc').value.trim(),
        amount: Number(row.querySelector('.milestone-amount').value) || 0,
      }))
      .filter((m) => m.description);

    const payload = {
      project_id: projectId,
      bid_amount: bidAmount,
      estimated_duration: duration,
      cover_letter: letter,
      milestones,
    };

    try {
      await api('/proposals', { method: 'POST', body: JSON.stringify(payload) });
      showToast('Proposal submitted successfully!');
      setTimeout(() => {
        window.location.href = 'freelancer-dashboard.html';
      }, 800);
    } catch (err) {
      showToast(err.message || 'Something went wrong submitting your proposal.', 'error');
    }
  });
});

async function loadProjectBrief(projectId) {
  try {
    const project = await api(`/projects/${projectId}`);
    const card = document.querySelector('.brief-card');
    if (!card) return;

    card.querySelector('.tag').textContent = project.category;
    card.querySelector('h2').textContent = project.title;
    card.querySelector('.brief-budget').textContent =
      `Budget: ${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')}`;
    card.querySelector('.desc').textContent = project.description;

    const tags = card.querySelector('.brief-tags');
    tags.innerHTML = (project.skills || [])
      .map((s) => `<span class="tag">${escapeHtml(s)}</span>`)
      .join('');

    const rows = card.querySelectorAll('.brief-meta-row');
    if (rows[0]) rows[0].children[1].textContent = timeAgo(project.created_at);
    if (rows[1]) rows[1].children[1].textContent = String(project.proposal_count || 0);
    if (rows[2]) {
      rows[2].children[1].textContent = project.deadline
        ? new Date(project.deadline).toLocaleDateString()
        : 'Flexible';
    }
    if (rows[3]) rows[3].children[1].textContent = project.experience_level || 'Any';

    if (project.client) {
      const clientBox = card.querySelector('.client-box');
      clientBox.querySelector('.avatar-sm').textContent = initials(project.client.name);
      clientBox.querySelector('h5').textContent = project.client.name;
      clientBox.querySelector('span').textContent =
        `Client · ${project.client.projects_done || 0} projects posted`;
    }

    const budgetHint = document.getElementById('budgetHint');
    if (budgetHint) {
      budgetHint.textContent = `Client's budget: ${formatMoney(project.budget_min)}–${formatMoney(project.budget_max).replace('$', '')}`;
    }
  } catch (err) {
    showToast(err.message || 'Could not load project.', 'error');
  }
}
