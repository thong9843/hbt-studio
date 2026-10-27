import { cx } from './cx';
import './ui.css';

interface Props {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
  className?: string;
}

/** Công tắc bật/tắt; núm trượt bằng `translateX` 150 ms. */
export function Switch({ checked, onChange, label, disabled, className }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={cx('ui-switch', className)}
      onClick={() => onChange(!checked)}
    />
  );
}
