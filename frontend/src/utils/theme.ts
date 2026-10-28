export type Theme = 'light' | 'dark';

/** Khoá localStorage; script trong index.html dùng đúng khoá này. */
export const THEME_KEY = 'hbt-theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

/** Chế độ đã lưu; `null` khi chưa chọn hoặc localStorage không dùng được. */
export function readStoredTheme(): Theme | null {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

export function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* private window hoặc bị chặn: vẫn đổi được trong phiên này */
  }
}

export function systemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
}

/** Chế độ đang hiển thị: đã lưu thì theo đã lưu, chưa thì theo hệ thống. */
export function currentTheme(): Theme {
  return readStoredTheme() ?? systemTheme();
}

/** Ép một chế độ lên <html> (CSS đã có khối `[data-theme]`). */
export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
}
