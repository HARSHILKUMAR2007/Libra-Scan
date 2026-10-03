/**
 * Bulk Queue Monitoring & Live Polling Controller
 */

import { fetchBatch, retryJob, cancelJob, retryFailedBatchJobs, clearFinishedBatchJobs, fetchActiveBatches } from './api.js';
import { showToast } from './toast.js';
import { navigateTo } from './router.js';
import { escapeHtml } from './utils.js';

let pollTimer = null;
let pollStartTime = 0;
let currentBatchId = null;
let isFinishedNotified = false;

export function showQueueView(batchId) {
  currentBatchId = batchId;
  isFinishedNotified = false;
  pollStartTime = Date.now();
  localStorage.setItem('librascan_active_batch_id', batchId);

  document.getElementById('bulk-add-section')?.classList.add('hidden');
  document.getElementById('bulk-review-section')?.classList.add('hidden');
  const queueSection = document.getElementById('bulk-queue-section');
  if (queueSection) queueSection.classList.remove('hidden');

  setupQueueHeaderActions();
  startPolling(batchId);
}

function startPolling(batchId) {
  stopPolling();
  fetchAndRenderQueue(batchId);

  const poll = () => {
    if (document.hidden) return; // Pause polling when tab is hidden
    const elapsed = Date.now() - pollStartTime;
    const interval = elapsed > 60000 ? 5000 : 1500; // Back off to 5s after 1 min

    pollTimer = setTimeout(async () => {
      const isTerminal = await fetchAndRenderQueue(batchId);
      if (!isTerminal) poll();
    }, interval);
  };
  poll();
}

export function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

// Pause/resume on tab visibility
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && currentBatchId && !pollTimer) {
    startPolling(currentBatchId);
  }
});

async function fetchAndRenderQueue(batchId) {
  try {
    const summary = await fetchBatch(batchId);
    renderQueueSummary(summary);
    renderJobRows(summary.jobs);
    updateActiveSidebarBadge();

    const counts = summary.counts;
    const activeCount = (counts.queued || 0) + (counts.processing || 0);

    if (activeCount === 0 && summary.total > 0 && !isFinishedNotified) {
      isFinishedNotified = true;
      const reviewCount = summary.jobs.filter(j => j.needs_review).length;
      showToast(`${summary.done_count} books processed (${reviewCount} need review).`, 'success');
      return true; // Stop polling
    }
    return activeCount === 0;
  } catch (err) {
    console.error('Queue poll error:', err);
    return false;
  }
}

function renderQueueSummary(summary) {
  const { total, done_count, counts, avg_seconds_per_job } = summary;
  const pct = total > 0 ? Math.round((done_count / total) * 100) : 0;

  const bar = document.getElementById('queue-progress-bar');
  if (bar) bar.style.width = `${pct}%`;

  const countsEl = document.getElementById('queue-summary-text');
  if (countsEl) {
    countsEl.textContent = `${done_count} of ${total} done &bull; ${counts.processing || 0} processing &bull; ${counts.failed || 0} failed`;
  }

  const elapsedSec = Math.floor((Date.now() - pollStartTime) / 1000);
  const remainingJobs = (counts.queued || 0) + (counts.processing || 0);
  const etaSec = avg_seconds_per_job > 0 && remainingJobs > 0 ? Math.round(remainingJobs * avg_seconds_per_job) : null;

  const etaEl = document.getElementById('queue-eta-text');
  if (etaEl) {
    etaEl.textContent = etaSec !== null ? `ETA: ~${etaSec}s (${elapsedSec}s elapsed)` : `${elapsedSec}s elapsed`;
  }

  // Toggle "Go to Review Queue" button if any book needs review
  const hasReview = summary.jobs.some(j => j.needs_review);
  document.getElementById('btn-queue-review')?.classList.toggle('hidden', !hasReview);
  document.getElementById('btn-queue-retry-failed')?.classList.toggle('hidden', (counts.failed || 0) === 0);
}

function renderJobRows(jobs) {
  const tbody = document.getElementById('queue-jobs-tbody');
  if (!tbody) return;

  tbody.innerHTML = jobs.map(j => {
    const pillClass = { queued: 'pill-pending', processing: 'pill-blue', done: 'pill-confirmed', duplicate: 'pill-review', failed: 'pill-red', canceled: 'pill-pending' }[j.status] || 'pill-pending';
    const stepLabel = j.status === 'processing' ? `(${j.step || 'Starting...'})` : '';

    return `
      <tr class="queue-row" data-id="${j.id}">
        <td><img src="${j.front_url}" class="thumb" onerror="this.src=''"/></td>
        <td>
          <div class="table-title">${escapeHtml(j.label || 'Book')}</div>
          ${j.title ? `<div class="table-subtitle">${escapeHtml(j.title)}</div>` : ''}
          ${j.authors?.length ? `<div class="table-subtitle text-muted">${escapeHtml(j.authors.join(', '))}</div>` : ''}
          ${j.error ? `<div class="text-danger" style="font-size: 11px; margin-top: 2px;">⚠️ ${escapeHtml(j.error)}</div>` : ''}
        </td>
        <td>
          <span class="status-pill ${pillClass}">${j.status.toUpperCase()} ${stepLabel}</span>
        </td>
        <td>
          ${j.confidence ? `<span class="conf-badge">${Math.round(j.confidence * 100)}%</span>` : '-'}
          ${j.needs_review ? `<span class="status-pill pill-review" style="margin-left:4px;">Review</span>` : ''}
        </td>
        <td style="text-align: right;">
          ${j.book_id ? `<button class="btn btn-outline btn-xs" onclick="window.openBookFromQueue(${j.book_id})">Open</button>` : ''}
          ${j.status === 'failed' ? `<button class="btn btn-outline btn-xs" onclick="window.retryQueueJob(${j.id})">Retry</button>` : ''}
          ${j.status === 'queued' ? `<button class="btn btn-danger-ghost btn-xs" onclick="window.cancelQueueJob(${j.id})">Cancel</button>` : ''}
        </td>
      </tr>
    `;
  }).join('');
}

function setupQueueHeaderActions() {
  document.getElementById('btn-queue-retry-failed').onclick = async () => {
    if (!currentBatchId) return;
    await retryFailedBatchJobs(currentBatchId);
    showToast('Retrying failed jobs...', 'info');
    fetchAndRenderQueue(currentBatchId);
  };

  document.getElementById('btn-queue-clear-finished').onclick = async () => {
    if (!currentBatchId) return;
    await clearFinishedBatchJobs(currentBatchId);
    showToast('Cleared finished jobs from view.', 'info');
    fetchAndRenderQueue(currentBatchId);
  };

  document.getElementById('btn-queue-review').onclick = () => {
    navigateTo('review');
  };

  document.getElementById('btn-queue-new-batch').onclick = () => {
    localStorage.removeItem('librascan_active_batch_id');
    stopPolling();
    window.resetBulkUpload();
  };
}

export async function updateActiveSidebarBadge() {
  try {
    const res = await fetchActiveBatches();
    const count = res.active_job_count || 0;
    const badge = document.getElementById('nav-scan-badge');
    const mobBadge = document.getElementById('mob-nav-scan-badge');
    [badge, mobBadge].forEach(b => {
      if (b) {
        b.textContent = count;
        b.classList.toggle('hidden', count === 0);
      }
    });
  } catch (err) {}
}

window.openBookFromQueue = (bookId) => {
  window.dispatchEvent(new CustomEvent('load-book', { detail: bookId }));
  document.getElementById('btn-mode-single')?.click();
};

window.retryQueueJob = async (jobId) => {
  await retryJob(jobId);
  showToast('Job re-queued.', 'info');
  if (currentBatchId) fetchAndRenderQueue(currentBatchId);
};

window.cancelQueueJob = async (jobId) => {
  await cancelJob(jobId);
  showToast('Job canceled.', 'info');
  if (currentBatchId) fetchAndRenderQueue(currentBatchId);
};