/**
 * Hash-based Application Router
 */

import { state } from './state.js';
import { renderOverview } from './views/overview.js';
import { initScanView } from './views/scan.js';
import { loadLibraryView } from './views/library.js';
import { renderInsights } from './views/insights.js';

export const ROUTES = {
  overview: { id: 'view-overview', title: 'Library Overview', nav: 'nav-overview-btn' },
  scan: { id: 'view-scan', title: 'New Scan', nav: 'nav-scan-btn' },
  library: { id: 'view-library', title: 'Library Catalog', nav: 'nav-library-btn' },
  review: { id: 'view-library', title: 'Review Queue', nav: 'nav-review-btn' },
  insights: { id: 'view-insights', title: 'Catalog Insights', nav: 'nav-insights-btn' }
};

export function initRouter() {
  window.addEventListener('hashchange', handleRoute);
  document.getElementById('nav-overview-btn')?.addEventListener('click', () => {
    if (window.location.hash === '#overview' || !window.location.hash) {
      renderOverview();
    }
  });
  if (!window.location.hash || !ROUTES[window.location.hash.slice(1)]) {
    window.location.hash = '#overview';
  }
  handleRoute();
}

export function navigateTo(route) {
  window.location.hash = `#${route}`;
}

export function handleRoute() {
  const hash = (window.location.hash || '#overview').slice(1);
  const route = ROUTES[hash] ? hash : 'overview';

  // Toggle active view sections and navigation items
  const activeViewId = ROUTES[route]?.id || 'view-overview';
  const allViewIds = new Set(Object.values(ROUTES).map(r => r.id));
  allViewIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active', id === activeViewId);
  });

  Object.keys(ROUTES).forEach(r => {
    const navBtn = document.getElementById(ROUTES[r].nav);
    if (navBtn) navBtn.classList.toggle('active', r === route);
  });

  // Update topbar headers
  const titleEl = document.getElementById('main-page-title');
  const subEl = document.getElementById('main-page-subtitle');
  if (titleEl && subEl) {
    if (route === 'overview') {
      titleEl.textContent = 'Library Overview';
      subEl.textContent = 'Books cataloged from front and back cover scans, with AI extraction';
    } else if (route === 'scan') {
      titleEl.textContent = 'New Scan';
      subEl.textContent = 'Upload front and back covers for merged OCR and catalog extraction';
    } else if (route === 'library') {
      titleEl.textContent = 'Library Catalog';
      subEl.textContent = 'Cataloged books repository and verification records';
    } else if (route === 'review') {
      titleEl.textContent = 'Review Queue';
      subEl.textContent = 'Books requiring librarian verification, prioritized by lowest confidence';
    } else if (route === 'insights') {
      titleEl.textContent = 'Catalog Insights';
      subEl.textContent = 'Distribution analysis of authors, publishers, and publication years';
    }
  }

  // Close mobile sidebar
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.classList.remove('open');

  // Trigger view renderers
  if (route === 'overview') {
    renderOverview();
  } else if (route === 'scan') {
    initScanView();
  } else if (route === 'library') {
    loadLibraryView(false);
  } else if (route === 'review') {
    loadLibraryView(true);
  } else if (route === 'insights') {
    renderInsights();
  }
}

export function updateSidebarBadges(needsReviewCount) {
  const badge = document.getElementById('nav-review-badge');
  if (badge) {
    if (needsReviewCount > 0) {
      badge.textContent = needsReviewCount;
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  }
}

export function toggleSidebar(forceOpen) {
  const sb = document.getElementById('sidebar');
  if (!sb) return;
  if (typeof forceOpen === 'boolean') {
    sb.classList.toggle('open', forceOpen);
  } else {
    sb.classList.toggle('open');
  }
}
