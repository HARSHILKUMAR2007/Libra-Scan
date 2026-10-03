/**
 * API Service Client
 */

export async function fetchStats() {
  const res = await fetch('/stats');
  if (!res.ok) throw new Error('Failed to load stats');
  return res.json();
}

export async function fetchBooks(status = '') {
  const url = status ? `/books?status=${encodeURIComponent(status)}&limit=100` : '/books?limit=100';
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to load library books');
  return res.json();
}

export async function fetchBook(id) {
  const res = await fetch(`/books/${id}`);
  if (!res.ok) throw new Error(`Failed to load book #${id}`);
  return res.json();
}

export async function uploadBookImages(frontFile, backFile) {
  const fd = new FormData();
  fd.append('front', frontFile);
  if (backFile) fd.append('back', backFile);

  const res = await fetch('/books/upload', {
    method: 'POST',
    body: fd
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to process cover images');
  }
  return res.json();
}

export async function updateBook(id, payload) {
  const res = await fetch(`/books/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to save changes');
  }
  return res.json();
}

export async function deleteBook(id) {
  const res = await fetch(`/books/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete book');
  return res.json();
}

export function getExportCsvUrl() {
  return '/books/export.csv';
}

export async function createBatch(items, files) {
  const fd = new FormData();
  fd.append('items', JSON.stringify(items));
  files.forEach(f => fd.append('files', f));

  const res = await fetch('/batches', {
    method: 'POST',
    body: fd
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create bulk upload batch');
  }
  return res.json();
}

export async function fetchBatch(batchId) {
  const res = await fetch(`/batches/${batchId}`);
  if (!res.ok) throw new Error('Failed to load batch status');
  return res.json();
}

export async function fetchActiveBatches() {
  const res = await fetch('/batches/active');
  if (!res.ok) throw new Error('Failed to load active batches');
  return res.json();
}

export async function retryJob(jobId) {
  const res = await fetch(`/jobs/${jobId}/retry`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to retry job');
  return res.json();
}

export async function cancelJob(jobId) {
  const res = await fetch(`/jobs/${jobId}/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to cancel job');
  return res.json();
}

export async function retryFailedBatchJobs(batchId) {
  const res = await fetch(`/batches/${batchId}/retry-failed`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to retry failed batch jobs');
  return res.json();
}

export async function clearFinishedBatchJobs(batchId) {
  const res = await fetch(`/batches/${batchId}/finished`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to clear finished jobs');
  return res.json();
}
