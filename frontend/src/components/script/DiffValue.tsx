import type { Card, CardLine, Theme } from '../../api/types';
import { vi } from '../../i18n/vi';

const T = vi.script;
const INK = '#16120F';
const NAMED: Record<string, keyof typeof T.colors> = {
  ink: 'ink',
  primary: 'primary',
  accent: 'accent',
};

function swatch(color: string, theme: Theme): string {
  if (color === 'ink') return INK;
  if (color === 'primary') return theme.primary;
  if (color === 'accent') return theme.accent;
  return color;
}

function Line({ line, theme }: { line: CardLine; theme: Theme }) {
  const name = NAMED[line.color] ? T.colors[NAMED[line.color]] : line.color;
  return (
    <li className="flex items-center gap-2">
      <span
        className="inline-block size-3 shrink-0 rounded-full border border-line"
        style={{ background: swatch(line.color, theme) }}
        role="img"
        aria-label={name}
      />
      <span className="min-w-0 break-words">{line.text || T.empty}</span>
      <span className="ml-auto shrink-0 rounded-full bg-soft px-2 text-tiny font-bold uppercase">
        {line.size}
      </span>
    </li>
  );
}

function CardView({ card, theme }: { card: Card; theme: Theme }) {
  return (
    <div>
      <p className="text-tiny text-muted">
        {T.fields.y}: {String(card.y)} · {T.lines(card.lines.length)}
      </p>
      <ul className="mt-1 space-y-1">
        {card.lines.map((l, i) => (
          <Line key={i} line={l} theme={theme} />
        ))}
      </ul>
    </div>
  );
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

function isCard(v: unknown): v is Card {
  return isObject(v) && Array.isArray(v.lines);
}

/** Một giá trị cũ hoặc mới của khối diff, theo tên trường. */
export function DiffValue({
  field,
  value,
  theme,
}: {
  field: string;
  value: unknown;
  theme: Theme;
}) {
  if (value === null || value === undefined) {
    return <span className="text-muted">{field === 'caption_y' ? T.auto : T.empty}</span>;
  }
  if (field === 'card' && isCard(value)) return <CardView card={value} theme={theme} />;
  if (field === 'voice' && typeof value === 'string') {
    return <span className="break-words">{value.trim() ? value : T.empty}</span>;
  }
  if (field === 'punch') return <span>{value ? T.yes : T.no}</span>;
  if (field === 'caption_y') return <span>{`${String(value)} px`}</span>;
  if (field === 'labels' && Array.isArray(value)) return <span>{T.labelsCount(value.length)}</span>;
  if (field === 'publish' && isObject(value)) {
    const tags = Array.isArray(value.hashtags) ? value.hashtags.map((t) => `#${String(t)}`) : [];
    return (
      <span className="break-words">
        {[String(value.hook ?? ''), tags.join(' ')].filter(Boolean).join(' · ') || T.empty}
      </span>
    );
  }
  if (field === 'thumbnail' && isObject(value)) {
    const lines = Array.isArray(value.lines) ? value.lines.map(String).join(' / ') : '';
    return (
      <span className="break-words">
        {T.scene(Number(value.scene) || 1)} · {lines || T.empty}
      </span>
    );
  }
  if (field === 'scene' && isObject(value)) {
    return (
      <div className="space-y-1">
        {isCard(value.card) && <CardView card={value.card} theme={theme} />}
        {typeof value.voice === 'string' && value.voice && (
          <p className="break-words">{value.voice}</p>
        )}
      </div>
    );
  }
  return (
    <span className="break-words">{typeof value === 'string' ? value : JSON.stringify(value)}</span>
  );
}
