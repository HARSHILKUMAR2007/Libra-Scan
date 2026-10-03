/**
 * Toast Notification System
 */

export function showToast(message, type = 'info', action = null, duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  const textSpan = document.createElement('span');
  textSpan.className = 'toast-text';
  textSpan.textContent = message;
  toast.appendChild(textSpan);

  let timeoutId = null;

  if (action && action.text && action.onClick) {
    const actionBtn = document.createElement('button');
    actionBtn.className = 'toast-action-btn';
    actionBtn.textContent = action.text;
    actionBtn.onclick = (e) => {
      e.stopPropagation();
      clearTimeout(timeoutId);
      dismissToast(toast);
      action.onClick();
    };
    toast.appendChild(actionBtn);
  }

  const closeBtn = document.createElement('button');
  closeBtn.className = 'toast-close-btn';
  closeBtn.innerHTML = '&times;';
  closeBtn.onclick = () => {
    clearTimeout(timeoutId);
    dismissToast(toast);
  };
  toast.appendChild(closeBtn);

  container.appendChild(toast);

  timeoutId = setTimeout(() => {
    dismissToast(toast);
  }, duration);

  return () => {
    clearTimeout(timeoutId);
    dismissToast(toast);
  };
}

function dismissToast(toast) {
  if (!toast || !toast.parentNode) return;
  toast.classList.add('toast-dismissing');
  setTimeout(() => {
    toast.remove();
  }, 250);
}
