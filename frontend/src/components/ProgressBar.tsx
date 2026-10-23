interface Props {
  /** 0..100 */
  value: number;
  /** Tên bước hiện tại, hiển thị bằng chữ cạnh phần trăm. */
  step: string;
  label: string;
  message?: string;
}

/** Thanh tiến độ cao 8, bo tròn, kèm tên bước và phần trăm bằng chữ (DESIGN-HBT.md mục 6). */
export function ProgressBar({ value, step, label, message }: Props) {
  const pct = Math.round(Math.min(100, Math.max(0, value)));
  return (
    <div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="h-2 w-full overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-200 ease-hbt"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-2 text-small">
        <span className="num">{pct}%</span>
        {step && <span> · {step}</span>}
        {message && <span className="text-text-muted"> — {message}</span>}
      </p>
    </div>
  );
}
