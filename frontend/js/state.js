/**
 * Centralized State Management
 */

class AppState {
  constructor() {
    this.frontFile = null;
    this.backFile = null;
    this.currentBook = null;
    this.activeSide = 'front';
    this.activeField = null;
    this.isHoveringCanvas = false;
    this.libraryBooks = [];
    this.statsData = null;
    this.openedFrom = null;
    this.pendingDeletions = new Map();
    this.listeners = new Set();
  }

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  notify(event, data) {
    this.listeners.forEach(fn => fn(event, data));
  }

  setCurrentBook(book) {
    this.currentBook = book;
    this.activeSide = 'front';
    this.activeField = null;
    this.notify('book:changed', book);
  }

  setActiveSide(side) {
    if (this.activeSide !== side) {
      this.activeSide = side;
      this.notify('side:changed', side);
    }
  }

  setActiveField(fieldName) {
    if (this.activeField !== fieldName) {
      this.activeField = fieldName;
      this.notify('field:changed', fieldName);
    }
  }

  setLibraryBooks(books) {
    this.libraryBooks = books || [];
    this.notify('library:changed', this.libraryBooks);
  }

  setStats(stats) {
    this.statsData = stats;
    this.notify('stats:changed', stats);
  }
}

export const state = new AppState();
