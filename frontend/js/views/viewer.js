/**
 * Interactive Image Viewer & Bounding Box Canvas
 */

import { FIELD_COLORS } from '../../config.js';
import { state } from '../state.js';

let canvas, ctx, img, tooltip;

export function initViewer() {
  canvas = document.getElementById('box-canvas');
  img = document.getElementById('viewer-img');
  tooltip = document.getElementById('box-tooltip');
  if (!canvas || !img) return;

  ctx = canvas.getContext('2d');

  document.getElementById('tab-side-front')?.addEventListener('click', () => switchSide('front'));
  document.getElementById('tab-side-back')?.addEventListener('click', () => switchSide('back'));
  document.getElementById('toggle-ocr-lines')?.addEventListener('change', () => drawBoxes());

  window.addEventListener('resize', () => {
    updateCanvasSize();
    drawBoxes();
  });

  setupCanvasEvents();
  setupFormHoverSync();
}

export function resetViewer() {
  if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (img) img.src = '';
  if (tooltip) tooltip.classList.add('hidden');
}

export function renderViewerBook(book) {
  state.activeSide = 'front';
  updateSideTabs();
  loadViewerImage();
}

export function switchSide(side, callback) {
  if (state.activeSide === side && !callback) return;
  state.setActiveSide(side);
  updateSideTabs();
  loadViewerImage(callback);
}

function updateSideTabs() {
  const { front, back } = getBoxesBySide();
  const frontTab = document.getElementById('tab-side-front');
  const backTab = document.getElementById('tab-side-back');

  if (frontTab) {
    frontTab.textContent = `Front Cover (${front.length})`;
    frontTab.classList.toggle('active', state.activeSide === 'front');
  }
  if (backTab) {
    if (state.currentBook?.back_image_url) {
      backTab.textContent = `Back Cover (${back.length})`;
      backTab.classList.remove('hidden');
      backTab.classList.toggle('active', state.activeSide === 'back');
    } else {
      backTab.classList.add('hidden');
    }
  }
}

function loadViewerImage(callback) {
  if (!img || !state.currentBook) return;
  const cacheKey = state.currentBook.image_hash || Date.now();
  img.onload = () => {
    updateCanvasSize();
    drawBoxes();
    if (callback) callback();
  };
  img.src = `/books/${state.currentBook.id}/image?side=${state.activeSide}&v=${cacheKey}`;
}

function updateCanvasSize() {
  if (!img?.clientWidth || !img?.clientHeight || !canvas) return;
  canvas.style.left = `${img.offsetLeft}px`;
  canvas.style.top = `${img.offsetTop}px`;
  canvas.style.width = `${img.clientWidth}px`;
  canvas.style.height = `${img.clientHeight}px`;

  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(img.clientWidth * dpr);
  canvas.height = Math.round(img.clientHeight * dpr);
  ctx.resetTransform?.();
  ctx.scale(dpr, dpr);
}

function getBoxesBySide() {
  const front = [], back = [];
  if (!state.currentBook?.field_boxes) return { front, back };

  for (const [fieldName, fieldData] of Object.entries(state.currentBook.field_boxes)) {
    const boxes = fieldData.boxes || [];
    for (const b of boxes) {
      const item = { fieldName, value: fieldData.value, color: FIELD_COLORS[fieldName] || '#0f6b5f', bbox: b.bbox, image: b.image };
      if (b.image === 'front') front.push(item);
      else if (b.image === 'back') back.push(item);
    }
  }
  return { front, back };
}

function findBoxAt(nx, ny) {
  let best = null, minArea = Infinity;
  const { front, back } = getBoxesBySide();
  const currentBoxes = state.activeSide === 'front' ? front : back;

  for (const item of currentBoxes) {
    const [x1, y1, x2, y2] = item.bbox;
    if (nx >= x1 && nx <= x2 && ny >= y1 && ny <= y2) {
      const area = (x2 - x1) * (y2 - y1);
      if (area < minArea) {
        minArea = area;
        best = item.fieldName;
      }
    }
  }
  return best;
}

function setupCanvasEvents() {
  canvas.onmousemove = e => {
    state.isHoveringCanvas = true;
    const nx = e.offsetX / img.clientWidth;
    const ny = e.offsetY / img.clientHeight;
    const hit = findBoxAt(nx, ny);

    if (hit) {
      canvas.style.cursor = 'pointer';
      const val = document.getElementById(`field-${hit}`)?.value || 'empty';
      tooltip.textContent = `${hit.toUpperCase()}: ${val}`;
      tooltip.style.left = `${img.offsetLeft + e.offsetX}px`;
      tooltip.style.top = `${img.offsetTop + e.offsetY}px`;
      tooltip.classList.remove('hidden');
      highlightField(hit, true);
    } else {
      canvas.style.cursor = 'default';
      tooltip.classList.add('hidden');
      const focused = document.activeElement?.dataset?.field;
      highlightField(focused || null);
    }
  };

  canvas.onmouseleave = () => {
    state.isHoveringCanvas = false;
    tooltip.classList.add('hidden');
    highlightField(document.activeElement?.dataset?.field || null);
  };

  canvas.onclick = e => {
    const hit = findBoxAt(e.offsetX / img.clientWidth, e.offsetY / img.clientHeight);
    if (hit) {
      document.getElementById(`field-${hit}`)?.focus();
      highlightField(hit, true);
    }
  };
}

export function highlightField(fieldName, shouldScroll = false) {
  if (state.activeField === fieldName && !shouldScroll) return;
  state.activeField = fieldName;

  document.querySelectorAll('.form-group').forEach(fg => {
    fg.classList.remove('field-active');
    fg.style.removeProperty('--active-color');
  });

  if (fieldName) {
    const row = document.querySelector(`.form-group[data-field="${fieldName}"]`);
    if (row) {
      const color = FIELD_COLORS[fieldName] || '#0f6b5f';
      row.classList.add('field-active');
      row.style.setProperty('--active-color', color);
      if (shouldScroll) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }
  requestAnimationFrame(drawBoxes);
}

function setupFormHoverSync() {
  document.querySelectorAll('.form-group[data-field]').forEach(fg => {
    const field = fg.dataset.field;
    fg.onmouseenter = () => { if (!state.isHoveringCanvas) highlightField(field); };
    fg.onmouseleave = () => {
      if (!state.isHoveringCanvas && document.activeElement?.dataset?.field !== field) {
        highlightField(null);
      }
    };
    const input = fg.querySelector('input');
    if (input) {
      input.onfocus = () => highlightField(field, false);
      input.onblur = () => { if (!state.isHoveringCanvas) highlightField(null); };
    }
  });
}

export function drawBoxes() {
  if (!img?.clientWidth || !img?.clientHeight || !ctx) return;
  updateCanvasSize();
  const w = img.clientWidth, h = img.clientHeight;
  ctx.clearRect(0, 0, w, h);

  // Draw OCR lines if toggled
  const ocrToggled = document.getElementById('toggle-ocr-lines')?.checked;
  if (ocrToggled && state.currentBook?.ocr_lines) {
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(239, 68, 68, 0.6)';
    ctx.fillStyle = '#dc2626';
    ctx.font = '10px sans-serif';
    state.currentBook.ocr_lines.filter(l => l.image === state.activeSide).forEach(l => {
      const [x1, y1, x2, y2] = l.bbox;
      ctx.strokeRect(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h);
      ctx.fillText(String(l.id), x1 * w + 2, y1 * h + 10);
    });
  }

  // Draw Field Bounding Boxes
  const { front, back } = getBoxesBySide();
  const boxes = state.activeSide === 'front' ? front : back;

  boxes.forEach(item => {
    const isAct = state.activeField === item.fieldName;
    const hasAct = Boolean(state.activeField);
    const [x1, y1, x2, y2] = item.bbox;
    const bx = x1 * w, by = y1 * h, bw = (x2 - x1) * w, bh = (y2 - y1) * h;

    ctx.strokeStyle = isAct ? item.color : (hasAct ? `${item.color}50` : item.color);
    ctx.lineWidth = isAct ? 3 : (hasAct ? 1 : 2);
    ctx.fillStyle = isAct ? `${item.color}40` : (hasAct ? `${item.color}08` : `${item.color}15`);
    ctx.fillRect(bx, by, bw, bh);
    ctx.strokeRect(bx, by, bw, bh);

    // Label tag
    const tag = item.fieldName.charAt(0).toUpperCase() + item.fieldName.slice(1);
    ctx.font = 'bold 11px sans-serif';
    const tagW = ctx.measureText(tag).width + 8;
    const tagH = 15;
    const tagY = (by - tagH >= 0) ? (by - tagH) : by;

    ctx.fillStyle = isAct ? item.color : (hasAct ? `${item.color}80` : item.color);
    ctx.fillRect(bx, tagY, tagW, tagH);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(tag, bx + 4, tagY + 11);
  });
}
