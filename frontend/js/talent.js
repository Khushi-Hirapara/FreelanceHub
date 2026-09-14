// ============================================
// talent.js — Find Talent search & filters
// Same chip/search pattern as dashboard.js
// ============================================

document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('talentSearch');
  const categoryChips = document.querySelectorAll('.filter-category');
  const ratingChips = document.querySelectorAll('.filter-rating');
  const rateChips = document.querySelectorAll('.filter-rate');
  const cards = document.querySelectorAll('.talent-card');
  const emptyMsg = document.getElementById('noTalentResults');

  let activeCategory = 'all';
  let minRating = 0;
  let rateRange = 'all';

  categoryChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      categoryChips.forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      activeCategory = chip.dataset.category || 'all';
      applyFilters();
    });
  });

  ratingChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      ratingChips.forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      minRating = Number(chip.dataset.rating || 0);
      applyFilters();
    });
  });

  rateChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      rateChips.forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      rateRange = chip.dataset.rate || 'all';
      applyFilters();
    });
  });

  searchInput?.addEventListener('input', () => applyFilters());

  function rateMatches(hourly) {
    if (rateRange === 'all') return true;
    if (rateRange === '0-25') return hourly < 25;
    if (rateRange === '25-50') return hourly >= 25 && hourly <= 50;
    if (rateRange === '50-100') return hourly >= 50 && hourly <= 100;
    if (rateRange === '100+') return hourly >= 100;
    return true;
  }

  function applyFilters() {
    const query = (searchInput?.value || '').trim().toLowerCase();
    let visible = 0;

    cards.forEach((card) => {
      const name = card.dataset.name || '';
      const title = card.dataset.title || '';
      const bio = card.dataset.bio || '';
      const skills = card.dataset.skills || '';
      const category = card.dataset.category || '';
      const rating = Number(card.dataset.rating || 0);
      const rate = Number(card.dataset.rate || 0);

      const haystack = `${name} ${title} ${bio} ${skills}`;
      const matchSearch = !query || haystack.includes(query);
      const matchCategory = activeCategory === 'all' || category === activeCategory;
      const matchRating = rating >= minRating;
      const matchRate = rateMatches(rate);

      const show = matchSearch && matchCategory && matchRating && matchRate;
      card.style.display = show ? '' : 'none';
      if (show) visible += 1;
    });

    if (emptyMsg) emptyMsg.style.display = visible === 0 ? 'block' : 'none';
  }
});
