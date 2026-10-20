import type { Config } from 'tailwindcss';

// Màu lấy từ biến CSS trong src/styles/tokens.css (token từ DESIGN.md bổ sung ở M3).
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        fg: 'var(--color-fg)',
        muted: 'var(--color-muted)',
        surface: 'var(--color-surface)',
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
