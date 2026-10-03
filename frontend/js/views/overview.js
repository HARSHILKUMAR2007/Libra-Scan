/**
 * Overview Dashboard View
 */

import { fetchStats } from '../api.js';
import { state } from '../state.js';
import { navigateTo, updateSidebarBadges } from '../router.js';
import { getTimeGreeting, formatRelativeTime, animateCounter, escapeHtml } from '../utils.js';
import { FIELD_COLORS } from '../../config.js';

export async function renderOverview() {
  const greetingEl = document.getElementById('overview-greeting');
  if (greetingEl) greetingEl.textContent = `${getTimeGreeting()}, Librarian`;

  const container = document.getElementById('view-overview');
  if (!container) return;

  try {
    const stats = await fetchStats();
    state.setStats(stats);
    updateSidebarBadges(stats.totals.needs_review);

    // Hero Strip: show only when library has fewer than 5 books
    const heroStrip = document.getElementById('overview-hero-strip');
    if (heroStrip) {
      heroStrip.classList.toggle('hidden', stats.totals.books >= 5);
    }

    renderKpiCards(stats);
    renderTrendChart(stats.per_day);
    renderReviewStatus(stats.totals);
    renderRecentScans(stats.recent);
    renderFieldConfidence(stats.field_confidence);
  } catch (err) {
    console.error('Failed to render overview stats:', err);
    renderOverviewError(err);
  }
}

function renderOverviewError(err) {
  const msg = escapeHtml(err?.message || 'Could not load data');
  const errHtml = `
    <div style="text-align: center; padding: 24px; color: var(--muted);">
      <p style="font-size: 13px; font-weight: 600; color: var(--danger); margin-bottom: 4px;">Failed to load data</p>
      <p style="font-size: 12px; margin-bottom: 12px;">${msg}</p>
      <button class="btn btn-outline btn-xs" onclick="window.retryOverview()">Retry</button>
    </div>
  `;
  ['trend-chart-container', 'review-status-list', 'recent-scans-list', 'field-conf-list'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = errHtml;
  });
}

window.retryOverview = renderOverview;

function renderKpiCards(stats) {
  const { totals, avg_confidence } = stats;
  const reviewPct = totals.books > 0 ? Math.round((totals.needs_review / totals.books) * 100) : 0;
  const isbnPct = totals.books > 0 ? Math.round(((totals.books - totals.isbn_missing) / totals.books) * 100) : 0;

  animateCounter(document.getElementById('kpi-books-val'), totals.books);
  document.getElementById('kpi-books-sub').textContent = `${totals.scanned_today} scanned today`;

  animateCounter(document.getElementById('kpi-review-val'), totals.needs_review);
  document.getElementById('kpi-review-sub').textContent = `${reviewPct}% of library`;

  animateCounter(document.getElementById('kpi-conf-val'), Math.round(avg_confidence * 100), 700, '%');
  document.getElementById('kpi-conf-sub').textContent = 'across all fields';

  animateCounter(document.getElementById('kpi-isbn-val'), isbnPct, 700, '%');
  document.getElementById('kpi-isbn-sub').textContent = `${totals.isbn_missing} missing ISBN`;
}

function renderTrendChart(perDay) {
  const container = document.getElementById('trend-chart-container');
  if (!container) return;

  const totalScans = perDay.reduce((acc, d) => acc + d.count, 0);
  if (!totalScans) {
    container.innerHTML = `<div class="chart-empty"><span>No scans in the last 30 days</span></div>`;
    return;
  }

  const w = 560;
  const h = 180;
  const pad = { top: 25, right: 20, bottom: 25, left: 30 };
  const counts = perDay.map(d => d.count);
  const max = Math.max(...counts, 1);
  const peakIdx = counts.indexOf(max);

  const points = perDay.map((d, i) => {
    const x = pad.left + (i / (perDay.length - 1)) * (w - pad.left - pad.right);
    const y = pad.top + (1 - d.count / max) * (h - pad.top - pad.bottom);
    return { x, y, date: d.date, count: d.count };
  });

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(1)} ${h - pad.bottom} L ${points[0].x.toFixed(1)} ${h - pad.bottom} Z`;

  const circles = points.map(p => `
    <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" class="chart-dot" data-date="${p.date}" data-count="${p.count}"/>
  `).join('');

  const peak = points[peakIdx];
  const peakLabel = peak && peak.count > 0 ? `
    <g class="peak-group">
      <rect x="${peak.x - 28}" y="${peak.y - 24}" width="56" height="18" rx="4" class="peak-badge"/>
      <text x="${peak.x}" y="${peak.y - 12}" text-anchor="middle" class="peak-text">Peak: ${peak.count}</text>
    </g>
  ` : '';

  container.innerHTML = `
    <svg viewBox="0 0 ${w} ${h}" class="trend-svg" preserveAspectRatio="none">
      <defs>
        <linearGradient id="area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.32"/>
          <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      <line x1="${pad.left}" y1="${h - pad.bottom}" x2="${w - pad.right}" y2="${h - pad.bottom}" class="chart-axis"/>
      <path d="${areaPath}" fill="url(#area-grad)"/>
      <path d="${linePath}" fill="none" class="chart-line"/>
      ${circles}
      ${peakLabel}
    </svg>
    <div id="chart-tooltip" class="chart-tooltip hidden"></div>
  `;

  setupChartInteractions(container);
}

function setupChartInteractions(container) {
  const tooltip = container.querySelector('#chart-tooltip');
  const dots = container.querySelectorAll('.chart-dot');
  dots.forEach(dot => {
    dot.addEventListener('mouseenter', e => {
      const rect = container.getBoundingClientRect();
      const dotRect = dot.getBoundingClientRect();
      tooltip.textContent = `${dot.dataset.date}: ${dot.dataset.count} scans`;
      tooltip.style.left = `${dotRect.left - rect.left}px`;
      tooltip.style.top = `${dotRect.top - rect.top - 28}px`;
      tooltip.classList.remove('hidden');
    });
    dot.addEventListener('mouseleave', () => tooltip.classList.add('hidden'));
  });
}

function renderReviewStatus(totals) {
  const container = document.getElementById('review-status-list');
  if (!container) return;
  const total = Math.max(totals.books, 1);
  const items = [
    { label: 'Confirmed', count: totals.confirmed, color: 'var(--ok)', pillClass: 'pill-confirmed' },
    { label: 'Needs review', count: totals.needs_review, color: 'var(--warn)', pillClass: 'pill-review' },
    { label: 'Pending', count: totals.pending, color: 'var(--muted)', pillClass: 'pill-pending' },
  ];

  container.innerHTML = items.map(item => {
    const pct = Math.round((item.count / total) * 100);
    return `
      <div class="status-row">
        <div class="status-info">
          <span class="status-pill ${item.pillClass}">${item.label}</span>
          <span class="status-count">${item.count} <small class="text-muted">(${pct}%)</small></span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" style="width: ${pct}%; background-color: ${item.color};"></div>
        </div>
      </div>
    `;
  }).join('');
}

function renderRecentScans(books) {
  const list = document.getElementById('recent-scans-list');
  if (!list) return;
  if (!books || !books.length) {
    list.innerHTML = `<div class="empty-hint">No recent scans. Upload covers to start cataloging!</div>`;
    return;
  }

  list.innerHTML = books.map(b => `
    <div class="recent-book-card" onclick="window.location.hash='#scan'; window.dispatchEvent(new CustomEvent('load-book', {detail: ${b.id}}))">
      <img src="${b.front_image_url}" class="recent-thumb" alt="Cover" onerror="this.style.display='none'"/>
      <div class="recent-meta">
        <h4 class="recent-title">${escapeHtml(b.title || 'Untitled')}</h4>
        <p class="recent-author">${escapeHtml((b.authors || []).join(', ') || 'Unknown Author')}</p>
        <span class="recent-time">${formatRelativeTime(b.created_at)}</span>
      </div>
      <div class="recent-badges">
        <span class="status-pill ${b.needs_review ? 'pill-review' : 'pill-confirmed'}">${b.needs_review ? 'Review' : 'OK'}</span>
        <span class="conf-badge">${Math.round((b.confidence || 0) * 100)}%</span>
      </div>
    </div>
  `).join('');
}

function renderFieldConfidence(fieldConf) {
  const container = document.getElementById('field-conf-list');
  if (!container) return;
  const fields = ['title', 'authors', 'publisher', 'isbn13', 'year', 'language'];

  container.innerHTML = fields.map(f => {
    const score = fieldConf?.[f] ?? 0;
    const pct = Math.round(score * 100);
    const color = FIELD_COLORS[f] || 'var(--accent)';
    return `
      <div class="field-bar-item">
        <div class="field-bar-header">
          <span class="field-bar-label">${f.toUpperCase()}</span>
          <span class="field-bar-val" style="color: ${color};">${pct}%</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" style="width: ${pct}%; background-color: ${color};"></div>
        </div>
      </div>
    `;
  }).join('');
}
