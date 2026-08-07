/**
 * app.js — Nour Competitor Monitor Dashboard
 * Fetches content from the Flask API and renders it in the UI.
 */

// ── State ─────────────────────────────────────────────────────────
let activeCompetitor = null;  // null = all
let activeTab = 'all';
let allData = [];             // cached API response
let lightboxItems = [];       // flat list for keyboard nav
let lightboxIndex = 0;

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadCompetitors();
  document.addEventListener('keydown', onKeyDown);
});

// ── API helpers ───────────────────────────────────────────────────
async function apiFetch(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

// ── Stats ─────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const stats = await apiFetch('/api/stats');
    document.getElementById('stat-competitors').textContent = stats.competitors;
    document.getElementById('stat-stories').textContent    = stats.stories;
    document.getElementById('stat-posts').textContent      = stats.posts;
    document.getElementById('stat-reels').textContent      = stats.reels;
  } catch (e) {
    console.warn('Could not load stats:', e);
  }
}

// ── Competitor sidebar ────────────────────────────────────────────
async function loadCompetitors() {
  const list = document.getElementById('competitor-list');
  try {
    const competitors = await apiFetch('/api/competitors');
    list.innerHTML = '';

    if (competitors.length === 0) {
      list.innerHTML = '<div class="loading-pulse">No data yet. Run scrape.py first.</div>';
      return;
    }

    // "All" item
    const allItem = createCompetitorItem({ username: 'all', full_name: 'All Competitors' }, true);
    list.appendChild(allItem);

    competitors.forEach(c => {
      list.appendChild(createCompetitorItem(c));
    });

    // Load all content by default
    await loadContent(null);

  } catch (e) {
    list.innerHTML = `<div class="loading-pulse" style="color:#f87171">Failed to connect to server.<br>Is server.py running?</div>`;
  }
}

function createCompetitorItem(competitor, isAll = false) {
  const item = document.createElement('div');
  item.className = 'competitor-item' + (isAll ? ' active' : '');
  item.dataset.username = competitor.username;

  const initial = competitor.username[0].toUpperCase();
  const hasStory = competitor.has_stories;

  item.innerHTML = `
    <div class="competitor-avatar ${hasStory ? 'has-story' : ''}">${initial}</div>
    <div class="competitor-info">
      <div class="competitor-name">@${isAll ? 'all' : competitor.username}</div>
      <div class="competitor-meta">${isAll ? 'All accounts' : (competitor.full_name || '')}</div>
    </div>
  `;

  item.addEventListener('click', () => {
    document.querySelectorAll('.competitor-item').forEach(el => el.classList.remove('active'));
    item.classList.add('active');
    loadContent(isAll ? null : competitor.username);
  });

  return item;
}

// ── Content loading ───────────────────────────────────────────────
async function loadContent(username) {
  activeCompetitor = username;

  const title    = document.getElementById('page-title');
  const subtitle = document.getElementById('page-subtitle');
  const grid     = document.getElementById('media-grid');
  const empty    = document.getElementById('empty-state');

  grid.innerHTML = '<div class="loading-pulse" style="padding:40px;grid-column:1/-1">Loading content…</div>';
  empty.classList.add('hidden');

  try {
    const endpoint = username ? `/api/content/${username}` : '/api/content';
    const data = await apiFetch(endpoint);

    // Normalise: endpoint returns array for all, object for single
    allData = Array.isArray(data) ? data : [data];

    if (username) {
      title.textContent    = `@${username}`;
      subtitle.textContent = allData[0]?.profile?.full_name || '';
    } else {
      title.textContent    = 'All Competitors';
      subtitle.textContent = `${allData.length} account${allData.length !== 1 ? 's' : ''}`;
    }

    renderGrid();

  } catch (e) {
    grid.innerHTML = `<div class="no-data">Failed to load content: ${e.message}</div>`;
  }
}

// ── Tab ───────────────────────────────────────────────────────────
function setTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.tab[data-tab="${tab}"]`).classList.add('active');
  renderGrid();
}

// ── Render ─────────────────────────────────────────────────────────
function renderGrid() {
  const grid  = document.getElementById('media-grid');
  const empty = document.getElementById('empty-state');
  grid.innerHTML = '';
  lightboxItems = [];

  let totalItems = 0;

  allData.forEach(competitor => {
    const sections = getSections(competitor);
    let competitorItems = 0;

    sections.forEach(({ label, type, items }) => {
      const filtered = filterItems(items, type);
      if (filtered.length === 0) return;

      // Section heading (only show when viewing all or multiple sections)
      if (allData.length > 1 || sections.length > 1) {
        const heading = document.createElement('div');
        heading.className = 'grid-section-title';
        heading.innerHTML = `
          <span class="section-badge ${type}">${label}</span>
          <h3>${allData.length > 1 ? '@' + competitor.username + ' — ' : ''}${label}</h3>
        `;
        grid.appendChild(heading);
      }

      filtered.forEach((item, idx) => {
        const globalIdx = lightboxItems.length;
        lightboxItems.push({ ...item, username: competitor.username });
        grid.appendChild(createCard(item, globalIdx));
        competitorItems++;
      });
    });

    totalItems += competitorItems;
  });

  if (totalItems === 0) {
    empty.classList.remove('hidden');
    grid.innerHTML = '';
  } else {
    empty.classList.add('hidden');
  }
}

function getSections(competitor) {
  return [
    { label: 'Stories', type: 'story', items: competitor.stories || [] },
    { label: 'Posts',   type: 'post',  items: competitor.posts   || [] },
    { label: 'Reels',   type: 'reel',  items: competitor.reels   || [] },
  ];
}

function filterItems(items, type) {
  if (activeTab === 'all') return items;
  const map = { stories: 'story', posts: 'post', reels: 'reel' };
  return type === map[activeTab] ? items : [];
}

// ── Card ─────────────────────────────────────────────────────────
function createCard(item, globalIdx) {
  const card = document.createElement('div');
  card.className = 'media-card';
  card.style.animationDelay = `${(globalIdx % 12) * 0.04}s`;

  const typeLabel = item.type;

  if (item.is_video) {
    card.innerHTML = `
      <video src="${item.url}" muted preload="metadata" style="pointer-events:none"></video>
      <div class="play-icon">▶</div>
      <span class="type-badge ${typeLabel}">${typeLabel}</span>
      <div class="media-card-overlay">
        ${item.caption ? `<div class="media-card-caption">${escHtml(item.caption)}</div>` : ''}
        <div class="media-card-meta">
          ${item.timestamp ? `<span>${formatDate(item.timestamp)}</span>` : ''}
          ${item.likes != null ? `<span>♥ ${fmt(item.likes)}</span>` : ''}
        </div>
      </div>
    `;
  } else {
    card.innerHTML = `
      <img src="${item.url}" alt="${typeLabel}" loading="lazy" />
      <span class="type-badge ${typeLabel}">${typeLabel}</span>
      <div class="media-card-overlay">
        ${item.caption ? `<div class="media-card-caption">${escHtml(item.caption)}</div>` : ''}
        <div class="media-card-meta">
          ${item.timestamp ? `<span>${formatDate(item.timestamp)}</span>` : ''}
          ${item.likes != null ? `<span>♥ ${fmt(item.likes)}</span>` : ''}
        </div>
      </div>
    `;
  }

  card.addEventListener('click', () => openLightbox(globalIdx));
  return card;
}

// ── Lightbox ──────────────────────────────────────────────────────
function openLightbox(idx) {
  lightboxIndex = idx;
  renderLightbox();
  document.getElementById('lightbox').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeLightbox(e) {
  if (e && e.target !== document.getElementById('lightbox') && !e.target.classList.contains('lightbox-close')) return;
  document.getElementById('lightbox').classList.remove('open');
  document.body.style.overflow = '';
  // Pause any playing video
  const vid = document.querySelector('#lightbox-media-wrap video');
  if (vid) vid.pause();
}

function renderLightbox() {
  const item = lightboxItems[lightboxIndex];
  if (!item) return;

  const mediaWrap = document.getElementById('lightbox-media-wrap');
  const info      = document.getElementById('lightbox-info');

  if (item.is_video) {
    mediaWrap.innerHTML = `<video src="${item.url}" controls autoplay style="max-height:80vh;max-width:100%;border-radius:12px;"></video>`;
  } else {
    mediaWrap.innerHTML = `<img src="${item.url}" alt="${item.type}" style="max-height:80vh;max-width:100%;border-radius:12px;" />`;
  }

  info.innerHTML = `
    <div class="lightbox-info-row">
      <span class="info-label">Account</span>
      <span class="info-value">@${item.username}</span>
    </div>
    <div class="lightbox-info-row">
      <span class="info-label">Type</span>
      <span class="info-value"><span class="section-badge ${item.type}">${item.type}</span></span>
    </div>
    ${item.timestamp ? `
    <div class="lightbox-info-row">
      <span class="info-label">Date</span>
      <span class="info-value">${formatDateFull(item.timestamp)}</span>
    </div>` : ''}
    ${item.likes != null || item.comments != null ? `
    <div class="info-stats">
      ${item.likes != null ? `<div class="info-stat"><span class="info-stat-val">${fmt(item.likes)}</span><span class="info-stat-key">Likes</span></div>` : ''}
      ${item.comments != null ? `<div class="info-stat"><span class="info-stat-val">${fmt(item.comments)}</span><span class="info-stat-key">Comments</span></div>` : ''}
    </div>` : ''}
    ${item.caption ? `
    <div class="lightbox-info-row">
      <span class="info-label">Caption</span>
      <span class="info-value" style="font-size:12px;color:var(--text2)">${escHtml(item.caption)}</span>
    </div>` : ''}
    ${item.ig_url ? `
    <div class="lightbox-info-row">
      <a class="info-link" href="${item.ig_url}" target="_blank" rel="noopener">↗ View on Instagram</a>
    </div>` : ''}
    <div class="lightbox-info-row" style="margin-top:auto;padding-top:8px;border-top:1px solid var(--border)">
      <span class="info-label">Navigation</span>
      <span class="info-value" style="font-size:11px;color:var(--text3)">${lightboxIndex + 1} of ${lightboxItems.length} — use ← → keys</span>
    </div>
  `;
}

function onKeyDown(e) {
  const lb = document.getElementById('lightbox');
  if (!lb.classList.contains('open')) return;
  if (e.key === 'Escape') { closeLightbox(); return; }
  if (e.key === 'ArrowRight' && lightboxIndex < lightboxItems.length - 1) {
    lightboxIndex++;
    renderLightbox();
  }
  if (e.key === 'ArrowLeft' && lightboxIndex > 0) {
    lightboxIndex--;
    renderLightbox();
  }
}

// ── Refresh ───────────────────────────────────────────────────────
async function refreshData() {
  const btn = document.getElementById('btn-refresh');
  btn.disabled = true;
  await loadStats();
  await loadCompetitors();
  btn.disabled = false;
}

// ── Formatting helpers ────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function fmt(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return (n/1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n/1_000).toFixed(1) + 'K';
  return String(n);
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function formatDateFull(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
