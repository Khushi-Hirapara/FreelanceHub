// ============================================
// main.js — shared behavior across all pages
// Role is read from localStorage key "user" → { role, ... }
// (set by Auth.setSession in api.js / auth.js)
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  if (typeof enforceAuthGate === 'function' && !enforceAuthGate()) return;

  document.querySelectorAll('a.nav-logo').forEach((logo) => {
    logo.setAttribute('href', homeHref());
  });

  updateRoleNavLinks();
  updateAuthNav();
  mountStaticSidebar();
  startNotificationPolling();
  bindLogoutButtons();
  bindComingSoonLinks();
  highlightActiveNav();
  wireMarketingCtas();
  fixMessagingBrowseLink();
});

function isHomePage() {
  const page = window.location.pathname.split('/').pop() || 'index.html';
  return page === '' || page === 'index.html';
}

function pagesPrefix() {
  return isHomePage() ? 'pages/' : '';
}

function homeHref() {
  return isHomePage() ? 'index.html' : '../index.html';
}

function currentPageName() {
  return window.location.pathname.split('/').pop() || 'index.html';
}

/** Role from localStorage "user" object (Auth.getUser().role) */
function getStoredRole() {
  if (typeof Auth === 'undefined' || !Auth.isLoggedIn()) return null;
  const user = Auth.getUser();
  return user?.role || null;
}

function updateRoleNavLinks() {
  const navList = document.querySelector('.nav-links');
  if (!navList) return;

  const prefix = pagesPrefix();
  const role = getStoredRole();
  const howHref = isHomePage() ? '#how' : '../index.html#how';

  let items = [];

  if (!role) {
    // Logged out — keep marketing links on the landing page
    if (isHomePage()) {
      items = [
        { href: '#how', label: 'How it works', key: 'how' },
        { href: '#briefs', label: 'Open briefs', key: 'briefs' },
        { href: prefix + 'login.html', label: 'Sign in', key: 'signin' },
      ];
    } else {
      items = [
        { href: '../index.html', label: 'Home', key: 'home' },
        { href: howHref, label: 'How it Works', key: 'how' },
        { href: prefix + 'login.html', label: 'Sign in', key: 'signin' },
      ];
    }
  } else if (role === 'freelancer') {
    items = [
      { href: prefix + 'freelancer-dashboard.html', label: 'Find Work', key: 'find-work' },
      { href: prefix + 'contracts.html', label: 'Contracts', key: 'contracts' },
      { href: prefix + 'payments.html', label: 'Earnings', key: 'payments' },
      { href: prefix + 'messaging.html', label: 'Messages', key: 'messages' },
      { href: prefix + 'profile.html', label: 'Profile', key: 'profile' },
    ];
  } else if (role === 'admin') {
    items = [
      { href: prefix + 'admin-dashboard.html', label: 'Admin', key: 'admin' },
      { href: prefix + 'find-talent.html', label: 'Find Talent', key: 'find-talent' },
      { href: prefix + 'contracts.html', label: 'Contracts', key: 'contracts' },
      { href: prefix + 'payments.html', label: 'Payments', key: 'payments' },
      { href: prefix + 'messaging.html', label: 'Messages', key: 'messages' },
      { href: prefix + 'profile.html', label: 'Profile', key: 'profile' },
    ];
  } else {
    // client
    items = [
      { href: prefix + 'find-talent.html', label: 'Find Talent', key: 'find-talent' },
      { href: prefix + 'client-dashboard.html', label: 'My Projects', key: 'my-projects' },
      { href: prefix + 'contracts.html', label: 'Contracts', key: 'contracts' },
      { href: prefix + 'payments.html', label: 'Payments', key: 'payments' },
      { href: prefix + 'messaging.html', label: 'Messages', key: 'messages' },
      { href: prefix + 'profile.html', label: 'Profile', key: 'profile' },
    ];
  }

  navList.innerHTML = items
    .map(
      (item) =>
        `<li data-nav="${item.key}"><a href="${item.href}">${item.label}</a></li>`
    )
    .join('');
}

function highlightActiveNav() {
  const page = currentPageName();
  document.querySelectorAll('.nav-links a').forEach((link) => {
    const href = link.getAttribute('href') || '';
    const file = href.split('/').pop().split('#')[0];
    if (file && file === page) {
      link.classList.add('active');
    }
  });
}

/** Fixed role sidebar — same links on every app page (active state only changes). */
function sidebarLinksForRole(role) {
  if (role === 'freelancer') {
    return {
      workspace: [
        { href: 'freelancer-dashboard.html', label: 'Find Work', icon: 'FW', match: ['freelancer-dashboard.html', 'project-detail.html', 'proposal-submission.html'] },
        { href: 'my-proposals.html', label: 'My Proposals', icon: 'MP', match: ['my-proposals.html'] },
        { href: 'contracts.html', label: 'Contracts', icon: 'CT', match: ['contracts.html', 'contract-detail.html', 'milestone-payment.html'] },
        { href: 'payments.html', label: 'Earnings', icon: 'ER', match: ['payments.html', 'payment.html', 'payment-detail.html'] },
      ],
      account: [
        { href: 'messaging.html', label: 'Messages', icon: 'MS', match: ['messaging.html'] },
        { href: 'profile.html', label: 'Profile', icon: 'PF', match: ['profile.html', 'freelancer-profile.html'] },
      ],
      roleLabel: 'Freelancer',
    };
  }
  if (role === 'admin') {
    return {
      workspace: [
        { href: 'admin-dashboard.html', label: 'Admin Console', icon: 'AD', match: ['admin-dashboard.html'] },
        { href: 'find-talent.html', label: 'Find Talent', icon: 'FT', match: ['find-talent.html', 'freelancer-profile.html'] },
        { href: 'contracts.html', label: 'Contracts', icon: 'CT', match: ['contracts.html', 'contract-detail.html'] },
        { href: 'payments.html', label: 'Payments', icon: 'PY', match: ['payments.html', 'payment.html', 'payment-detail.html'] },
      ],
      account: [
        { href: 'messaging.html', label: 'Messages', icon: 'MS', match: ['messaging.html'] },
        { href: 'profile.html', label: 'Profile', icon: 'PF', match: ['profile.html'] },
      ],
      roleLabel: 'Admin',
    };
  }
  // client (default authenticated marketplace role)
  return {
    workspace: [
      { href: 'find-talent.html', label: 'Find Talent', icon: 'FT', match: ['find-talent.html', 'freelancer-profile.html'] },
      { href: 'client-dashboard.html', label: 'My Projects', icon: 'PR', match: ['client-dashboard.html', 'project-detail.html'] },
      { href: 'project-posting.html', label: 'Post a Project', icon: 'NP', match: ['project-posting.html'] },
      { href: 'contracts.html', label: 'Contracts', icon: 'CT', match: ['contracts.html', 'contract-detail.html', 'milestone-payment.html'] },
      { href: 'payments.html', label: 'Payments', icon: 'PY', match: ['payments.html', 'payment.html', 'payment-detail.html'] },
    ],
    account: [
      { href: 'messaging.html', label: 'Messages', icon: 'MS', match: ['messaging.html'] },
      { href: 'profile.html', label: 'Profile', icon: 'PF', match: ['profile.html'] },
    ],
    roleLabel: 'Client',
  };
}

function mountStaticSidebar() {
  const aside = document.querySelector('aside.sidebar[data-static-sidebar]');
  if (!aside) return;

  const role = getStoredRole();
  const user = typeof Auth !== 'undefined' ? Auth.getUser() : null;
  const page = currentPageName();
  const prefix = pagesPrefix();

  if (!role) {
    aside.innerHTML = `
      <div class="sidebar-profile">
        <div class="avatar">?</div>
        <div>
          <h4>Guest</h4>
          <span>Sign in to continue</span>
        </div>
      </div>
      <nav class="sidebar-nav" aria-label="Explore">
        <div class="nav-section">Browse</div>
        <a href="${prefix}find-talent.html" class="${page === 'find-talent.html' ? 'active' : ''}">
          <span class="icon">FT</span><span>Find Talent</span>
        </a>
        <a href="${prefix}freelancer-dashboard.html" class="${page === 'freelancer-dashboard.html' ? 'active' : ''}">
          <span class="icon">FW</span><span>Find Work</span>
        </a>
        <div class="nav-section">Account</div>
        <a href="${prefix}login.html"><span class="icon">IN</span><span>Log in</span></a>
        <a href="${prefix}register.html"><span class="icon">JN</span><span>Join free</span></a>
      </nav>
    `;
    return;
  }

  const menu = sidebarLinksForRole(role);
  const allLinks = [...menu.workspace, ...menu.account];

  const linkHtml = (item) => {
    const active = (item.match || [item.href]).includes(page);
    return `<a href="${item.href}" class="${active ? 'active' : ''}" data-nav-href="${item.href}">
      <span class="icon">${item.icon}</span>
      <span>${item.label}</span>
    </a>`;
  };

  const name = user?.name || menu.roleLabel;
  const roleText =
    role === 'freelancer' ? 'Freelancer' : role === 'admin' ? 'Admin' : 'Client';

  aside.innerHTML = `
    <div class="sidebar-profile">
      <div class="avatar" id="sideAvatar">${escapeHtml(typeof initials === 'function' ? initials(name) : '•')}</div>
      <div>
        <h4 id="sideName">${escapeHtml(name)}</h4>
        <span id="sideRole">${escapeHtml(roleText)}</span>
      </div>
    </div>
    <nav class="sidebar-nav" id="sideNav" aria-label="Workspace">
      <div class="nav-section">Workspace</div>
      ${menu.workspace.map(linkHtml).join('')}
      <div class="nav-section">Account</div>
      ${menu.account.map(linkHtml).join('')}
    </nav>
    <div class="sidebar-foot">
      <a href="../index.html">← Back to home</a>
    </div>
  `;

  let mobile = document.querySelector('.mobile-side-nav');
  if (!mobile) {
    mobile = document.createElement('div');
    mobile.className = 'mobile-side-nav';
    mobile.setAttribute('aria-label', 'Workspace navigation');
    const layout = document.querySelector('.dash-layout');
    layout?.parentNode?.insertBefore(mobile, layout);
  }
  mobile.innerHTML = allLinks
    .map((item) => {
      const active = (item.match || [item.href]).includes(page);
      return `<a href="${item.href}" class="${active ? 'active' : ''}">${item.label}</a>`;
    })
    .join('');
}

function updateAuthNav() {
  const actions = document.querySelector('.nav-actions');
  if (!actions || typeof Auth === 'undefined') return;

  const user = Auth.getUser();
  const loggedIn = Auth.isLoggedIn() && user;
  const prefix = pagesPrefix();

  if (loggedIn) {
    const firstName = escapeHtml(user.name.split(' ')[0]);
    actions.innerHTML = `
      <div class="nav-notify" id="navNotify">
        <button type="button" class="nav-bell" id="notifyBell" aria-label="Notifications" aria-expanded="false">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9a6 6 0 1 1 12 0c0 7 3 7 3 9H3c0-2 3-2 3-9"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>
          <span class="nav-badge" id="notifyBadge" hidden>0</span>
        </button>
        <div class="notify-panel" id="notifyPanel" hidden>
          <div class="notify-head">
            <strong>Notifications</strong>
            <button type="button" id="notifyReadAll">Mark all read</button>
          </div>
          <div class="notify-list" id="notifyList">
            <p class="notify-empty">Loading…</p>
          </div>
        </div>
      </div>
      <span class="nav-user">Hi, ${firstName}</span>
      <a href="#" class="btn btn-primary btn-sm" data-logout>Log Out</a>
    `;
    bindNotificationBell();
  } else {
    actions.innerHTML = `
      <a href="${prefix}login.html" class="btn btn-ghost">Log in</a>
      <a href="${prefix}register.html" class="btn btn-primary btn-sm">Join Free</a>
    `;
  }

  bindLogoutButtons();
}

function bindLogoutButtons() {
  document.querySelectorAll('[data-logout]').forEach((link) => {
    link.onclick = (e) => {
      e.preventDefault();
      Auth.clear();
      stopNotificationPolling();
      window.location.href = pagesPrefix() + 'login.html';
    };
  });
}

function wireMarketingCtas() {
  const loggedIn = typeof Auth !== 'undefined' && Auth.isLoggedIn();
  const user = typeof Auth !== 'undefined' ? Auth.getUser() : null;
  const prefix = pagesPrefix();

  if (!loggedIn || !user) {
    document.querySelectorAll('[data-auth-cta]').forEach((a) => {
      const intent = a.getAttribute('data-auth-cta');
      if (intent === 'hire') a.setAttribute('href', prefix + 'register.html');
      if (intent === 'work') a.setAttribute('href', prefix + 'register.html');
      if (intent === 'signin') a.setAttribute('href', prefix + 'login.html');
    });
    return;
  }

  document.querySelectorAll('[data-auth-cta], .hero-ctas a, .cta-band a, .role-card a, .land-cta a').forEach((a) => {
    const intent = a.getAttribute('data-auth-cta');
    const text = (a.textContent || '').trim().toLowerCase();
    if (intent === 'hire' || text.includes('hire') || text === 'post a project' || text.includes('get started')) {
      a.setAttribute(
        'href',
        user.role === 'freelancer' ? prefix + 'freelancer-dashboard.html' : prefix + 'project-posting.html'
      );
      if (intent === 'hire') a.textContent = user.role === 'freelancer' ? 'Browse Work' : 'Post a Project';
    }
    if (intent === 'work' || text === 'browse work' || text === 'browse projects' || text.includes('find work')) {
      a.setAttribute(
        'href',
        user.role === 'client' || user.role === 'admin'
          ? prefix + 'find-talent.html'
          : prefix + 'freelancer-dashboard.html'
      );
    }
    if (intent === 'signin' || text.includes('create free') || text === 'join free' || text.includes('go to dashboard')) {
      a.setAttribute('href', prefix + dashboardForRole(user.role));
      a.textContent = 'Go to Dashboard';
    }
  });
}

function bindComingSoonLinks() {
  document.querySelectorAll('[data-coming-soon]').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      showToast(link.getAttribute('data-coming-soon') || 'Coming soon.', 'error');
    });
  });
}

function fixMessagingBrowseLink() {
  const link = document.getElementById('chatBrowseLink');
  if (!link) return;
  const role = getStoredRole();
  const prefix = pagesPrefix();
  if (role === 'freelancer') {
    link.href = prefix + 'freelancer-dashboard.html';
    link.textContent = 'Browse Work';
  } else if (role === 'client' || role === 'admin') {
    link.href = prefix + 'find-talent.html';
    link.textContent = 'Find Talent';
  } else {
    link.href = prefix + 'login.html';
    link.textContent = 'Log in';
  }
}

let notificationTimer = null;
let notificationVisibilityBound = false;

function stopNotificationPolling() {
  if (notificationTimer) {
    clearInterval(notificationTimer);
    notificationTimer = null;
  }
}
window.stopNotificationPolling = stopNotificationPolling;

function startNotificationPolling() {
  stopNotificationPolling();
  if (typeof Auth === 'undefined' || !Auth.isLoggedIn() || !Auth.getUser()) return;
  refreshUnreadCount();
  notificationTimer = setInterval(refreshUnreadCount, 20000);
  if (!notificationVisibilityBound) {
    notificationVisibilityBound = true;
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && Auth.isLoggedIn()) {
        refreshUnreadCount();
      }
    });
  }
}

function bindNotificationBell() {
  const bell = document.getElementById('notifyBell');
  const panel = document.getElementById('notifyPanel');
  const readAll = document.getElementById('notifyReadAll');
  if (!bell || !panel) return;

  bell.addEventListener('click', async (event) => {
    event.stopPropagation();
    const open = panel.hidden;
    panel.hidden = !open;
    bell.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) await loadNotificationList();
  });
  panel.addEventListener('click', (event) => event.stopPropagation());
  document.addEventListener('click', () => {
    panel.hidden = true;
    bell.setAttribute('aria-expanded', 'false');
  });
  readAll?.addEventListener('click', async () => {
    try {
      await api('/notifications/read-all', { method: 'PATCH' });
      await refreshUnreadCount();
      await loadNotificationList();
    } catch (err) {
      showToast(err.message || 'Could not mark notifications read.', 'error');
    }
  });
}

async function refreshUnreadCount() {
  const badge = document.getElementById('notifyBadge');
  if (!badge || typeof Auth === 'undefined' || !Auth.isLoggedIn()) {
    stopNotificationPolling();
    return;
  }
  try {
    const data = await api('/notifications/unread-count');
    const count = Number(data?.count || 0);
    badge.hidden = count <= 0;
    badge.textContent = count > 99 ? '99+' : String(count);
  } catch (err) {
    badge.hidden = true;
    if (err?.status === 401) stopNotificationPolling();
  }
}

async function loadNotificationList() {
  const list = document.getElementById('notifyList');
  if (!list) return;
  if (typeof Auth === 'undefined' || !Auth.isLoggedIn()) {
    list.innerHTML = '<p class="notify-empty">Log in to see notifications.</p>';
    return;
  }
  list.innerHTML = '<p class="notify-empty">Loading…</p>';
  try {
    const items = await api('/notifications?limit=12');
    if (!items.length) {
      list.innerHTML = '<p class="notify-empty">No notifications yet.</p>';
      return;
    }
    list.innerHTML = items.map(renderNotificationItem).join('');
    list.querySelectorAll('[data-notification]').forEach((button) => {
      button.addEventListener('click', () => openNotification(button.dataset.notification));
    });
  } catch (err) {
    list.innerHTML = `<p class="notify-empty">${escapeHtml(err.message || 'Could not load notifications.')}</p>`;
  }
}

function renderNotificationItem(item) {
  return `
    <button type="button" class="notify-item${item.is_read ? '' : ' unread'}" data-notification="${item.id}" data-href="${escapeHtml(notificationHref(item))}">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.message)}</p>
      <span>${escapeHtml(timeAgo(item.created_at))}</span>
    </button>
  `;
}

function notificationHref(item) {
  const prefix = pagesPrefix();
  const id = item.related_id;
  const type = (item.related_type || '').toLowerCase();
  if (type === 'project' && id) return `${prefix}project-detail.html?id=${id}`;
  if (type === 'contract' && id) return `${prefix}contract-detail.html?id=${id}`;
  if (type === 'payment' && id) return `${prefix}payment-detail.html?id=${id}`;
  if (type === 'milestone' && id) return `${prefix}contract-detail.html?id=${id}`;
  if (type === 'conversation' || type === 'message') return `${prefix}messaging.html`;
  if (type === 'proposal' && id) {
    return getStoredRole() === 'freelancer'
      ? `${prefix}my-proposals.html`
      : `${prefix}project-detail.html?id=${id}`;
  }
  if (type === 'dispute' && id) return `${prefix}contract-detail.html?id=${id}`;
  if (type === 'review') return `${prefix}profile.html`;
  return prefix + (getStoredRole() === 'freelancer' ? 'freelancer-dashboard.html' : 'client-dashboard.html');
}

async function openNotification(id) {
  const button = document.querySelector(`[data-notification="${id}"]`);
  const href = button?.dataset.href;
  try {
    await api(`/notifications/${id}/read`, { method: 'PATCH' });
  } catch {
    // Still follow the link if the row was already read or removed.
  }
  if (href) window.location.href = href;
}

function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    background: ${type === 'error' ? '#B23A3A' : '#12172B'};
    color: #F7F5F0; padding: 12px 20px; border-radius: 6px;
    font-family: 'Inter', sans-serif; font-size: 0.9rem;
    box-shadow: 0 8px 24px rgba(0,0,0,0.2); z-index: 1000;
    opacity: 0; transition: opacity 0.2s ease;
  `;
  document.body.appendChild(toast);
  requestAnimationFrame(() => {
    toast.style.opacity = '1';
  });
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 200);
  }, 2500);
}
