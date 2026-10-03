/**
 * LibraScan - Main Application Entrypoint
 */

import { CONFIG } from '../config.js';
import { initTheme } from './theme.js';
import { initRouter, navigateTo, toggleSidebar } from './router.js';
import { startExtraction, removeSide, saveAndConfirm, deleteCurrentBook, resetToScan } from './views/scan.js';
import { switchSide } from './views/viewer.js';
import { initBulkUpload } from './bulk.js';
import { updateActiveSidebarBadge } from './queue.js';

document.addEventListener('DOMContentLoaded', () => {
  // Set title and branding
  document.title = CONFIG.APP_NAME;

  initTheme();
  initRouter();
  initBulkUpload();
  updateActiveSidebarBadge();

  // Global search shortcut (Ctrl+K or '/')
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && document.activeElement.tagName !== 'INPUT')) {
      e.preventDefault();
      navigateTo('library');
      setTimeout(() => {
        const searchInput = document.getElementById('library-search');
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
      }, 50);
    }
  });

  // Expose compatibility helpers to window for template event handlers
  window.navigateTo = navigateTo;
  window.toggleSidebar = toggleSidebar;
  window.startExtraction = startExtraction;
  window.removeSide = removeSide;
  window.saveAndConfirm = saveAndConfirm;
  window.deleteCurrentBook = deleteCurrentBook;
  window.resetToScan = resetToScan;
  window.switchViewerSide = switchSide;
});
