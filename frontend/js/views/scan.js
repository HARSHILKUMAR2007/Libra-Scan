/**
 * New Scan & Review Form Controller
 */

import { CONFIG, FIELD_COLORS } from '../../config.js';
import { state } from '../state.js';
import { showToast } from '../toast.js';
import { navigateTo } from '../router.js';
import { uploadBookImages, updateBook, deleteBook, fetchBook } from '../api.js';
import { formatFileSize } from '../utils.js';
import { initViewer, renderViewerBook, switchSide, resetViewer } from './viewer.js';

let isInitialized = false;

export function initScanView() {
  if (isInitialized) return;
  isInitialized = true;

  initViewer();
  setupDropZone('front');
  setupDropZone('back');
  setupPhotoTips();
  setupKeyboardShortcuts();

  window.addEventListener('load-book', async (e) => {
    const bookId = e.detail;
    try {
      const book = await fetchBook(bookId);
      displayBookReview(book);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
}

function setupDropZone(side) {
  const dropZone = document.getElementById(`drop-${side}`);
  const fileInput = document.getElementById(`file-${side}`);
  const cameraInput = document.getElementById(`camera-${side}`);
  const replaceInput = document.getElementById(`replace-${side}`);

  if (!dropZone) return;

  dropZone.onclick = e => {
    if (e.target.closest('.preview-actions') || e.target.tagName === 'INPUT' || e.target.closest('.camera-btn')) return;
    const hasFile = side === 'front' ? state.frontFile : state.backFile;
    if (!hasFile && fileInput) fileInput.click();
  };

  dropZone.ondragover = e => { e.preventDefault(); dropZone.classList.add('dragover'); };
  dropZone.ondragleave = () => dropZone.classList.remove('dragover');
  dropZone.ondrop = e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) handleFile(side, e.dataTransfer.files[0]);
  };

  const bindChange = input => {
    if (input) input.onchange = e => { if (e.target.files[0]) handleFile(side, e.target.files[0]); };
  };
  bindChange(fileInput);
  bindChange(cameraInput);
  bindChange(replaceInput);
}

function handleFile(side, file) {
  const errEl = document.getElementById(`error-${side}`);
  if (errEl) errEl.classList.add('hidden');

  if (!CONFIG.ALLOWED_MIME.includes(file.type)) {
    if (errEl) {
      errEl.textContent = 'Invalid format. Only JPEG, PNG, and WEBP are supported.';
      errEl.classList.remove('hidden');
    }
    return;
  }
  if (file.size > CONFIG.MAX_UPLOAD_MB * 1024 * 1024) {
    if (errEl) {
      errEl.textContent = `File too large. Maximum size is ${CONFIG.MAX_UPLOAD_MB}MB.`;
      errEl.classList.remove('hidden');
    }
    return;
  }

  if (side === 'front') state.frontFile = file;
  else state.backFile = file;

  document.getElementById(`drop-content-${side}`).classList.add('hidden');
  const previewBox = document.getElementById(`preview-box-${side}`);
  previewBox.classList.remove('hidden');

  const reader = new FileReader();
  reader.onload = ev => { document.getElementById(`thumb-${side}`).src = ev.target.result; };
  reader.readAsDataURL(file);

  document.getElementById(`name-${side}`).textContent = file.name;
  document.getElementById(`size-${side}`).textContent = formatFileSize(file.size);
  updateExtractBtn();
}

export function removeSide(side) {
  if (side === 'front') state.frontFile = null;
  else state.backFile = null;

  ['file', 'camera', 'replace'].forEach(prefix => {
    const input = document.getElementById(`${prefix}-${side}`);
    if (input) input.value = '';
  });

  const previewBox = document.getElementById(`preview-box-${side}`);
  const dropContent = document.getElementById(`drop-content-${side}`);
  if (previewBox) previewBox.classList.add('hidden');
  if (dropContent) dropContent.classList.remove('hidden');
  updateExtractBtn();
}

function updateExtractBtn() {
  const btn = document.getElementById('btn-extract');
  if (!btn) return;
  if (!state.frontFile) {
    btn.disabled = true;
    btn.textContent = 'Extract Details (Front required)';
  } else if (state.backFile) {
    btn.disabled = false;
    btn.textContent = 'Extract Details (Front + Back)';
  } else {
    btn.disabled = false;
    btn.textContent = 'Extract Details (Front only)';
  }
}

export async function startExtraction() {
  if (!state.frontFile) return;
  state.openedFrom = null;

  const uploadStep = document.getElementById('upload-step-section');
  const progress = document.getElementById('progress-container');
  const reviewLayout = document.getElementById('review-container');

  uploadStep.classList.add('hidden');
  progress.classList.remove('hidden');
  reviewLayout.classList.add('hidden');

  const step1 = document.getElementById('step-1');
  const step2 = document.getElementById('step-2');
  const step3 = document.getElementById('step-3');

  step1.className = 'step-item active';
  step2.className = 'step-item';
  step3.className = 'step-item';

  const t1 = setTimeout(() => {
    step1.className = 'step-item completed';
    step2.className = 'step-item active';
  }, 1000);

  const t2 = setTimeout(() => {
    step2.className = 'step-item completed';
    step3.className = 'step-item active';
  }, 2400);

  try {
    const book = await uploadBookImages(state.frontFile, state.backFile);
    clearTimeout(t1);
    clearTimeout(t2);
    progress.classList.add('hidden');
    displayBookReview(book);
    showToast('Cover details extracted successfully!', 'success');
  } catch (err) {
    clearTimeout(t1);
    clearTimeout(t2);
    progress.classList.add('hidden');
    uploadStep.classList.remove('hidden');
    showToast(err.message, 'error');
  }
}

export function displayBookReview(book) {
  state.setCurrentBook(book);
  document.getElementById('upload-step-section').classList.add('hidden');
  document.getElementById('progress-container').classList.add('hidden');
  document.getElementById('review-container').classList.remove('hidden');

  renderViewerBook(book);

  // Populate form fields
  for (const [key] of Object.entries(FIELD_COLORS)) {
    const input = document.getElementById(`field-${key}`);
    const badge = document.getElementById(`badge-${key}`);
    const chipsContainer = document.getElementById(`chips-${key}`);
    const fieldData = book.field_boxes?.[key] || {};

    let val = (fieldData.value !== undefined && fieldData.value !== null && fieldData.value !== '')
      ? fieldData.value
      : (book[key] !== undefined && book[key] !== null ? book[key] : '');

    // Intelligent client fallback: if field is empty, inspect book.ocr_lines
    if ((val === '' || val === null || (Array.isArray(val) && val.length === 0)) && book.ocr_lines?.length) {
      if (key === 'isbn13' || key === 'isbn10') {
        const fullOcr = book.ocr_lines.map(l => l.text).join(' ');
        const m13 = fullOcr.match(/97[89][-\s\d]{10,14}/);
        if (m13 && key === 'isbn13') {
          val = m13[0].replace(/[^0-9X]/gi, '');
        }
      } else if (key === 'year') {
        for (const l of book.ocr_lines) {
          const ym = l.text.match(/\b(19\d{2}|20[0-2]\d)\b/);
          if (ym) { val = parseInt(ym[1]); break; }
        }
      } else if (key === 'language') {
        val = 'English';
      } else if (key === 'title') {
        const frontLines = book.ocr_lines.filter(l => l.image === 'front');
        if (frontLines.length) {
          const sorted = [...frontLines].sort((a, b) => (b.bbox[3] - b.bbox[1]) - (a.bbox[3] - a.bbox[1]));
          val = sorted[0].text;
        }
      }
    }

    if (Array.isArray(val)) val = val.join(', ');
    if (input) input.value = (val !== null && val !== undefined) ? val : '';

    const conf = fieldData.confidence !== undefined ? fieldData.confidence : (val ? 0.9 : 0.0);
    if (badge) {
      if (val) {
        badge.textContent = `${Math.round(conf * 100)}%`;
        badge.className = `badge ${conf >= 0.85 ? 'badge-green' : conf >= 0.6 ? 'badge-amber' : 'badge-red'}`;
      } else {
        badge.textContent = 'Not found';
        badge.className = 'badge badge-muted';
      }
    }

    if (chipsContainer) {
      const boxes = fieldData.boxes || [];
      const hasFront = boxes.some(b => b.image === 'front');
      const hasBack = boxes.some(b => b.image === 'back');
      chipsContainer.innerHTML = '';
      if (hasFront) {
        chipsContainer.innerHTML += `<span class="source-chip chip-front" style="cursor:pointer;" title="View on front cover" onclick="window.switchViewerSide('front')">Front</span>`;
      }
      if (hasBack) {
        chipsContainer.innerHTML += `<span class="source-chip chip-back" style="cursor:pointer;" title="View on back cover" onclick="window.switchViewerSide('back')">Back</span>`;
      }
    }
  }

  // Warnings banner
  const warnBanner = document.getElementById('review-alert');
  const warnList = document.getElementById('warning-list');
  if (book.needs_review && book.warnings?.length) {
    warnList.innerHTML = book.warnings.map(w => `<li>${w}</li>`).join('');
    warnBanner.classList.remove('hidden');
  } else {
    warnBanner.classList.add('hidden');
  }

  document.getElementById('raw-json-viewer').textContent = JSON.stringify(book.field_boxes || book, null, 2);
}

export async function saveAndConfirm() {
  if (!state.currentBook) return;
  const payload = {
    title: document.getElementById('field-title')?.value || null,
    subtitle: document.getElementById('field-subtitle')?.value || null,
    authors: (document.getElementById('field-authors')?.value || '').split(',').map(s => s.trim()).filter(Boolean),
    publisher: document.getElementById('field-publisher')?.value || null,
    isbn10: document.getElementById('field-isbn10')?.value || null,
    isbn13: document.getElementById('field-isbn13')?.value || null,
    year: parseInt(document.getElementById('field-year')?.value) || null,
    edition: document.getElementById('field-edition')?.value || null,
    language: document.getElementById('field-language')?.value || null,
    series: document.getElementById('field-series')?.value || null,
    status: 'confirmed'
  };

  try {
    const updated = await updateBook(state.currentBook.id, payload);
    state.setCurrentBook(updated);
    showToast('Book confirmed and catalog entry saved!', 'success');

    const returnTo = state.openedFrom;
    state.openedFrom = null;

    resetToScan();

    if (returnTo === 'library' || returnTo === 'review') {
      navigateTo(returnTo);
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

export function deleteCurrentBook() {
  if (!state.currentBook) return;
  const bookId = state.currentBook.id;
  const bookTitle = state.currentBook.title || 'Untitled book';

  // 5-second Undo mechanism
  resetToScan();

  let isUndone = false;
  const timer = setTimeout(async () => {
    if (!isUndone) {
      try {
        await deleteBook(bookId);
      } catch (err) {
        showToast(`Failed to permanently delete #${bookId}`, 'error');
      }
    }
  }, CONFIG.UNDO_TIMEOUT_MS);

  showToast(`Deleted "${bookTitle}"`, 'info', {
    text: 'Undo (5s)',
    onClick: async () => {
      isUndone = true;
      clearTimeout(timer);
      try {
        const restored = await fetchBook(bookId);
        displayBookReview(restored);
        showToast('Deletion undone.', 'success');
      } catch (err) {
        showToast('Could not restore book.', 'error');
      }
    }
  }, CONFIG.UNDO_TIMEOUT_MS);
}

export function resetToScan() {
  state.currentBook = null;
  state.frontFile = null;
  state.backFile = null;
  removeSide('front');
  removeSide('back');
  resetViewer();

  // Clear form fields, badges, and source chips
  for (const [key] of Object.entries(FIELD_COLORS)) {
    const input = document.getElementById(`field-${key}`);
    const badge = document.getElementById(`badge-${key}`);
    const chips = document.getElementById(`chips-${key}`);
    if (input) input.value = '';
    if (badge) {
      badge.textContent = '';
      badge.className = 'badge';
    }
    if (chips) chips.innerHTML = '';
  }

  const rawJson = document.getElementById('raw-json-viewer');
  if (rawJson) rawJson.textContent = '';

  const warnBanner = document.getElementById('review-alert');
  if (warnBanner) warnBanner.classList.add('hidden');
  const warnList = document.getElementById('warning-list');
  if (warnList) warnList.innerHTML = '';

  document.getElementById('review-container')?.classList.add('hidden');
  document.getElementById('progress-container')?.classList.add('hidden');
  document.getElementById('upload-step-section')?.classList.remove('hidden');
  updateExtractBtn();
}

function setupPhotoTips() {
  const tipsCard = document.getElementById('photo-tips-banner');
  const dismissBtn = document.getElementById('photo-tips-dismiss');
  if (localStorage.getItem('librascan-tips-dismissed') === 'true') {
    if (tipsCard) tipsCard.classList.add('hidden');
  }
  if (dismissBtn && tipsCard) {
    dismissBtn.onclick = () => {
      tipsCard.classList.add('hidden');
      localStorage.setItem('librascan-tips-dismissed', 'true');
    };
  }
}

function setupKeyboardShortcuts() {
  document.addEventListener('keydown', e => {
    // Only apply in review view
    const reviewView = document.getElementById('review-container');
    if (!reviewView || reviewView.classList.contains('hidden')) return;

    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      saveAndConfirm();
    } else if (e.key === 'Escape') {
      if (document.activeElement && document.activeElement.tagName === 'INPUT') {
        document.activeElement.value = '';
        e.preventDefault();
      }
    }
  });
}
