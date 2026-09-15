// ============================================
// hire.js — real-world hire / invite / message flow
// ============================================

(function () {
  const STATE = {
    freelancer: null,
    step: 'choose', // choose | message | invite
    projects: [],
  };

  function ensureModal() {
    let root = document.getElementById('hireModal');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'hireModal';
    root.className = 'hire-modal';
    root.hidden = true;
    root.innerHTML = `
      <div class="hire-modal-backdrop" data-hire-close></div>
      <div class="hire-modal-panel" role="dialog" aria-modal="true" aria-labelledby="hireModalTitle">
        <button type="button" class="hire-modal-x" data-hire-close aria-label="Close">×</button>
        <div class="hire-modal-body" id="hireModalBody"></div>
      </div>
    `;
    document.body.appendChild(root);
    root.addEventListener('click', (event) => {
      if (event.target.closest('[data-hire-close]')) closeHireModal();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !root.hidden) closeHireModal();
    });
    return root;
  }

  function closeHireModal() {
    const root = document.getElementById('hireModal');
    if (!root) return;
    root.hidden = true;
    document.body.classList.remove('hire-modal-open');
    STATE.freelancer = null;
    STATE.step = 'choose';
  }

  window.openHireFlow = async function openHireFlow(freelancer) {
    const viewer = typeof Auth !== 'undefined' ? Auth.getUser() : null;
    if (!viewer || !Auth.isLoggedIn()) {
      window.location.href = 'login.html?next=find-talent.html';
      return;
    }
    if (viewer.role !== 'client' && viewer.role !== 'admin') {
      showToast('Only clients can hire freelancers.', 'error');
      return;
    }
    if (!freelancer?.id) return;

    STATE.freelancer = {
      id: Number(freelancer.id),
      name: freelancer.name || 'Freelancer',
      title: freelancer.title || 'Freelancer',
      skills: freelancer.skills || [],
    };
    STATE.step = 'choose';

    const root = ensureModal();
    root.hidden = false;
    document.body.classList.add('hire-modal-open');
    renderHireStep();
  };

  function renderHireStep() {
    const body = document.getElementById('hireModalBody');
    if (!body || !STATE.freelancer) return;
    if (STATE.step === 'message') {
      body.innerHTML = renderMessageStep();
      bindMessageStep();
      return;
    }
    if (STATE.step === 'invite') {
      body.innerHTML = renderInviteStepLoading();
      loadInviteStep();
      return;
    }
    body.innerHTML = renderChooseStep();
    bindChooseStep();
  }

  function personChip() {
    const p = STATE.freelancer;
    return `
      <div class="hire-person">
        <div class="hire-avatar">${escapeHtml(initials(p.name))}</div>
        <div>
          <strong>${escapeHtml(p.name)}</strong>
          <span>${escapeHtml(p.title)}</span>
        </div>
      </div>
    `;
  }

  function renderChooseStep() {
    return `
      <p class="hire-kicker">Start hiring</p>
      <h2 id="hireModalTitle">How do you want to work with ${escapeHtml(STATE.freelancer.name)}?</h2>
      <p class="hire-lead">Pick the path that matches how real marketplaces work — talk first, invite to a job, or post a fresh brief.</p>
      ${personChip()}
      <div class="hire-options">
        <button type="button" class="hire-option" data-hire-path="message">
          <span class="hire-option-icon">01</span>
          <span class="hire-option-copy">
            <strong>Send a message</strong>
            <small>Introduce the work and start a conversation.</small>
          </span>
        </button>
        <button type="button" class="hire-option" data-hire-path="invite">
          <span class="hire-option-icon">02</span>
          <span class="hire-option-copy">
            <strong>Invite to a project</strong>
            <small>Ask them to bid on one of your open briefs.</small>
          </span>
        </button>
        <button type="button" class="hire-option" data-hire-path="new">
          <span class="hire-option-icon">03</span>
          <span class="hire-option-copy">
            <strong>Post a new project</strong>
            <small>Create a fresh brief with this freelancer in mind.</small>
          </span>
        </button>
      </div>
    `;
  }

  function bindChooseStep() {
    document.querySelectorAll('[data-hire-path]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const path = btn.getAttribute('data-hire-path');
        if (path === 'new') {
          window.location.href = `project-posting.html?hire=${encodeURIComponent(STATE.freelancer.id)}`;
          return;
        }
        STATE.step = path;
        renderHireStep();
      });
    });
  }

  function renderMessageStep() {
    const defaultNote = `Hi ${STATE.freelancer.name} — I’d like to discuss a project with you on FreelanceHub. Are you available to chat about scope and timeline?`;
    return `
      <button type="button" class="hire-back" data-hire-back>← Back</button>
      <p class="hire-kicker">Message</p>
      <h2 id="hireModalTitle">Introduce yourself to ${escapeHtml(STATE.freelancer.name)}</h2>
      <p class="hire-lead">They’ll get a notification and can reply in Messages.</p>
      ${personChip()}
      <label class="hire-label" for="hireMessageText">Your message</label>
      <textarea id="hireMessageText" class="hire-textarea" rows="5" maxlength="5000">${escapeHtml(defaultNote)}</textarea>
      <div class="hire-actions">
        <button type="button" class="btn btn-ghost" data-hire-close>Cancel</button>
        <button type="button" class="btn btn-primary" id="hireSendMessage">Send message</button>
      </div>
      <p class="hire-error" id="hireError" hidden></p>
    `;
  }

  function bindMessageStep() {
    document.querySelector('[data-hire-back]')?.addEventListener('click', () => {
      STATE.step = 'choose';
      renderHireStep();
    });
    document.getElementById('hireSendMessage')?.addEventListener('click', async () => {
      const text = document.getElementById('hireMessageText')?.value.trim() || '';
      const error = document.getElementById('hireError');
      const btn = document.getElementById('hireSendMessage');
      if (!text) {
        if (error) {
          error.hidden = false;
          error.textContent = 'Write a short introduction first.';
        }
        return;
      }
      if (btn) btn.disabled = true;
      try {
        const saved = await api('/messages', {
          method: 'POST',
          body: JSON.stringify({
            receiver_id: STATE.freelancer.id,
            message_text: text,
          }),
        });
        showToast('Message sent.');
        window.location.href = `messaging.html?conversation=${saved.conversation_id}`;
      } catch (err) {
        if (error) {
          error.hidden = false;
          error.textContent = err.message || 'Could not send message.';
        }
        if (btn) btn.disabled = false;
      }
    });
  }

  function renderInviteStepLoading() {
    return `
      <button type="button" class="hire-back" data-hire-back>← Back</button>
      <p class="hire-kicker">Invite</p>
      <h2 id="hireModalTitle">Invite ${escapeHtml(STATE.freelancer.name)} to a project</h2>
      <p class="hire-lead">Loading your open projects…</p>
    `;
  }

  async function loadInviteStep() {
    const body = document.getElementById('hireModalBody');
    document.querySelector('[data-hire-back]')?.addEventListener('click', () => {
      STATE.step = 'choose';
      renderHireStep();
    });
    try {
      const mine = await api('/projects/mine');
      STATE.projects = (mine || []).filter((p) => String(p.status) === 'open');
      if (!body) return;
      body.innerHTML = renderInviteStep();
      bindInviteStep();
    } catch (err) {
      if (!body) return;
      body.innerHTML = `
        <button type="button" class="hire-back" data-hire-back>← Back</button>
        <h2 id="hireModalTitle">Could not load projects</h2>
        <p class="hire-lead">${escapeHtml(err.message || 'Try again.')}</p>
        <div class="hire-actions">
          <a class="btn btn-primary" href="project-posting.html?hire=${encodeURIComponent(STATE.freelancer.id)}">Post a new project</a>
        </div>
      `;
      document.querySelector('[data-hire-back]')?.addEventListener('click', () => {
        STATE.step = 'choose';
        renderHireStep();
      });
    }
  }

  function renderInviteStep() {
    if (!STATE.projects.length) {
      return `
        <button type="button" class="hire-back" data-hire-back>← Back</button>
        <p class="hire-kicker">Invite</p>
        <h2 id="hireModalTitle">No open projects yet</h2>
        <p class="hire-lead">Post a brief first, then invite ${escapeHtml(STATE.freelancer.name)} to bid.</p>
        ${personChip()}
        <div class="hire-actions">
          <button type="button" class="btn btn-ghost" data-hire-close>Cancel</button>
          <a class="btn btn-primary" href="project-posting.html?hire=${encodeURIComponent(STATE.freelancer.id)}">Post a project</a>
        </div>
      `;
    }

    const options = STATE.projects
      .map(
        (p) => `
        <label class="hire-project">
          <input type="radio" name="hireProject" value="${p.id}">
          <span>
            <strong>${escapeHtml(p.title)}</strong>
            <small>${escapeHtml(p.category)} · ${formatMoney(p.budget_min)}–${formatMoney(p.budget_max)}</small>
          </span>
        </label>
      `
      )
      .join('');

    const defaultNote = `Hi ${STATE.freelancer.name} — I’d like to invite you to submit a proposal on my project. Looking forward to your thoughts on scope and timeline.`;

    return `
      <button type="button" class="hire-back" data-hire-back>← Back</button>
      <p class="hire-kicker">Invite</p>
      <h2 id="hireModalTitle">Invite ${escapeHtml(STATE.freelancer.name)}</h2>
      <p class="hire-lead">They’ll get a message linked to the project and can open it to bid.</p>
      ${personChip()}
      <p class="hire-label">Choose an open project</p>
      <div class="hire-project-list">${options}</div>
      <label class="hire-label" for="hireInviteText">Invitation note</label>
      <textarea id="hireInviteText" class="hire-textarea" rows="4" maxlength="5000">${escapeHtml(defaultNote)}</textarea>
      <div class="hire-actions">
        <button type="button" class="btn btn-ghost" data-hire-close>Cancel</button>
        <button type="button" class="btn btn-primary" id="hireSendInvite">Send invite</button>
      </div>
      <p class="hire-error" id="hireError" hidden></p>
    `;
  }

  function bindInviteStep() {
    document.querySelector('[data-hire-back]')?.addEventListener('click', () => {
      STATE.step = 'choose';
      renderHireStep();
    });
    const first = document.querySelector('input[name="hireProject"]');
    if (first) first.checked = true;

    document.getElementById('hireSendInvite')?.addEventListener('click', async () => {
      const projectId = Number(document.querySelector('input[name="hireProject"]:checked')?.value || 0);
      const note = document.getElementById('hireInviteText')?.value.trim() || '';
      const error = document.getElementById('hireError');
      const btn = document.getElementById('hireSendInvite');
      const project = STATE.projects.find((p) => Number(p.id) === projectId);

      if (!projectId || !project) {
        if (error) {
          error.hidden = false;
          error.textContent = 'Select a project to invite them to.';
        }
        return;
      }
      if (!note) {
        if (error) {
          error.hidden = false;
          error.textContent = 'Add a short invitation note.';
        }
        return;
      }

      const messageText = `Project invite: “${project.title}”\n\n${note}\n\nOpen the project to submit a proposal.`;
      if (btn) btn.disabled = true;
      try {
        const saved = await api('/messages', {
          method: 'POST',
          body: JSON.stringify({
            receiver_id: STATE.freelancer.id,
            project_id: projectId,
            message_text: messageText,
          }),
        });
        showToast('Invite sent.');
        window.location.href = `messaging.html?conversation=${saved.conversation_id}`;
      } catch (err) {
        if (error) {
          error.hidden = false;
          error.textContent = err.message || 'Could not send invite.';
        }
        if (btn) btn.disabled = false;
      }
    });
  }
})();
