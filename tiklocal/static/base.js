// Theme Manager
class ThemeManager {
  constructor() {
    this.init();
  }
  init() {
    this.mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const savedTheme = localStorage.getItem('theme');
    this.preference = ['light', 'dark', 'system'].includes(savedTheme) ? savedTheme : 'system';
    this.apply();
    const onSystemThemeChange = () => {
      if (this.preference === 'system') this.apply();
    };
    if (this.mediaQuery.addEventListener) {
      this.mediaQuery.addEventListener('change', onSystemThemeChange);
    } else {
      this.mediaQuery.addListener?.(onSystemThemeChange);
    }
    feather.replace();
  }
  resolvedTheme() {
    return this.preference === 'system'
      ? (this.mediaQuery.matches ? 'dark' : 'light')
      : this.preference;
  }
  apply() {
    const resolved = this.resolvedTheme();
    document.body.setAttribute('data-theme', resolved);
    window.dispatchEvent(new CustomEvent('tiklocal:theme-changed', {
      detail: { preference: this.preference, resolved }
    }));
  }
  setPreference(preference) {
    if (!['light', 'dark', 'system'].includes(preference)) return;
    this.preference = preference;
    localStorage.setItem('theme', preference);
    this.apply();
  }
}

class MoreMenu {
  constructor() {
    this.menu = document.getElementById('app-nav-menu');
    this.trigger = document.getElementById('app-nav-menu-trigger');
    this.bindEvents();
  }
  isOpen() {
    return this.menu?.classList.contains('is-open');
  }
  open() {
    if (!this.menu || !this.trigger) return;
    this.menu.classList.add('is-open');
    this.menu.removeAttribute('inert');
    this.menu.setAttribute('aria-hidden', 'false');
    this.trigger.setAttribute('aria-expanded', 'true');
    document.body.classList.add('app-nav-menu-open');
    this.menu.querySelector('a[href], button')?.focus();
  }
  close({ restoreFocus = true } = {}) {
    if (!this.menu || !this.trigger) return;
    this.menu.classList.remove('is-open');
    this.menu.setAttribute('inert', '');
    this.menu.setAttribute('aria-hidden', 'true');
    this.trigger.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('app-nav-menu-open');
    if (restoreFocus) this.trigger.focus();
  }
  bindEvents() {
    this.trigger?.addEventListener('click', () => this.isOpen() ? this.close() : this.open());
    this.menu?.addEventListener('click', (event) => {
      if (event.target === this.menu) this.close();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && this.isOpen()) this.close();
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.themeManager = new ThemeManager();
  new MoreMenu();
});
