import { cx } from './cx';
import './ui.css';

interface Props {
  /** 0-100. */
  value: number;
  label: string;
  className?: string;
}

/** Thanh tiến độ: đổi `transform: scaleX()` 300 ms tuyến tính, không đổi `width`. */
export function Progress({ value, label, className }: Props) {
  const v = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v)}
      className={cx('ui-progress', className)}
    >
      <div className="ui-progress-bar" style={{ transform: `scaleX(${v / 100})` }} />
    </div>
  );
}
