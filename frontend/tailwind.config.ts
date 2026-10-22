import type { Config } from 'tailwindcss';

// Mọi màu lấy từ biến CSS trong src/styles/tokens.css (sáng/tối đổi theo hệ thống).
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
        text: 'var(--text)',
        'text-muted': 'var(--text-muted)',
        border: 'var(--border)',
        primary: 'var(--primary)',
        'on-primary': 'var(--on-primary)',
        accent: 'var(--accent)',
        'on-accent': 'var(--on-accent)',
        'brand-red': 'var(--brand-red)',
        'brand-cream': 'var(--brand-cream)',
        'brand-ink': 'var(--brand-ink)',
        danger: 'var(--danger)',
        focus: 'var(--focus)',
      },
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        hero: ['56px', { lineHeight: '64px', letterSpacing: '-0.02em' }],
        h1: ['36px', { lineHeight: '44px', letterSpacing: '-0.02em' }],
        h2: ['24px', { lineHeight: '32px' }],
        body: ['16px', { lineHeight: '24px' }],
        small: ['14px', { lineHeight: '20px' }],
        tiny: ['12px', { lineHeight: '16px', letterSpacing: '0.04em' }],
      },
      borderRadius: {
        input: '12px',
        card: '20px',
        preview: '16px',
        frame: '24px',
      },
      spacing: {
        18: '72px',
        70: '280px',
        90: '360px',
      },
      transitionTimingFunction: { hbt: 'cubic-bezier(0.2, 0, 0, 1)' },
    },
  },
  plugins: [],
} satisfies Config;
