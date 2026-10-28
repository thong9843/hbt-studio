import type { Theme } from '../../api/types';
import { vi } from '../../i18n/vi';
import { cx } from '../ui/cx';
import { PlusIcon } from '../icons';

const NAMED = ['ink', 'primary', 'accent'] as const;
const HEX = /^#[0-9a-fA-F]{6}$/;
/** Màu "Mực" của bộ vẽ thẻ (chỉ để tô chấm; bản vẽ thật do backend). */
const INK = '#16120F';

interface Props {
  value: string;
  theme: Theme;
  label: string;
  onChange: (value: string) => void;
}

/** Ba chấm Mực / Chính / Nhấn và một chấm chọn màu #RRGGBB. Mỗi chấm có tên đọc được. */
export function ColorDots({ value, theme, label, onChange }: Props) {
  const T = vi.compose.card.colors;
  const swatch = { ink: INK, primary: theme.primary, accent: theme.accent };
  const custom = !(NAMED as readonly string[]).includes(value);
  const hex = HEX.test(value) ? value : '#000000';
  return (
    <div role="group" aria-label={label} className="flex items-center gap-2">
      {NAMED.map((name) => (
        <button
          key={name}
          type="button"
          className="ui-dot"
          aria-pressed={value === name}
          aria-label={T[name]}
          title={T[name]}
          style={{ background: swatch[name] }}
          onClick={() => onChange(name)}
        />
      ))}
      <label
        className="ui-dot"
        data-on={custom}
        title={T.custom}
        style={custom ? { background: hex } : undefined}
      >
        {!custom && <PlusIcon size={14} />}
        <input
          type="color"
          aria-label={T.custom}
          value={hex}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
        />
      </label>
      <span className={cx('text-tiny font-semibold text-muted')} aria-hidden="true">
        {custom ? T.custom : T[value as (typeof NAMED)[number]]}
      </span>
    </div>
  );
}
