/**
 * Library Catalog & Review Queue Controller
 */

import { fetchBooks, fetchBook, deleteBook, getExportCsvUrl } from '../api.js';
import { state } from '../state.js';
import { showToast } from '../toast.js';
import { navigateTo, updateSidebarBadges } from '../router.js';
import { escapeHtml } from '../utils.js';
import { CONFIG } from '../../config.js';

let isReviewQueueMode = false;

export async function loadLibraryView(reviewQueueMode = false) {
  isReviewQueueMode = reviewQueueMode;

  const titleEl = document.getElementById('library-view-title') || document.getElementById('main-page-title');
  const subtitleEl = document.getElementById('library-view-subtitle') || document.getElementById('main-page-subtitle');
  const filterStatus = document.getElementById('library-status-filter');

  if (titleEl) titleEl.textContent = reviewQueueMode ? 'Review Queue' : 'Library Catalog';
  if (subtitleEl) {
    subtitleEl.textContent = reviewQueueMode
      ? 'Books requiring librarian verification, prioritized by lowest confidence'
      : 'Cataloged books repository and verification records';
  }
  if (filterStatus) filterStatus.style.display = reviewQueueMode ? 'none' : 'block';

  try {
    const status = reviewQueueMode ? '' : (filterStatus ? filterStatus.value : '');
    const books = await fetchBooks(status);
    state.setLibraryBooks(books);

    // Update sidebar badge
    const reviewCount = books.filter(b => b.needs_review).length;
    updateSidebarBadges(reviewCount);

    filterAndRenderLibrary();
  } catch (err) {
    showToast('Failed to load library catalog', 'error');
  }

  setupLibraryListeners();
}

function setupLibraryListeners() {
  const searchInput = document.getElementById('library-search');
  const statusFilter = document.getElementById('library-status-filter');
  const exportBtn = document.getElementById('btn-export-csv');

  if (searchInput) searchInput.oninput = () => filterAndRenderLibrary();
  if (statusFilter) statusFilter.onchange = () => loadLibraryView(isReviewQueueMode);
  if (exportBtn) exportBtn.onclick = () => { window.location.href = getExportCsvUrl(); };
}

export function filterAndRenderLibrary() {
  const query = (document.getElementById('library-search')?.value || '').toLowerCase().trim();
  let list = [...state.libraryBooks];

  if (isReviewQueueMode) {
    list = list.filter(b => b.needs_review);
    // Sort by lowest confidence first
    list.sort((a, b) => (a.confidence || 0) - (b.confidence || 0));
  }

  if (query) {
    list = list.filter(b =>
      (b.title || '').toLowerCase().includes(query) ||
      (b.authors || []).join(' ').toLowerCase().includes(query) ||
      (b.publisher || '').toLowerCase().includes(query) ||
      (b.isbn13 || '').includes(query) ||
      (b.isbn10 || '').includes(query)
    );
  }

  const tbody = document.getElementById('library-tbody');
  const emptyEl = document.getElementById('library-empty');
  if (!tbody) return;

  if (!list.length) {
    tbody.innerHTML = '';
    if (emptyEl) {
      emptyEl.classList.remove('hidden');
      const emptyTitle = emptyEl.querySelector('h3');
      const emptyText = emptyEl.querySelector('p');
      if (emptyTitle) emptyTitle.textContent = isReviewQueueMode ? 'No items in review queue' : 'No books found';
      if (emptyText) emptyText.textContent = isReviewQueueMode ? 'All scanned books have high confidence.' : 'Scan a cover to catalog your first book.';
    }
    return;
  }

  if (emptyEl) emptyEl.classList.add('hidden');

  tbody.innerHTML = list.map(b => `
    <tr class="table-row" data-id="${b.id}">
      <td>
        <img src="${b.front_image_url}" class="thumb" alt="Cover" onerror="this.src=''"/>
      </td>
      <td>
        <div class="table-title">${escapeHtml(b.title || 'Untitled')}</div>
        ${b.subtitle ? `<div class="table-subtitle">${escapeHtml(b.subtitle)}</div>` : ''}
      </td>
      <td>${escapeHtml((b.authors || []).join(', ') || '-')}</td>
      <td><code>${escapeHtml(b.isbn13 || b.isbn10 || '-')}</code></td>
      <td>${b.year || '-'}</td>
      <td><span class="status-pill ${b.status === 'confirmed' ? 'pill-confirmed' : 'pill-pending'}">${b.status}</span></td>
      <td>${b.needs_review ? '<span class="status-pill pill-review">Review</span>' : '<span class="status-pill pill-confirmed">OK</span>'}</td>
      <td><span class="conf-badge">${Math.round((b.confidence || 0) * 100)}%</span></td>
      <td>
        <div class="row-actions">
          <button class="btn btn-outline btn-xs" onclick="event.stopPropagation(); window.openReviewBook(${b.id}, '${isReviewQueueMode ? 'review' : 'library'}')">Review</button>
          <button class="btn btn-danger-ghost btn-xs" onclick="event.stopPropagation(); window.deleteLibraryBook(${b.id}, '${escapeHtml(b.title || 'book')}')">Delete</button>
        </div>
      </td>
    </tr>
  `).join('');

  // Row click to review
  tbody.querySelectorAll('.table-row').forEach(tr => {
    tr.onclick = () => {
      const id = tr.dataset.id;
      if (id) window.openReviewBook(id, isReviewQueueMode ? 'review' : 'library');
    };
  });
}

// Global actions for inline event handlers
window.openReviewBook = async (id, origin = null) => {
  state.openedFrom = origin || (isReviewQueueMode ? 'review' : 'library');
  navigateTo('scan');
  window.dispatchEvent(new CustomEvent('load-book', { detail: id }));
};

window.deleteLibraryBook = (id, title) => {
  // Remove from state immediately
  const originalList = [...state.libraryBooks];
  state.setLibraryBooks(originalList.filter(b => b.id !== id));
  filterAndRenderLibrary();

  let isUndone = false;
  const timer = setTimeout(async () => {
    if (!isUndone) {
      try {
        await deleteBook(id);
      } catch (err) {
        showToast(`Failed to delete book #${id}`, 'error');
      }
    }
  }, CONFIG.UNDO_TIMEOUT_MS);

  showToast(`Deleted "${title}"`, 'info', {
    text: 'Undo (5s)',
    onClick: () => {
      isUndone = true;
      clearTimeout(timer);
      state.setLibraryBooks(originalList);
      filterAndRenderLibrary();
      showToast('Book restored.', 'success');
    }
  }, CONFIG.UNDO_TIMEOUT_MS);
};
