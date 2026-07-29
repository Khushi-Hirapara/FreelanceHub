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
    throw new ApiError(message, res.status, detail);
  }

  return data;
}

function requireAuth(roles = null) {
  if (!Auth.isLoggedIn()) {
    window.location.href = 'login.html';
    return null;
  }
  const user = Auth.getUser();
  if (roles && user && !roles.includes(user.role)) {
    if (user.role === 'freelancer') window.location.href = 'freelancer-dashboard.html';
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

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

function dashboardForRole(role) {
  if (role === 'freelancer') return 'freelancer-dashboard.html';
  if (role === 'admin') return 'client-dashboard.html';
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
  };
  return map[status] || 'status-open';
}
