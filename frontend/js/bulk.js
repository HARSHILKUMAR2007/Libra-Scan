/**
 * Bulk Upload Controller - Multi-file selection, auto-pairing, and batch submission
 */

import { CONFIG } from '../config.js';
import { pairFiles, parseFileName } from './pairing.js';
import { createBatch } from './api.js';
import { showToast } from './toast.js';
import { showQueueView } from './queue.js';
import { escapeHtml } from './utils.js';

let stagedPairs = [];
let unpairedFiles = [];
let rawFiles = [];
let bulkSubmode = 'front_back'; // 'front_only' | 'front_back'

export function initBulkUpload() {
  setupBulkModeToggle();
  setupBulkSubmodeToggle();
  setupBulkDropZone();
  setupReviewActions();

  // If there is an active batch in progress, resume queue view
  const activeBatchId = localStorage.getItem('librascan_active_batch_id');
  if (activeBatchId) {
    showQueueView(parseInt(activeBatchId, 10));
  }
}

function setupBulkSubmodeToggle() {
  const frontOnlyBtn = document.getElementById('btn-bulk-front-only');
  const frontBackBtn = document.getElementById('btn-bulk-front-back');

  if (frontOnlyBtn && frontBackBtn) {
    frontOnlyBtn.onclick = () => {
      if (bulkSubmode === 'front_only') return;
      bulkSubmode = 'front_only';
      frontOnlyBtn.classList.add('active');
      frontBackBtn.classList.remove('active');
      if (rawFiles.length) processRawFiles();
    };
    frontBackBtn.onclick = () => {
      if (bulkSubmode === 'front_back') return;
      bulkSubmode = 'front_back';
      frontBackBtn.classList.add('active');
      frontOnlyBtn.classList.remove('active');
      if (rawFiles.length) processRawFiles();
    };
  }
}

function setupBulkModeToggle() {
  const singleBtn = document.getElementById('btn-mode-single');
  const bulkBtn = document.getElementById('btn-mode-bulk');
  const singleContainer = document.getElementById('single-scan-container');
  const bulkContainer = document.getElementById('bulk-scan-container');

  if (singleBtn && bulkBtn) {
    singleBtn.onclick = () => {
      singleBtn.classList.add('active');
      bulkBtn.classList.remove('active');
      singleContainer?.classList.remove('hidden');
      bulkContainer?.classList.add('hidden');
    };
    bulkBtn.onclick = () => {
      bulkBtn.classList.add('active');
      singleBtn.classList.remove('active');
      bulkContainer?.classList.remove('hidden');
      singleContainer?.classList.add('hidden');
    };
  }

  window.switchScanMode = (mode) => {
    if (mode === 'single') singleBtn?.click();
    else bulkBtn?.click();
  };
}

function setupBulkDropZone() {
  const dropZone = document.getElementById('bulk-drop-zone');
  const fileInput = document.getElementById('bulk-files-input');
  const cameraInput = document.getElementById('bulk-camera-input');

  if (!dropZone || !fileInput) return;

  dropZone.onclick = e => {
    if (e.target.tagName !== 'INPUT' && !e.target.closest('.camera-btn')) fileInput.click();
  };
  dropZone.ondragover = e => { e.preventDefault(); dropZone.classList.add('dragover'); };
  dropZone.ondragleave = () => dropZone.classList.remove('dragover');
  dropZone.ondrop = e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files) handleBulkFiles(e.dataTransfer.files);
  };

  fileInput.onchange = e => { if (e.target.files) handleBulkFiles(e.target.files); };
  if (cameraInput) {
    cameraInput.onchange = e => { if (e.target.files) handleBulkFiles(e.target.files); };
  }
}

function handleBulkFiles(files) {
  const valid = [];
  const rejected = [];

  Array.from(files).forEach(f => {
    if (!CONFIG.ALLOWED_MIME.includes(f.type)) {
      rejected.push(`${f.name}: Invalid format (only JPEG/PNG/WEBP).`);
    } else if (f.size > CONFIG.MAX_UPLOAD_MB * 1024 * 1024) {
      rejected.push(`${f.name}: Exceeds ${CONFIG.MAX_UPLOAD_MB}MB.`);
    } else {
      valid.push(f);
    }
  });

  const errContainer = document.getElementById('bulk-error-list');
  if (errContainer) {
    if (rejected.length) {
      errContainer.innerHTML = rejected.map(r => `<li>${escapeHtml(r)}</li>`).join('');
      errContainer.classList.remove('hidden');
    } else {
      errContainer.classList.add('hidden');
    }
  }

  if (!valid.length) return;

  rawFiles = valid;
  processRawFiles();
}

function processRawFiles() {
  if (bulkSubmode === 'front_only') {
    stagedPairs = rawFiles.map((file, idx) => {
      const { displayBase } = parseFileName(file.name);
      const label = displayBase.replace(/[_\-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || `Book ${idx + 1}`;
      return {
        id: `book_${idx + 1}_${Date.now()}`,
        label,
        front: { id: `file_${idx}`, file, name: file.name, index: idx, displayLabel: label },
        back: null
      };
    });
    unpairedFiles = [];
    renderPairsReview(false);
  } else {
    const result = pairFiles(rawFiles);
    stagedPairs = result.pairs;
    unpairedFiles = result.unpaired;
    renderPairsReview(result.pairedByOrder);
  }
}

function renderPairsReview(pairedByOrder) {
  document.getElementById('bulk-add-section')?.classList.add('hidden');
  document.getElementById('bulk-review-section')?.classList.remove('hidden');

  const notice = document.getElementById('order-pairing-notice');
  if (notice) notice.classList.toggle('hidden', bulkSubmode === 'front_only' || !pairedByOrder);

  renderPairsList();
  renderUnpairedTray();
  updateStartBatchButton();
}

function renderPairsList() {
  const container = document.getElementById('pairs-list-container');
  if (!container) return;

  container.innerHTML = stagedPairs.map((pair, idx) => `
    <div class="pair-card card" data-id="${pair.id}">
      <div class="pair-left">
        <div class="slot front-slot">
          <img src="${URL.createObjectURL(pair.front.file)}" class="pair-thumb" alt="Front"/>
          <span class="slot-tag">Front</span>
        </div>
        ${bulkSubmode === 'front_only' ? '' : `
        <div class="slot back-slot ${!pair.back ? 'empty-slot' : ''}" ondragover="event.preventDefault()" ondrop="window.dropOnBackSlot(event, '${pair.id}')">
          ${pair.back ? `
            <img src="${URL.createObjectURL(pair.back.file)}" class="pair-thumb" alt="Back"/>
            <span class="slot-tag">Back</span>
          ` : `<span class="empty-text">Drop back here</span>`}
        </div>
        `}
      </div>
      <div class="pair-meta">
        <label class="field-label">Book Label</label>
        <input type="text" class="pair-label-input" value="${escapeHtml(pair.label)}" onchange="window.updatePairLabel('${pair.id}', this.value)"/>
        <div class="pair-files-hint">${escapeHtml(pair.front.name)} ${pair.back ? `&bull; ${escapeHtml(pair.back.name)}` : '(Front only)'}</div>
      </div>
      <div class="pair-actions">
        ${pair.back ? `<button class="btn btn-outline btn-xs" onclick="window.swapPairSides('${pair.id}')">Swap sides</button>` : ''}
        ${pair.back ? `<button class="btn btn-outline btn-xs" onclick="window.removePairBack('${pair.id}')">Remove back</button>` : ''}
        <button class="btn btn-danger-ghost btn-xs" onclick="window.removePairRow('${pair.id}')">Remove book</button>
      </div>
    </div>
  `).join('');
}

function renderUnpairedTray() {
  const traySection = document.getElementById('unpaired-tray-section');
  if (bulkSubmode === 'front_only') {
    if (traySection) traySection.classList.add('hidden');
    return;
  }
  if (traySection) traySection.classList.remove('hidden');

  const tray = document.getElementById('unpaired-tray');
  const countEl = document.getElementById('unpaired-count');
  if (!tray) return;

  if (countEl) countEl.textContent = unpairedFiles.length;

  if (!unpairedFiles.length) {
    tray.innerHTML = `<span class="text-muted" style="font-size: 12px;">No unpaired files.</span>`;
    return;
  }

  tray.innerHTML = unpairedFiles.map(item => `
    <div class="unpaired-chip" draggable="true" ondragstart="event.dataTransfer.setData('text/plain', '${item.id}')">
      <span>📄 ${escapeHtml(item.name)}</span>
      <button class="btn btn-outline btn-xs" onclick="window.makeFrontOnlyBook('${item.id}')">+ Book</button>
    </div>
  `).join('');
}

function updateStartBatchButton() {
  const btn = document.getElementById('btn-start-batch');
  if (btn) {
    btn.disabled = stagedPairs.length === 0;
    btn.textContent = `Start processing (${stagedPairs.length} book${stagedPairs.length === 1 ? '' : 's'})`;
  }
}

function setupReviewActions() {
  document.getElementById('btn-cancel-batch')?.addEventListener('click', () => {
    resetBulkUpload();
  });

  document.getElementById('btn-start-batch')?.addEventListener('click', async () => {
    if (!stagedPairs.length) return;

    const items = stagedPairs.map(p => ({
      label: p.label,
      front_index: p.front.index,
      back_index: p.back ? p.back.index : null
    }));

    try {
      showToast('Uploading batch files and starting queue...', 'info');
      const res = await createBatch(items, rawFiles);
      showQueueView(res.batch_id);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
}

export function resetBulkUpload() {
  stagedPairs = [];
  unpairedFiles = [];
  rawFiles = [];
  document.getElementById('bulk-review-section')?.classList.add('hidden');
  document.getElementById('bulk-queue-section')?.classList.add('hidden');
  document.getElementById('bulk-add-section')?.classList.remove('hidden');
  const input = document.getElementById('bulk-files-input');
  if (input) input.value = '';
}

// Global window actions for inline pair manipulation
window.updatePairLabel = (id, val) => {
  const pair = stagedPairs.find(p => p.id === id);
  if (pair) pair.label = val;
};

window.swapPairSides = (id) => {
  const pair = stagedPairs.find(p => p.id === id);
  if (pair && pair.back) {
    const tmp = pair.front;
    pair.front = pair.back;
    pair.back = tmp;
    renderPairsList();
  }
};

window.removePairBack = (id) => {
  const pair = stagedPairs.find(p => p.id === id);
  if (pair && pair.back) {
    unpairedFiles.push(pair.back);
    pair.back = null;
    renderPairsReview();
  }
};

window.removePairRow = (id) => {
  const pair = stagedPairs.find(p => p.id === id);
  if (pair) {
    if (bulkSubmode !== 'front_only') {
      if (pair.front) unpairedFiles.push(pair.front);
      if (pair.back) unpairedFiles.push(pair.back);
    }
    stagedPairs = stagedPairs.filter(p => p.id !== id);
    renderPairsReview();
  }
};

window.makeFrontOnlyBook = (itemId) => {
  const item = unpairedFiles.find(u => u.id === itemId);
  if (item) {
    unpairedFiles = unpairedFiles.filter(u => u.id !== itemId);
    stagedPairs.push({
      id: `book_${stagedPairs.length + 1}_${Date.now()}`,
      label: item.displayLabel,
      front: item,
      back: null
    });
    renderPairsReview();
  }
};

window.dropOnBackSlot = (e, pairId) => {
  e.preventDefault();
  const fileId = e.dataTransfer.getData('text/plain');
  const item = unpairedFiles.find(u => u.id === fileId);
  const pair = stagedPairs.find(p => p.id === pairId);
  if (item && pair) {
    unpairedFiles = unpairedFiles.filter(u => u.id !== fileId);
    if (pair.back) unpairedFiles.push(pair.back);
    pair.back = item;
    renderPairsReview();
  }
};

window.resetBulkUpload = resetBulkUpload;
