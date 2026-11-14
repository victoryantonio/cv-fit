/**
 * Light and dark come from one attribute on <html>. The choice is stored so a
 * reload keeps it, and the OS preference is only a default, never a lock.
 */
export type Theme = "light" | "dark";

const STORAGE_KEY = "cv-fit.theme";

function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark";
}

export function readTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isTheme(stored)) return stored;
  } catch {
    // Private mode can throw on storage access; fall through to the OS.
  }
  const prefersDark =
    window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? false;
  return prefersDark ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Not being able to remember the choice is not a reason to fail the click.
  }
}

export function initTheme(): Theme {
  const theme = readTheme();
  document.documentElement.dataset.theme = theme;
  return theme;
}
