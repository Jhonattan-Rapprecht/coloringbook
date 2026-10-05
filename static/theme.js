// Light/dark theme: saved choice wins, otherwise follow the operating system setting.
(function () {
  const KEY = 'theme';
  const root = document.documentElement;
  const media = window.matchMedia('(prefers-color-scheme: dark)');

  function saved() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function current() {
    return saved() || (media.matches ? 'dark' : 'light');
  }
  function apply(theme) {
    root.dataset.theme = theme;
    const button = document.getElementById('theme-toggle');
    if (button) {
      const next = theme === 'dark' ? 'light' : 'dark';
      button.textContent = theme === 'dark' ? '☀️' : '🌙';
      button.title = button.ariaLabel = `Switch to ${next} theme`;
    }
  }

  apply(current());  // runs in <head> before the page paints, so there is no flash
  media.addEventListener('change', () => { if (!saved()) apply(current()); });
  document.addEventListener('DOMContentLoaded', () => {
    apply(current());
    document.getElementById('theme-toggle').addEventListener('click', () => {
      const theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(KEY, theme); } catch (e) { /* private mode: still toggles for this page */ }
      apply(theme);
    });
  });
})();
