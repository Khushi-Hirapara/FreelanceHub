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

    if (!payload.title || !payload.description || !payload.budget_min || !payload.budget_max) {
      showToast('Please fill in all required fields.', 'error');
      return;
    }
    if (payload.budget_min > payload.budget_max) {
      showToast('Minimum budget cannot exceed maximum.', 'error');
      return;
    }

    try {
      await api('/projects', { method: 'POST', body: JSON.stringify(payload) });
      showToast('Project posted successfully!');
      setTimeout(() => {
        window.location.href = 'client-dashboard.html';
      }, 800);
    } catch (err) {
      showToast(err.message || 'Something went wrong posting your project.', 'error');
    }
  });

  updatePreview();
});

// ---------- Proposal submission ----------
document.addEventListener('DOMContentLoaded', () => {
  const proposalForm = document.getElementById('proposalForm');
  if (!proposalForm) return;

  requireAuth(['freelancer']);

  const params = new URLSearchParams(window.location.search);
  const projectId = Number(params.get('id'));
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
  } catch (err) {
    showToast(err.message || 'Could not load project.', 'error');
  }
}
