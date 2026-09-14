// ============================================
// main.js — shared behavior across all pages
// Role is read from localStorage key "user" → { role, ... }
// (set by Auth.setSession in api.js / auth.js)
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('a.nav-logo').forEach((logo) => {
    logo.setAttribute('href', homeHref());
  });

  updateRoleNavLinks();
  updateAuthNav();
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
    // Logged out
    items = [
      { href: prefix + 'find-talent.html', label: 'Find Talent', key: 'find-talent' },
      { href: prefix + 'freelancer-dashboard.html', label: 'Find Work', key: 'find-work' },
      { href: howHref, label: 'How it Works', key: 'how' },
    ];
  } else if (role === 'freelancer') {
    items = [
      { href: prefix + 'freelancer-dashboard.html', label: 'Find Work', key: 'find-work' },
      { href: prefix + 'messaging.html', label: 'Messages', key: 'messages' },
      { href: prefix + 'profile.html', label: 'Profile', key: 'profile' },
    ];
  } else {
    // client or admin
    items = [
      { href: prefix + 'find-talent.html', label: 'Find Talent', key: 'find-talent' },
      { href: prefix + 'client-dashboard.html', label: 'My Projects', key: 'my-projects' },
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

function updateAuthNav() {
  const actions = document.querySelector('.nav-actions');
  if (!actions || typeof Auth === 'undefined') return;

  const user = Auth.getUser();
  const loggedIn = Auth.isLoggedIn() && user;
  const prefix = pagesPrefix();

  if (loggedIn) {
    const firstName = escapeHtml(user.name.split(' ')[0]);
    actions.innerHTML = `
      <span class="nav-user">Hi, ${firstName}</span>
      <a href="#" class="btn btn-primary btn-sm" data-logout>Log Out</a>
    `;
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
      window.location.href = pagesPrefix() + 'login.html';
    };
  });
}

function wireMarketingCtas() {
  const loggedIn = typeof Auth !== 'undefined' && Auth.isLoggedIn();
  const user = typeof Auth !== 'undefined' ? Auth.getUser() : null;
  const prefix = pagesPrefix();
  if (!loggedIn || !user) return;

  document.querySelectorAll('.hero-ctas a, .cta-band a, .role-card a').forEach((a) => {
    const text = (a.textContent || '').trim().toLowerCase();
    if (text === 'post a project') {
      a.setAttribute(
        'href',
        user.role === 'freelancer' ? prefix + 'freelancer-dashboard.html' : prefix + 'project-posting.html'
      );
    }
    if (text === 'browse work' || text === 'browse projects') {
      a.setAttribute(
        'href',
        user.role === 'client' || user.role === 'admin'
          ? prefix + 'find-talent.html'
          : prefix + 'freelancer-dashboard.html'
      );
    }
    if (text.includes('create free') || text === 'join free') {
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
