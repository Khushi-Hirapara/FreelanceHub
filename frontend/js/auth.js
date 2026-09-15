// ============================================
// auth.js — Login & Register (connected to FastAPI)
// ============================================

document.querySelectorAll('.role-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const group = btn.parentElement;
    group.querySelectorAll('.role-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

function getSelectedRole(containerId) {
  const container = document.getElementById(containerId) || document;
  const active = container.querySelector('.role-btn.active');
  return active ? active.dataset.role : 'client';
}

function safeNextPage() {
  const next = new URLSearchParams(window.location.search).get('next') || '';
  if (!next || next.includes('://') || next.includes('..') || next.startsWith('/')) return null;
  if (!/^[a-z0-9\-]+\.html$/i.test(next)) return null;
  if (PUBLIC_PAGES?.has?.(next) || next === 'login.html' || next === 'register.html') return null;
  return next;
}

function redirectAfterAuth(user) {
  const next = safeNextPage();
  window.location.href = next || dashboardForRole(user?.role);
}

const loginForm = document.getElementById('loginForm');
if (loginForm) {
  if (Auth.isLoggedIn() && Auth.getUser()) {
    redirectAfterAuth(Auth.getUser());
  }

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorBox = document.getElementById('loginError');
    errorBox.classList.remove('show');

    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    if (!email || !password) {
      errorBox.textContent = 'Please fill in both fields.';
      errorBox.classList.add('show');
      return;
    }

    const submitBtn = loginForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    try {
      // Email + password only — role comes from the account
      const data = await api('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      Auth.setSession(data.access_token, data.user);
      showToast(`Welcome back, ${data.user.name.split(' ')[0]}!`);
      setTimeout(() => redirectAfterAuth(data.user), 600);
    } catch (err) {
      errorBox.textContent = err.message || 'Incorrect email or password. Try again.';
      errorBox.classList.add('show');
      submitBtn.disabled = false;
    }
  });
}

const registerForm = document.getElementById('registerForm');
if (registerForm) {
  if (Auth.isLoggedIn() && Auth.getUser()) {
    redirectAfterAuth(Auth.getUser());
  }

  registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const fname = document.getElementById('fname').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const role = getSelectedRole('roleSelect');

    if (!fname || !email) {
      showToast('Please fill in your name and email.', 'error');
      return;
    }
    if (password !== confirmPassword) {
      showToast('Passwords do not match.', 'error');
      return;
    }
    if (password.length < 8) {
      showToast('Password must be at least 8 characters.', 'error');
      return;
    }

    const submitBtn = registerForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    try {
      const data = await api('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ name: fname, email, password, role }),
      });
      Auth.setSession(data.access_token, data.user);
      showToast('Account created! Taking you to your dashboard...');
      setTimeout(() => redirectAfterAuth(data.user), 800);
    } catch (err) {
      showToast(err.message || 'Something went wrong. Try again.', 'error');
      submitBtn.disabled = false;
    }
  });
}
