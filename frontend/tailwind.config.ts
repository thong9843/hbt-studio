import type { Config } from 'tailwindcss';

// Mọi màu lấy từ biến CSS trong src/styles/tokens.css (sáng/tối đổi theo hệ thống).
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        fg: 'var(--color-fg)',
        muted: 'var(--color-muted)',
        surface: 'var(--color-surface)',
        'surface-2': 'var(--color-surface-2)',
        border: 'var(--color-border)',
        accent: 'var(--color-accent)',
        'on-accent': 'var(--color-on-accent)',
        ok: 'var(--color-ok)',
        'ok-bg': 'var(--color-ok-bg)',
        warn: 'var(--color-warn)',
        'warn-bg': 'var(--color-warn-bg)',
        danger: 'var(--color-danger)',
        'danger-bg': 'var(--color-danger-bg)',
        hbt: {
          red: 'var(--hbt-red)',
          cream: 'var(--hbt-cream)',
          mustard: 'var(--hbt-mustard)',
          ink: 'var(--hbt-ink)',
        },
      },
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
