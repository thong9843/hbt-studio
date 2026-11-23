import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { vi } from '../../i18n/vi';

interface EngineCardDef {
  key: string;
  to: string;
  title: string;
  desc: string;
  cta: string;
  primary?: boolean;
  art: ReactNode;
}

/** Minh họa SVG tối giản, sắc nét (0% CPU, thích ứng Light/Dark theo CSS tokens). */
function CoreArt() {
  return (
    <svg viewBox="0 0 160 64" className="h-14 w-full" fill="none" aria-hidden="true">
      <rect
        x="16"
        y="8"
        width="36"
        height="48"
        rx="6"
        fill="var(--card)"
        stroke="var(--border-subtle)"
      />
      <rect x="21" y="13" width="26" height="10" rx="3" fill="var(--brand)" />
      <rect x="21" y="27" width="26" height="14" rx="3" fill="var(--soft-2)" />
      <rect x="25" y="45" width="18" height="4" rx="2" fill="var(--line-input)" />
      <rect x="64" y="16" width="68" height="6" rx="3" fill="var(--text)" opacity="0.75" />
      <rect x="64" y="28" width="52" height="5" rx="2.5" fill="var(--line-input)" />
      <rect x="64" y="39" width="38" height="5" rx="2.5" fill="var(--soft-2)" />
    </svg>
  );
}

function PostvArt() {
  return (
    <svg viewBox="0 0 160 64" className="h-14 w-full" fill="none" aria-hidden="true">
      <rect
        x="18"
        y="10"
        width="124"
        height="44"
        rx="8"
        fill="var(--card)"
        stroke="var(--border-subtle)"
      />
      <circle cx="32" cy="23" r="6" fill="var(--text)" opacity="0.85" />
      <rect x="44" y="19" width="44" height="5" rx="2.5" fill="var(--text)" opacity="0.75" />
      <rect x="44" y="27" width="28" height="4" rx="2" fill="var(--line-input)" />
      <rect x="26" y="38" width="96" height="4" rx="2" fill="var(--line-input)" />
      <rect x="26" y="45" width="72" height="4" rx="2" fill="var(--soft-2)" />
    </svg>
  );
}

function ChattingArt() {
  return (
    <svg viewBox="0 0 160 64" className="h-14 w-full" fill="none" aria-hidden="true">
      <rect x="18" y="10" width="74" height="16" rx="8" fill="var(--card)" stroke="var(--line)" />
      <rect x="27" y="16" width="44" height="4" rx="2" fill="var(--line-input)" />
      <rect x="68" y="30" width="74" height="16" rx="8" fill="var(--brand)" />
      <rect x="78" y="36" width="46" height="4" rx="2" fill="#ffffff" opacity="0.9" />
      <rect x="18" y="50" width="52" height="8" rx="4" fill="var(--card)" stroke="var(--line)" />
    </svg>
  );
}

function StickvArt() {
  return (
    <svg viewBox="0 0 160 64" className="h-14 w-full" fill="none" aria-hidden="true">
      <rect
        x="68"
        y="10"
        width="74"
        height="44"
        rx="7"
        fill="var(--card)"
        stroke="var(--border-subtle)"
      />
      <rect x="78" y="19" width="38" height="5" rx="2.5" fill="var(--brand)" />
      <rect x="78" y="29" width="52" height="4" rx="2" fill="var(--line-input)" />
      <rect x="78" y="38" width="40" height="4" rx="2" fill="var(--soft-2)" />
      <circle cx="38" cy="20" r="7" stroke="var(--text)" strokeWidth="2.5" />
      <path
        d="M38 27v15m0-11 12-4m-12 4-9 6m9 5-7 10m7-10 7 10"
        stroke="var(--text)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * 4 Thẻ Động cơ Sáng tạo tối giản cực đoan:
 * Tên 2 từ + mô tả <= 6 từ + minh họa SVG sắc nét + nút 2 từ.
 */
export function EngineShowcaseCards() {
  const E = vi.veedHome.engines;
  const cards: EngineCardDef[] = [
    {
      key: 'core',
      to: '/core',
      title: E.coreTitle,
      desc: E.coreDesc,
      cta: E.coreCta,
      art: <CoreArt />,
    },
    {
      key: 'postv',
      to: '/postv',
      title: E.postvTitle,
      desc: E.postvDesc,
      cta: E.postvCta,
      art: <PostvArt />,
    },
    {
      key: 'chatting',
      to: '/chatting',
      title: E.chattingTitle,
      desc: E.chattingDesc,
      cta: E.chattingCta,
      art: <ChattingArt />,
    },
    {
      key: 'stickv',
      to: '/stickv',
      title: E.stickvTitle,
      desc: E.stickvDesc,
      cta: E.stickvCta,
      primary: true,
      art: <StickvArt />,
    },
  ];

  return (
    <section
      aria-label="4 Động cơ Sáng tạo"
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
    >
      {cards.map((c) => (
        <div
          key={c.key}
          className="group flex flex-col justify-between rounded-card border border-line bg-card p-4 shadow-card transition-colors hover:border-brand"
        >
          <div>
            <div className="mb-3 rounded-inner border border-line bg-soft px-2 py-2">{c.art}</div>
            <h2 className="text-body font-extrabold tracking-tight text-text">{c.title}</h2>
            <p className="mt-0.5 text-tiny font-medium text-muted">{c.desc}</p>
          </div>

          <div className="mt-4">
            <Link
              to={c.to}
              className={`ui-btn ui-btn-sm w-full justify-center ${c.primary ? 'ui-btn-brand' : 'ui-btn-ink'}`}
            >
              {c.cta}
            </Link>
          </div>
        </div>
      ))}
    </section>
  );
}
