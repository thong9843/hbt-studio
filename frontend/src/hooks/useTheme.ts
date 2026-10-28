import { useCallback, useEffect, useState } from 'react';
import { applyTheme, currentTheme, readStoredTheme, storeTheme, type Theme } from '../utils/theme';

/** Chế độ sáng/tối: lần đầu theo hệ thống, bấm đổi rồi thì nhớ lựa chọn. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  // Chưa chọn bao giờ thì đi theo hệ thống khi hệ thống đổi.
  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (readStoredTheme() === null) setTheme(currentTheme());
    };
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  const toggle = useCallback(() => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    storeTheme(next);
    setTheme(next);
  }, [theme]);

  return { theme, toggle };
}
