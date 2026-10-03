/**
 * Insights & Analytics View Controller
 */

import { fetchStats } from '../api.js';
import { state } from '../state.js';
import { escapeHtml } from '../utils.js';

export async function renderInsights() {
  const container = document.getElementById('insights-grid');
  if (!container) return;

  try {
    let stats = state.statsData;
    if (!stats) {
      stats = await fetchStats();
      state.setStats(stats);
    }

    renderRankedList('top-authors-card', 'Top Authors', stats.top_authors, 'Author');
    renderRankedList('top-publishers-card', 'Top Publishers', stats.top_publishers, 'Publisher');
    renderLanguageSplit('languages-card', stats.languages);
    renderYearsBarChart('years-card', stats.years);
  } catch (err) {
    console.error('Failed to render insights:', err);
  }
}

function renderRankedList(containerId, title, items, singular) {
  const card = document.getElementById(containerId);
  if (!card) return;

  if (!items || !items.length) {
    card.innerHTML = `
      <div class="card-header"><h3 class="card-title">${title}</h3></div>
      <div class="empty-hint">No ${singular.toLowerCase()} data available yet.</div>
    `;
    return;
  }

  const max = Math.max(...items.map(i => i.count), 1);
  const rows = items.map((item, idx) => {
    const pct = Math.round((item.count / max) * 100);
    return `
      <div class="insight-row">
        <div class="insight-rank">#${idx + 1}</div>
        <div class="insight-info">
          <div class="insight-label-row">
            <span class="insight-name">${escapeHtml(item.name)}</span>
            <span class="insight-count">${item.count} books</span>
          </div>
          <div class="progress-track">
            <div class="progress-bar" style="width: ${pct}%; background-color: var(--accent);"></div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  card.innerHTML = `
    <div class="card-header"><h3 class="card-title">${title}</h3></div>
    <div class="insight-list">${rows}</div>
  `;
}

function renderLanguageSplit(containerId, languages) {
  const card = document.getElementById(containerId);
  if (!card) return;

  if (!languages || !languages.length) {
    card.innerHTML = `
      <div class="card-header"><h3 class="card-title">Language Distribution</h3></div>
      <div class="empty-hint">No language information cataloged yet.</div>
    `;
    return;
  }

  const total = languages.reduce((acc, l) => acc + l.count, 0) || 1;
  const rows = languages.map(lang => {
    const pct = Math.round((lang.count / total) * 100);
    return `
      <div class="insight-row">
        <div class="insight-info">
          <div class="insight-label-row">
            <span class="insight-name">${escapeHtml(lang.name)}</span>
            <span class="insight-count">${lang.count} (${pct}%)</span>
          </div>
          <div class="progress-track">
            <div class="progress-bar" style="width: ${pct}%; background-color: var(--accent);"></div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  card.innerHTML = `
    <div class="card-header"><h3 class="card-title">Language Distribution</h3></div>
    <div class="insight-list">${rows}</div>
  `;
}

function renderYearsBarChart(containerId, years) {
  const card = document.getElementById(containerId);
  if (!card) return;

  if (!years || !years.length) {
    card.innerHTML = `
      <div class="card-header"><h3 class="card-title">Publication Years</h3></div>
      <div class="empty-hint">No publication years recorded yet.</div>
    `;
    return;
  }

  const w = 480, h = 180;
  const pad = { top: 20, right: 15, bottom: 30, left: 30 };
  const max = Math.max(...years.map(y => y.count), 1);
  const barWidth = Math.max(14, Math.floor((w - pad.left - pad.right) / years.length) - 8);

  const bars = years.map((y, i) => {
    const x = pad.left + i * ((w - pad.left - pad.right) / years.length) + 4;
    const barH = Math.max(4, (y.count / max) * (h - pad.top - pad.bottom));
    const yPos = h - pad.bottom - barH;
    return `
      <g class="bar-group">
        <rect x="${x}" y="${yPos}" width="${barWidth}" height="${barH}" rx="4" class="chart-bar"/>
        <text x="${x + barWidth / 2}" y="${h - pad.bottom + 16}" text-anchor="middle" class="bar-axis-text">${y.year}</text>
        <text x="${x + barWidth / 2}" y="${yPos - 6}" text-anchor="middle" class="bar-val-text">${y.count}</text>
      </g>
    `;
  }).join('');

  card.innerHTML = `
    <div class="card-header"><h3 class="card-title">Publication Years</h3></div>
    <div class="chart-svg-wrap">
      <svg viewBox="0 0 ${w} ${h}" class="years-svg" preserveAspectRatio="none">
        <line x1="${pad.left}" y1="${h - pad.bottom}" x2="${w - pad.right}" y2="${h - pad.bottom}" class="chart-axis"/>
        ${bars}
      </svg>
    </div>
  `;
}
