// ============================================
// main.js — shared behavior across all pages
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  const currentPage = window.location.pathname.split('/').pop();
  document.querySelectorAll('.nav-links a').forEach((link) => {
    if (link.getAttribute('href') === currentPage) {
      link.classList.add('active');
    }
  });

  document.querySelectorAll('.nav-actions a').forEach((link) => {
    const label = (link.textContent || '').trim().toLowerCase();
    if (label === 'log out' || label === 'logout') {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        Auth.clear();
        window.location.href = 'login.html';
      });
    }
  });
});

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
