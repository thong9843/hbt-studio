import { vi } from '../i18n/vi';

const NAMED = ['ink', 'primary', 'accent'] as const;
const HEX = /^#[0-9a-fA-F]{6}$/;

interface Props {
  value: string;
  onChange: (value: string) => void;
  label: string;
}

/** Chọn màu theo tên (mực / chủ đạo / nhấn) hoặc một màu #RRGGBB tuỳ ý. */
export function ColorField({ value, onChange, label }: Props) {
  const isNamed = (NAMED as readonly string[]).includes(value);
  const hex = HEX.test(value) ? value : '#000000';
  return (
    <div className="flex items-center gap-2">
      <select
        aria-label={label}
        className="input"
        value={isNamed ? value : 'custom'}
        onChange={(e) => onChange(e.target.value === 'custom' ? hex : e.target.value)}
      >
        {NAMED.map((name) => (
          <option key={name} value={name}>
            {vi.compose.colors[name]}
          </option>
        ))}
        <option value="custom">{vi.compose.colors.custom}</option>
      </select>
      {!isNamed && (
        <input
          type="color"
          aria-label={`${label} (${vi.compose.colors.custom})`}
          value={hex}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-9 w-12 shrink-0 cursor-pointer rounded-lg border border-border bg-bg p-0.5"
        />
      )}
    </div>
  );
}
