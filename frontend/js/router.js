/**
 * Hash-based Application Router
 */

import { state } from './state.js';
import { renderOverview } from './views/overview.js';
import { initScanView } from './views/scan.js';
import { loadLibraryView } from './views/library.js';
import { renderInsights } from './views/insights.js';

export const ROUTES = {
  overview: { id: 'view-overview', title: 'Library Overview', nav: 'nav-overview-btn', mobNav: 'mob-nav-overview' },
  scan: { id: 'view-scan', title: 'New Scan', nav: 'nav-scan-btn', mobNav: 'mob-nav-scan' },
  library: { id: 'view-library', title: 'Library Catalog', nav: 'nav-library-btn', mobNav: 'mob-nav-library' },
  review: { id: 'view-library', title: 'Review Queue', nav: 'nav-review-btn', mobNav: 'mob-nav-review' },
  insights: { id: 'view-insights', title: 'Catalog Insights', nav: 'nav-insights-btn', mobNav: 'mob-nav-insights' }
};

export function initRouter() {
  window.addEventListener('hashchange', handleRoute);
  document.getElementById('nav-overview-btn')?.addEventListener('click', () => {
    if (window.location.hash === '#overview' || !window.location.hash) {
      renderOverview();
    }
  });
  document.getElementById('mob-nav-overview')?.addEventListener('click', () => {
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

  // Toggle active view sections
  const activeViewId = ROUTES[route]?.id || 'view-overview';
  const allViewIds = new Set(Object.values(ROUTES).map(r => r.id));
  allViewIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active', id === activeViewId);
  });

  // Toggle sidebar navigation items and mobile bottom nav items
  Object.keys(ROUTES).forEach(r => {
    const navBtn = document.getElementById(ROUTES[r].nav);
    if (navBtn) navBtn.classList.toggle('active', r === route);

    const mobNavBtn = document.getElementById(ROUTES[r].mobNav);
    if (mobNavBtn) mobNavBtn.classList.toggle('active', r === route);
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

  // Close mobile sidebar and backdrop
  toggleSidebar(false);

  // Scroll to top of content smoothly
  window.scrollTo({ top: 0, behavior: 'instant' });

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
  const mobBadge = document.getElementById('mob-nav-review-badge');

  [badge, mobBadge].forEach(b => {
    if (b) {
      if (needsReviewCount > 0) {
        b.textContent = needsReviewCount;
        b.classList.remove('hidden');
      } else {
        b.classList.add('hidden');
      }
    }
  });
}

export function toggleSidebar(forceOpen) {
  const sb = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (!sb) return;

  const willOpen = typeof forceOpen === 'boolean' ? forceOpen : !sb.classList.contains('open');
  sb.classList.toggle('open', willOpen);
  if (backdrop) backdrop.classList.toggle('open', willOpen);
  document.body.classList.toggle('sidebar-locked', willOpen);
}