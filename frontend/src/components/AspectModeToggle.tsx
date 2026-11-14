import type { AspectMode } from '../api/types';

interface AspectModeToggleProps {
  value: AspectMode;
  onChange: (next: AspectMode) => void;
  disabled?: boolean;
}

/** Nút chọn nhanh chế độ khung hình 9:16: Lấp đầy (fill) hoặc Vừa khung nền mờ (fit). */
export function AspectModeToggle({ value, onChange, disabled }: AspectModeToggleProps) {
  return (
    <div
      role="group"
      aria-label="Khung hình 9:16"
      className="inline-flex items-center rounded-xl border border-white/10 bg-[#1A2234] p-0.5 text-xs"
    >
      <button
        type="button"
        disabled={disabled}
        aria-pressed={value === 'fill'}
        onClick={() => onChange('fill')}
        className={`rounded-lg px-2.5 py-1 font-medium transition-colors ${
          value === 'fill'
            ? 'bg-rose-600 text-white shadow-sm'
            : 'text-[#94A3B8] hover:text-[#F8FAFC]'
        }`}
      >
        Lấp đầy (fill)
      </button>
      <button
        type="button"
        disabled={disabled}
        aria-pressed={value === 'fit'}
        onClick={() => onChange('fit')}
        className={`rounded-lg px-2.5 py-1 font-medium transition-colors ${
          value === 'fit'
            ? 'bg-rose-600 text-white shadow-sm'
            : 'text-[#94A3B8] hover:text-[#F8FAFC]'
        }`}
      >
        Vừa khung nền mờ (fit)
      </button>
    </div>
  );
}
