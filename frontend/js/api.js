// ============================================
// api.js — shared API client for FreelanceHub
// ============================================

const API_BASE = 'http://localhost:8000/api';

const Auth = {
  getToken() {
    return localStorage.getItem('token');
  },
  setSession(token, user) {
    localStorage.setItem('token', token);
    if (user) localStorage.setItem('user', JSON.stringify(user));
  },
  getUser() {
    try {
      return JSON.parse(localStorage.getItem('user') || 'null');
    } catch {
      return null;
    }
  },
  clear() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  },
  isLoggedIn() {
    return Boolean(this.getToken());
  },
};

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function api(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  const token = Auth.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(
      'Cannot reach the API. Is the backend running on http://localhost:8000?',
      0
    );
  }

  if (res.status === 204) return null;

  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const detail = data?.detail;
    let message = 'Request failed';
    if (typeof detail === 'string') message = detail;
    else if (Array.isArray(detail)) message = detail.map((d) => d.msg || d).join(', ');
    else if (res.status === 401) message = 'Please log in again.';

    const isAuthAttempt = path.startsWith('/auth/login') || path.startsWith('/auth/register');
    if (res.status === 401 && !isAuthAttempt) {
      handleUnauthorizedSession();
    }
    throw new ApiError(message, res.status, detail);
  }

  return data;
}

/** Public pages that guests may open without a session. */
const PUBLIC_PAGES = new Set(['login.html', 'register.html', 'index.html', '']);

function currentHtmlPage() {
  return window.location.pathname.split('/').pop() || 'index.html';
}

function loginPageHref(nextPage) {
  const page = currentHtmlPage();
  const onAppPage = page !== '' && page !== 'index.html';
  const base = onAppPage ? 'login.html' : 'pages/login.html';
  if (!nextPage || PUBLIC_PAGES.has(nextPage) || nextPage === 'index.html') return base;
  return `${base}?next=${encodeURIComponent(nextPage)}`;
}

function handleUnauthorizedSession() {
  const page = currentHtmlPage();
  if (PUBLIC_PAGES.has(page)) return;
  Auth.clear();
  if (typeof window.stopNotificationPolling === 'function') {
    window.stopNotificationPolling();
  }
  if (!window.__fhRedirectingToLogin) {
    window.__fhRedirectingToLogin = true;
    window.location.href = loginPageHref(page);
  }
}

/** Redirect guests to login. Call early on every page that loads api.js. */
function enforceAuthGate() {
  const page = currentHtmlPage();
  if (PUBLIC_PAGES.has(page) || page === 'index.html' || page === '') return true;
  if (Auth.isLoggedIn() && Auth.getUser()) return true;
  Auth.clear();
  window.location.href = loginPageHref(page);
  return false;
}

async function apiUpload(path, formData) {
  const headers = {};
  const token = Auth.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData });
  } catch {
    throw new ApiError(
      'Cannot reach the API. Is the backend running on http://localhost:8000?',
      0
    );
  }

  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const detail = data?.detail;
    let message = 'Upload failed';
    if (typeof detail === 'string') message = detail;
    else if (Array.isArray(detail)) message = detail.map((d) => d.msg || d).join(', ');
    else if (res.status === 401) message = 'Please log in again.';
    if (res.status === 401) handleUnauthorizedSession();
    throw new ApiError(message, res.status, detail);
  }
  return data;
}

async function downloadAttachment(attachmentId, filename) {
  const headers = {};
  const token = Auth.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/attachments/${attachmentId}/download`, { headers });
  if (!res.ok) {
    let message = 'Download failed';
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') message = data.detail;
    } catch {
      // keep default
    }
    throw new ApiError(message, res.status);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || 'download';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function formatBytes(size) {
  const n = Number(size || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function requireAuth(roles = null) {
  if (!enforceAuthGate()) return null;
  const user = Auth.getUser();
  if (roles && user && !roles.includes(user.role)) {
    if (user.role === 'freelancer') window.location.href = 'freelancer-dashboard.html';
    else if (user.role === 'admin') window.location.href = 'admin-dashboard.html';
    else window.location.href = 'client-dashboard.html';
    return null;
  }
  return user;
}

function initials(name = '') {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || '')
    .join('') || '?';
}

function timeAgo(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function formatMoney(n) {
  return `$${Number(n || 0).toLocaleString()}`;
}

function starString(rating) {
  const filled = Math.max(0, Math.min(5, Math.round(Number(rating) || 0)));
  return `${'★'.repeat(filled)}${'☆'.repeat(5 - filled)}`;
}

function formatCurrency(amount, currency = 'USD') {
  const code = String(currency || 'USD').toUpperCase();
  try {
    return new Intl.NumberFormat(code === 'INR' ? 'en-IN' : 'en-US', {
      style: 'currency',
      currency: code,
      maximumFractionDigits: 2,
    }).format(Number(amount || 0));
  } catch {
    return formatMoney(amount);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

function dashboardForRole(role) {
  if (role === 'freelancer') return 'freelancer-dashboard.html';
  if (role === 'admin') return 'admin-dashboard.html';
  return 'client-dashboard.html';
}

function statusLabel(status) {
  const map = {
    open: 'Open for bids',
    in_progress: 'In progress',
    awaiting_review: 'Awaiting review',
    completed: 'Completed',
    draft: 'Draft',
    cancelled: 'Cancelled',
    pending: 'Pending',
    funded: 'Funded',
    submitted: 'Submitted',
    approved: 'Approved',
    disputed: 'Disputed',
    processing: 'Processing',
    paid: 'Paid',
    failed: 'Failed',
    released: 'Released',
    under_review: 'Under review',
    resolved: 'Resolved',
    rejected: 'Rejected',
    refund_client: 'Refund client',
    release_to_freelancer: 'Release to freelancer',
    partial_refund: 'Partial refund',
    refunded: 'Refunded',
  };
  return map[status] || status;
}

function statusClass(status) {
  const map = {
    open: 'status-open',
    in_progress: 'status-progress',
    awaiting_review: 'status-review',
    completed: 'status-open',
    draft: 'status-review',
    cancelled: 'status-review',
    pending: 'status-review',
    funded: 'status-progress',
    submitted: 'status-progress',
    approved: 'status-open',
    disputed: 'status-review',
  };
  return map[status] || 'status-open';
}
